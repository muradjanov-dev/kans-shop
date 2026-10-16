from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ReplyKeyboardRemove

from app.bot.handlers.user import (
    catalog,
)
from app.bot.keyboards.callback_data import (
    ORIGIN_CATEGORY,
    ORIGIN_SEARCH,
    ROOT_CATEGORY_ID,
    AddToCartCallback,
    CartActionCallback,
    CategoryCallback,
    ContinueShoppingCallback,
)
from app.bot.keyboards.inline.catalog import product_detail_keyboard
from app.bot.utils.messages import answer_callback_safely, edit_or_send_message
from app.core.exceptions import CategoryNotFoundError, OutOfStockError
from app.services.inventory_policy import InventoryPolicy


def _bad_request(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=SimpleNamespace(), message=message)


async def test_expired_add_to_cart_callback_does_not_mutate_cart(monkeypatch) -> None:
    calls: list[str] = []

    async def answer(text=None, *, show_alert=False):
        calls.append("answer")
        raise _bad_request("query is too old and response timeout expired")

    message = SimpleNamespace(answer=AsyncMock())
    callback = SimpleNamespace(answer=answer, message=message)

    add_item = AsyncMock()
    monkeypatch.setattr(catalog.cart_service, "add_item", add_item)
    callback_data = AddToCartCallback(product_id=7, qty=1, origin="category", ref_id=2, page=1)

    await catalog.on_add_to_cart(
        callback,
        callback_data,
        SimpleNamespace(),
        SimpleNamespace(id=3),
        lambda key, **_: key,
    )

    assert calls == ["answer"]
    add_item.assert_not_awaited()
    message.answer.assert_not_awaited()


async def test_add_to_cart_acknowledges_before_service_and_falls_back_to_message(
    monkeypatch,
) -> None:
    calls: list[str] = []

    async def answer(text=None, *, show_alert=False):
        calls.append("answer")

    async def add_item(*_args):
        calls.append("service")
        raise OutOfStockError("out of stock")

    message = SimpleNamespace(answer=AsyncMock())
    callback = SimpleNamespace(answer=answer, message=message)
    monkeypatch.setattr(catalog.cart_service, "add_item", add_item)
    callback_data = AddToCartCallback(product_id=7, qty=1, origin="category", ref_id=2, page=1)

    await catalog.on_add_to_cart(
        callback,
        callback_data,
        SimpleNamespace(),
        SimpleNamespace(id=3),
        lambda key, **_: key,
    )

    assert calls == ["answer", "service"]
    message.answer.assert_awaited_once()
    assert message.answer.await_args.args == ("cart.out_of_stock_alert",)
    assert isinstance(message.answer.await_args.kwargs["reply_markup"], ReplyKeyboardRemove)


async def test_successful_add_sends_one_message_with_continue_and_cart_choices(
    monkeypatch,
) -> None:
    first_sent_message = SimpleNamespace()
    transient_message = SimpleNamespace(delete=AsyncMock())
    callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(
            photo=[SimpleNamespace(file_id="photo-1")],
            answer=AsyncMock(side_effect=[first_sent_message, transient_message]),
        ),
    )
    add_item = AsyncMock()
    monkeypatch.setattr(catalog.cart_service, "add_item", add_item)
    callback_data = AddToCartCallback(product_id=7, qty=4, origin="category", ref_id=2, page=1)

    await catalog.on_add_to_cart(
        callback,
        callback_data,
        SimpleNamespace(),
        SimpleNamespace(id=3),
        lambda key, **_: key,
    )

    add_item.assert_awaited_once_with(SimpleNamespace(), 3, 7, 4)
    assert callback.message.answer.await_count == 2
    feedback = callback.message.answer.await_args_list[0]
    assert feedback.args == ("cart.added_alert",)
    assert feedback.kwargs["reply_markup"] is not None
    assert not isinstance(feedback.kwargs["reply_markup"], ReplyKeyboardRemove)
    cleanup = callback.message.answer.await_args_list[1]
    assert cleanup.args == ("cart.added_alert",)
    assert isinstance(cleanup.kwargs["reply_markup"], ReplyKeyboardRemove)
    transient_message.delete.assert_awaited_once_with()
    assert callback.answer.await_count == 1
    keyboard = feedback.kwargs["reply_markup"]
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.text for button in buttons] == [
        "catalog.continue_shopping",
        "cart.open_button",
    ]


async def test_catalog_entry_sends_all_root_categories_inline_and_cleans_transient_reply_keyboard(
    monkeypatch,
) -> None:
    categories = [
        SimpleNamespace(id=11, name_uz="Yozuv", name_ru="Письмо"),
        SimpleNamespace(id=12, name_uz="Qog'oz", name_ru="Бумага"),
        SimpleNamespace(id=13, name_uz="Maktab", name_ru="Школа"),
    ]
    first_sent_message = SimpleNamespace()
    transient_message = SimpleNamespace(delete=AsyncMock())
    message = SimpleNamespace(
        answer=AsyncMock(side_effect=[first_sent_message, transient_message])
    )
    list_root_categories = AsyncMock(return_value=categories)
    monkeypatch.setattr(catalog.catalog_service, "list_root_categories", list_root_categories)

    await catalog.open_catalog(message, SimpleNamespace(), "uz", lambda key: key)

    assert message.answer.await_count == 2
    category_message = message.answer.await_args_list[0]
    assert category_message.args == ("catalog.choose_category",)
    markup = category_message.kwargs["reply_markup"]
    category_buttons = [button for row in markup.inline_keyboard for button in row]
    assert [button.text for button in category_buttons] == ["Yozuv", "Qog'oz", "Maktab"]
    assert [
        CategoryCallback.unpack(button.callback_data).category_id
        for button in category_buttons
    ] == [11, 12, 13]
    cleanup = message.answer.await_args_list[1]
    assert cleanup.args == ("catalog.choose_category",)
    assert isinstance(cleanup.kwargs["reply_markup"], ReplyKeyboardRemove)
    transient_message.delete.assert_awaited_once_with()
    list_root_categories.assert_awaited_once_with(SimpleNamespace())


async def test_add_continue_and_add_second_product_is_one_mutation_per_product(
    monkeypatch,
) -> None:
    add_item = AsyncMock()
    send_product_list = AsyncMock()
    monkeypatch.setattr(catalog.cart_service, "add_item", add_item)
    monkeypatch.setattr(catalog, "send_product_list", send_product_list)
    monkeypatch.setattr(
        catalog.catalog_service,
        "get_category",
        AsyncMock(return_value=SimpleNamespace(id=42)),
    )
    session = SimpleNamespace()
    user = SimpleNamespace(id=3)

    first_sent_message = SimpleNamespace()
    first_transient_message = SimpleNamespace(delete=AsyncMock())
    first_callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(
            answer=AsyncMock(side_effect=[first_sent_message, first_transient_message])
        ),
    )
    await catalog.on_add_to_cart(
        first_callback,
        AddToCartCallback(
            product_id=7,
            qty=4,
            origin=ORIGIN_CATEGORY,
            ref_id=42,
            page=3,
        ),
        session,
        user,
        lambda key, **_: key,
    )

    post_add_markup = first_callback.message.answer.await_args_list[0].kwargs["reply_markup"]
    first_transient_message.delete.assert_awaited_once_with()
    continue_data = ContinueShoppingCallback.unpack(
        post_add_markup.inline_keyboard[0][0].callback_data
    )
    assert (continue_data.origin, continue_data.ref_id, continue_data.page) == (
        ORIGIN_CATEGORY,
        42,
        3,
    )

    continuation_callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(photo=[], edit_text=AsyncMock()),
    )
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=None),
        get_data=AsyncMock(return_value={}),
        clear=AsyncMock(),
        update_data=AsyncMock(),
    )
    await catalog.on_continue_shopping(
        continuation_callback,
        continue_data,
        session,
        "uz",
        lambda key, **_: key,
        state,
    )
    assert send_product_list.await_args.args[1:] == (session, 42, 3)

    second_sent_message = SimpleNamespace()
    second_transient_message = SimpleNamespace(delete=AsyncMock())
    second_callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(
            answer=AsyncMock(side_effect=[second_sent_message, second_transient_message])
        ),
    )
    await catalog.on_add_to_cart(
        second_callback,
        AddToCartCallback(
            product_id=8,
            qty=1,
            origin=continue_data.origin,
            ref_id=continue_data.ref_id,
            page=continue_data.page,
        ),
        session,
        user,
        lambda key, **_: key,
    )

    assert [call.args for call in add_item.await_args_list] == [
        (session, 3, 7, 4),
        (session, 3, 8, 1),
    ]
    assert add_item.await_count == 2
    second_transient_message.delete.assert_awaited_once_with()


def test_product_detail_has_no_direct_cart_navigation_before_adding() -> None:
    keyboard = product_detail_keyboard(
        product_id=7,
        origin="cat",
        ref_id=2,
        page=3,
        qty=1,
        in_stock=True,
        is_favorite=False,
        back_callback_data="back",
        translator=lambda key, **_: key,
    )

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert all(
        button.callback_data is None
        or CartActionCallback.unpack(button.callback_data).action != "open"
        for button in buttons
        if button.callback_data and button.callback_data.startswith("cart:")
    )


async def test_continue_shopping_restores_category_page_and_clears_checkout_state(
    monkeypatch,
) -> None:
    callback = SimpleNamespace(
        answer=AsyncMock(), message=SimpleNamespace(photo=[], edit_text=AsyncMock())
    )
    state = SimpleNamespace(
        get_state=AsyncMock(return_value="checkout:entering_name"),
        get_data=AsyncMock(return_value={}),
        clear=AsyncMock(),
        update_data=AsyncMock(),
    )
    session = SimpleNamespace()
    send_product_list = AsyncMock()
    send_categories = AsyncMock()
    monkeypatch.setattr(
        catalog.catalog_service,
        "get_category",
        AsyncMock(return_value=SimpleNamespace(id=42)),
    )
    monkeypatch.setattr(catalog, "send_product_list", send_product_list)
    monkeypatch.setattr(catalog, "send_category_level", send_categories)
    add_item = AsyncMock()
    monkeypatch.setattr(catalog.cart_service, "add_item", add_item)

    await catalog.on_continue_shopping(
        callback,
        ContinueShoppingCallback(origin=ORIGIN_CATEGORY, ref_id=42, page=3),
        session,
        "uz",
        lambda key, **_: key,
        state,
    )

    callback.answer.assert_awaited_once_with()
    state.clear.assert_awaited_once_with()
    send_product_list.assert_awaited_once()
    assert send_product_list.await_args.args[1:] == (session, 42, 3)
    send_categories.assert_not_awaited()
    add_item.assert_not_awaited()


async def test_continue_shopping_restores_search_query_and_page(monkeypatch) -> None:
    callback = SimpleNamespace(
        answer=AsyncMock(), message=SimpleNamespace(photo=[], edit_text=AsyncMock())
    )
    state = SimpleNamespace(
        get_state=AsyncMock(return_value="checkout:entering_name"),
        get_data=AsyncMock(return_value={"search_query": "Deli"}),
        clear=AsyncMock(),
        update_data=AsyncMock(),
    )
    result = SimpleNamespace(items=[SimpleNamespace(id=5)], total=1)
    search = AsyncMock(return_value=result)
    keyboard = object()
    send_categories = AsyncMock()
    monkeypatch.setattr(catalog.catalog_service, "search_products", search)
    monkeypatch.setattr(catalog, "search_results_keyboard", lambda *a, **k: keyboard)
    monkeypatch.setattr(catalog, "send_category_level", send_categories)

    await catalog.on_continue_shopping(
        callback,
        ContinueShoppingCallback(origin=ORIGIN_SEARCH, ref_id=0, page=2),
        SimpleNamespace(),
        "uz",
        lambda key, **_: key,
        state,
    )

    search.assert_awaited_once()
    assert search.await_args.args[1] == "Deli"
    assert search.await_args.kwargs["page"] == 2
    state.clear.assert_awaited_once_with()
    state.update_data.assert_awaited_once_with(search_query="Deli")
    callback.message.edit_text.assert_awaited_once()
    assert callback.message.edit_text.await_args.kwargs["reply_markup"] is keyboard
    send_categories.assert_not_awaited()


async def test_continue_shopping_falls_back_to_root_without_search_context(
    monkeypatch,
) -> None:
    callback = SimpleNamespace(
        answer=AsyncMock(), message=SimpleNamespace(photo=[], edit_text=AsyncMock())
    )
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=None),
        get_data=AsyncMock(return_value={}),
        clear=AsyncMock(),
        update_data=AsyncMock(),
    )
    search = AsyncMock()
    send_categories = AsyncMock()
    monkeypatch.setattr(catalog.catalog_service, "search_products", search)
    monkeypatch.setattr(catalog, "send_category_level", send_categories)

    await catalog.on_continue_shopping(
        callback,
        ContinueShoppingCallback(origin=ORIGIN_SEARCH, ref_id=0, page=2),
        SimpleNamespace(),
        "uz",
        lambda key, **_: key,
        state,
    )

    search.assert_not_awaited()
    send_categories.assert_awaited_once()
    assert send_categories.await_args.args[2] == ROOT_CATEGORY_ID


async def test_continue_shopping_falls_back_to_root_if_category_disappeared(
    monkeypatch,
) -> None:
    callback = SimpleNamespace(
        answer=AsyncMock(), message=SimpleNamespace(photo=[], edit_text=AsyncMock())
    )
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=None),
        get_data=AsyncMock(return_value={}),
        clear=AsyncMock(),
        update_data=AsyncMock(),
    )
    monkeypatch.setattr(
        catalog.catalog_service,
        "get_category",
        AsyncMock(side_effect=CategoryNotFoundError("missing")),
    )
    send_categories = AsyncMock()
    send_products = AsyncMock()
    monkeypatch.setattr(catalog, "send_category_level", send_categories)
    monkeypatch.setattr(catalog, "send_product_list", send_products)

    await catalog.on_continue_shopping(
        callback,
        ContinueShoppingCallback(origin=ORIGIN_CATEGORY, ref_id=42, page=3),
        SimpleNamespace(),
        "uz",
        lambda key, **_: key,
        state,
    )

    send_categories.assert_awaited_once()
    assert send_categories.await_args.args[2] == ROOT_CATEGORY_ID
    send_products.assert_not_awaited()


async def test_empty_or_stale_category_page_keeps_parent_navigation(monkeypatch) -> None:
    category = SimpleNamespace(id=42, name_uz="Pens", name_ru="Ручки", parent_id=None)
    result = SimpleNamespace(items=[], total=0, page=3, limit=8)
    monkeypatch.setattr(
        catalog.catalog_service, "get_category", AsyncMock(return_value=category)
    )
    monkeypatch.setattr(
        catalog.catalog_service, "list_products", AsyncMock(return_value=result)
    )
    send = AsyncMock()

    await catalog.send_product_list(
        send,
        SimpleNamespace(),
        42,
        3,
        lang="uz",
        translator=lambda key, **_: key,
    )

    send.assert_awaited_once()
    assert send.await_args.args == ("catalog.empty_category",)
    markup = send.await_args.kwargs["reply_markup"]
    button = next(button for row in markup.inline_keyboard for button in row)
    assert CategoryCallback.unpack(button.callback_data).category_id == ROOT_CATEGORY_ID


async def test_callback_ack_does_not_suppress_unexpected_bad_request() -> None:
    callback = SimpleNamespace(
        answer=AsyncMock(side_effect=_bad_request("message is not modified"))
    )

    try:
        await answer_callback_safely(callback)
    except TelegramBadRequest as error:
        assert "message is not modified" in error.message
    else:
        raise AssertionError("unexpected TelegramBadRequest was suppressed")


async def test_editing_text_message_to_product_photo_replaces_message() -> None:
    sent_photo = SimpleNamespace(photo=[SimpleNamespace(file_id="photo-1")])
    message = SimpleNamespace(
        photo=[],
        answer_photo=AsyncMock(return_value=sent_photo),
        delete=AsyncMock(),
        edit_text=AsyncMock(),
    )
    keyboard = object()

    result = await edit_or_send_message(
        message, "product details", reply_markup=keyboard, photo="photo-1"
    )

    assert result is sent_photo
    message.answer_photo.assert_awaited_once_with(
        photo="photo-1", caption="product details", reply_markup=keyboard
    )
    message.delete.assert_awaited_once()
    message.edit_text.assert_not_awaited()


async def test_repainting_same_product_photo_only_edits_caption() -> None:
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="photo-1")],
        edit_caption=AsyncMock(return_value="edited"),
        edit_media=AsyncMock(),
        answer=AsyncMock(),
        delete=AsyncMock(),
    )

    result = await edit_or_send_message(
        message, "new quantity", reply_markup="keyboard", photo="photo-1"
    )

    assert result == "edited"
    message.edit_caption.assert_awaited_once_with(
        caption="new quantity", reply_markup="keyboard"
    )
    message.edit_media.assert_not_awaited()
    message.answer.assert_not_awaited()


async def test_identical_product_caption_is_safe_when_telegram_rejects_noop_edit() -> None:
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="photo-1")],
        edit_caption=AsyncMock(
            side_effect=TelegramBadRequest(
                method=SimpleNamespace(), message="message is not modified"
            )
        ),
        edit_media=AsyncMock(),
        answer=AsyncMock(),
        delete=AsyncMock(),
    )

    result = await edit_or_send_message(
        message, "same caption", reply_markup="same keyboard", photo="photo-1"
    )

    assert result is message
    message.edit_caption.assert_awaited_once_with(
        caption="same caption", reply_markup="same keyboard"
    )
    message.edit_media.assert_not_awaited()


async def test_quantity_refresh_keeps_url_backed_product_photo_in_place() -> None:
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="telegram-cached-file-id")],
        edit_caption=AsyncMock(return_value="edited"),
        edit_media=AsyncMock(),
        answer=AsyncMock(),
        delete=AsyncMock(),
    )

    await edit_or_send_message(
        message,
        "new quantity",
        reply_markup="keyboard",
        photo="https://example.test/product.jpg",
        preserve_photo=True,
    )

    message.edit_caption.assert_awaited_once_with(
        caption="new quantity", reply_markup="keyboard"
    )
    message.edit_media.assert_not_awaited()
    message.answer.assert_not_awaited()


async def test_switching_product_photo_edits_media() -> None:
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="photo-1")],
        edit_caption=AsyncMock(),
        edit_media=AsyncMock(return_value="edited"),
        answer=AsyncMock(),
        delete=AsyncMock(),
    )

    result = await edit_or_send_message(
        message, "other product", reply_markup="keyboard", photo="photo-2"
    )

    assert result == "edited"
    message.edit_media.assert_awaited_once()
    media = message.edit_media.await_args.kwargs["media"]
    assert media.media == "photo-2"
    assert media.caption == "other product"
    message.edit_caption.assert_not_awaited()
    message.answer.assert_not_awaited()


async def test_returning_from_product_photo_to_text_replaces_message() -> None:
    sent_message = SimpleNamespace(photo=[])
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="photo-1")],
        answer=AsyncMock(return_value=sent_message),
        edit_caption=AsyncMock(),
        edit_text=AsyncMock(),
        delete=AsyncMock(),
    )

    result = await edit_or_send_message(message, "category list", reply_markup="keyboard")

    assert result is sent_message
    message.answer.assert_awaited_once_with("category list", reply_markup="keyboard")
    message.delete.assert_awaited_once()
    message.edit_text.assert_not_awaited()
    message.edit_caption.assert_not_awaited()


async def test_sourcing_product_detail_hides_stock_and_uses_minimum_one(
    monkeypatch,
) -> None:
    image = SimpleNamespace(
        is_main=True,
        sort_order=0,
        telegram_file_id="telegram-photo",
        url="https://example.test/product.jpg",
    )
    product = SimpleNamespace(
        id=7,
        name_uz="Pencil",
        name_ru="Карандаш",
        description_uz="Description",
        description_ru="Описание",
        price=Decimal("1200"),
        unit=SimpleNamespace(value="dona"),
        stock_qty=3,
        min_order_qty=48,
        images=[image],
    )
    monkeypatch.setattr(
        catalog.catalog_service, "get_product", AsyncMock(return_value=product)
    )
    monkeypatch.setattr(catalog.favorite_service, "is_favorite", AsyncMock(return_value=False))
    monkeypatch.setattr(
        catalog, "get_inventory_policy", AsyncMock(return_value=InventoryPolicy(False))
    )
    send = AsyncMock()

    await catalog.send_product_detail(
        send,
        SimpleNamespace(),
        7,
        user_id=3,
        origin="category",
        ref_id=2,
        page=1,
        back_callback_data="back",
        lang="uz",
        translator=lambda key, **values: f"{key} {values}",
    )

    send.assert_awaited_once()
    text = send.await_args.args[0]
    assert "catalog.product_card_sourcing" in text
    assert "stock" not in text.casefold()
    assert send.await_args.kwargs["photo"] == "telegram-photo"
    keyboard = send.await_args.kwargs["reply_markup"]
    button_data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    add_data = next(value for value in button_data if value and value.startswith("addcart:"))
    assert AddToCartCallback.unpack(add_data).qty == 1
    assert all(not value or not value.startswith("cart:") for value in button_data)


async def test_product_photo_caption_drops_only_long_description(monkeypatch) -> None:
    product = SimpleNamespace(
        id=8,
        name_uz="Name <&>",
        name_ru="Название",
        description_uz="D" * 1400,
        description_ru="D" * 1400,
        price=Decimal("1000"),
        unit=SimpleNamespace(value="dona"),
        stock_qty=20,
        min_order_qty=1,
        images=[
            SimpleNamespace(is_main=True, sort_order=0, telegram_file_id="photo-id", url=None)
        ],
    )
    monkeypatch.setattr(
        catalog.catalog_service, "get_product", AsyncMock(return_value=product)
    )
    monkeypatch.setattr(catalog.favorite_service, "is_favorite", AsyncMock(return_value=False))
    monkeypatch.setattr(
        catalog, "get_inventory_policy", AsyncMock(return_value=InventoryPolicy(False))
    )
    send = AsyncMock()

    await catalog.send_product_detail(
        send,
        SimpleNamespace(),
        8,
        user_id=3,
        origin="category",
        ref_id=2,
        page=1,
        back_callback_data="back",
        lang="uz",
        translator=lambda key, **values: f"{key} {values}",
    )

    caption = send.await_args.args[0]
    assert "product_card_no_description_sourcing" in caption
    assert "D" * 100 not in caption
    assert "Name &lt;&amp;&gt;" in caption
    assert send.await_args.kwargs["photo"] == "photo-id"


async def test_product_photo_bad_request_falls_back_to_text(monkeypatch) -> None:
    product = SimpleNamespace(
        id=9,
        name_uz="Name",
        name_ru="Имя",
        description_uz="Description",
        description_ru="Описание",
        price=Decimal("1000"),
        unit=SimpleNamespace(value="dona"),
        stock_qty=0,
        min_order_qty=1,
        images=[
            SimpleNamespace(
                is_main=True,
                sort_order=0,
                telegram_file_id=None,
                url="https://example.test/missing.jpg",
            )
        ],
    )
    monkeypatch.setattr(
        catalog.catalog_service, "get_product", AsyncMock(return_value=product)
    )
    monkeypatch.setattr(catalog.favorite_service, "is_favorite", AsyncMock(return_value=False))
    monkeypatch.setattr(
        catalog, "get_inventory_policy", AsyncMock(return_value=InventoryPolicy(False))
    )
    send = AsyncMock(
        side_effect=[
            TelegramBadRequest(
                method=SimpleNamespace(), message="failed to get HTTP URL content"
            ),
            "text fallback",
        ]
    )

    await catalog.send_product_detail(
        send,
        SimpleNamespace(),
        9,
        user_id=3,
        origin="category",
        ref_id=2,
        page=1,
        back_callback_data="back",
        lang="uz",
        translator=lambda key, **values: f"{key} {values}",
    )

    assert send.await_count == 2
    assert send.await_args_list[0].kwargs["photo"] == "https://example.test/missing.jpg"
    assert "photo" not in send.await_args_list[1].kwargs

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest

from app.bot.handlers.user import (
    cart as cart_handler,
)
from app.bot.handlers.user import (
    catalog,
)
from app.bot.handlers.user import (
    menu as menu_handler,
)
from app.bot.handlers.user import (
    start as start_handler,
)
from app.bot.keyboards.callback_data import AddToCartCallback, CartActionCallback, MenuCallback
from app.bot.keyboards.inline.catalog import product_detail_keyboard
from app.bot.keyboards.reply.menu import browse_cart_keyboard
from app.bot.utils.messages import answer_callback_safely, edit_or_send_message
from app.core.exceptions import OutOfStockError
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
    message.answer.assert_awaited_once_with("cart.out_of_stock_alert")


async def test_successful_add_feedback_has_one_inline_open_cart_button(monkeypatch) -> None:
    callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(
            photo=[SimpleNamespace(file_id="photo-1")], answer=AsyncMock()
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
    feedback = callback.message.answer.await_args
    assert feedback.args == ("cart.added_alert",)
    assert feedback.kwargs["reply_markup"] is not None
    buttons = [
        button for row in feedback.kwargs["reply_markup"].inline_keyboard for button in row
    ]
    cart_button = next(
        button for button in buttons if button.callback_data.startswith("cart:")
    )
    assert CartActionCallback.unpack(cart_button.callback_data).action == "open"


async def test_start_installs_persistent_cart_keyboard_for_returning_customer() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    user = SimpleNamespace(first_name="Buyer")

    await start_handler.cmd_start(
        message,
        SimpleNamespace(args=None),
        SimpleNamespace(),
        user,
        False,
        "uz",
        lambda key, **_: key,
        SimpleNamespace(get_state=AsyncMock(return_value=None)),
        None,
        SimpleNamespace(),
    )

    welcome_markup = message.answer.await_args_list[0].kwargs["reply_markup"]
    assert welcome_markup.is_persistent is True
    assert welcome_markup.keyboard[0][0].text == "menu.cart"


async def test_start_does_not_restore_browse_keyboard_inside_active_fsm() -> None:
    message = SimpleNamespace(answer=AsyncMock())

    await start_handler.cmd_start(
        message,
        SimpleNamespace(args=None),
        SimpleNamespace(),
        SimpleNamespace(first_name="Buyer"),
        False,
        "uz",
        lambda key, **_: key,
        SimpleNamespace(get_state=AsyncMock(return_value="checkout:entering_name")),
        None,
        SimpleNamespace(),
    )

    assert "reply_markup" not in message.answer.await_args_list[0].kwargs


async def test_catalog_menu_entry_installs_keyboard_once_before_browsing(monkeypatch) -> None:
    message = SimpleNamespace(answer=AsyncMock())
    callback = SimpleNamespace(answer=AsyncMock(), message=message)
    state = SimpleNamespace(clear=AsyncMock())
    send_categories = AsyncMock()
    monkeypatch.setattr(menu_handler, "send_category_level", send_categories)

    await menu_handler.on_menu_action(
        callback,
        MenuCallback(action="catalog"),
        SimpleNamespace(),
        SimpleNamespace(id=3),
        None,
        state,
        "uz",
        lambda key, **_: key,
    )

    assert message.answer.await_count == 1
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    assert keyboard.is_persistent is True
    send_categories.assert_awaited_once()
    state.clear.assert_awaited_once()


async def test_product_card_cart_action_replaces_photo_with_cart_view(monkeypatch) -> None:
    message = SimpleNamespace(
        photo=[SimpleNamespace(file_id="product-photo")],
        answer=AsyncMock(return_value=SimpleNamespace(photo=[])),
        delete=AsyncMock(),
        edit_text=AsyncMock(),
    )
    callback = SimpleNamespace(answer=AsyncMock(), message=message)
    state = SimpleNamespace(clear=AsyncMock())
    monkeypatch.setattr(
        cart_handler.cart_service,
        "get_cart",
        AsyncMock(return_value=SimpleNamespace(items=[])),
    )
    add_item = AsyncMock()
    monkeypatch.setattr(cart_handler.cart_service, "add_item", add_item)

    await cart_handler.on_open_cart_from_catalog(
        callback,
        SimpleNamespace(),
        SimpleNamespace(id=3),
        state,
        "uz",
        lambda key, **_: key,
    )

    callback.answer.assert_awaited_once_with()
    state.clear.assert_awaited_once_with()
    add_item.assert_not_awaited()
    message.answer.assert_awaited_once()
    assert message.answer.await_args.args == ("cart.empty",)
    message.delete.assert_awaited_once_with()
    message.edit_text.assert_not_awaited()


def test_product_detail_keyboard_includes_quick_open_cart_button() -> None:
    keyboard = product_detail_keyboard(
        product_id=7,
        origin="cat",
        ref_id=2,
        page=1,
        qty=1,
        in_stock=True,
        is_favorite=False,
        back_callback_data="back",
        translator=lambda key, **_: key,
    )

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    cart_button = next(
        button for button in buttons if button.callback_data.startswith("cart:")
    )
    assert CartActionCallback.unpack(cart_button.callback_data).action == "open"


def test_browse_cart_reply_keyboard_is_persistent_and_uses_localized_label() -> None:
    keyboard = browse_cart_keyboard(lambda key, **_: f"uz:{key}")

    assert keyboard.is_persistent is True
    assert keyboard.resize_keyboard is True
    assert keyboard.keyboard[0][0].text == "uz:menu.cart"


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
    cart_data = next(value for value in button_data if value and value.startswith("cart:"))
    assert CartActionCallback.unpack(cart_data).action == "open"


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

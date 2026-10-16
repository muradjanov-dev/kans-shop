from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest

from app.bot.handlers.user import catalog
from app.bot.keyboards.callback_data import AddToCartCallback
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

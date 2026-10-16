from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

from app.bot.handlers.admin import menu as admin_menu_handler
from app.bot.handlers.user import cart as cart_handler
from app.bot.handlers.user import checkout as checkout_handler
from app.bot.handlers.user import menu as menu_handler
from app.bot.handlers.user import start as start_handler
from app.bot.keyboards.reply.checkout import location_request_keyboard, phone_request_keyboard
from app.bot.utils.i18n import translate
from app.bot.utils.messages import answer_with_inline_keyboard, edit_or_send_message
from app.db.models.enums import AdminRole


def _translator(key: str, **kwargs) -> str:
    return translate("uz", key, **kwargs)


def test_checkout_reply_keyboards_keep_contact_and_location_requests() -> None:
    phone = phone_request_keyboard(_translator)
    location = location_request_keyboard(_translator)

    assert phone.keyboard[0][0].request_contact is True
    assert location.keyboard[0][0].request_location is True


async def test_inline_choices_are_sent_before_best_effort_keyboard_cleanup() -> None:
    primary = SimpleNamespace()
    cleanup = SimpleNamespace(delete=AsyncMock())
    message = SimpleNamespace(answer=AsyncMock(side_effect=[primary, cleanup]))
    markup = InlineKeyboardMarkup(inline_keyboard=[])

    result = await answer_with_inline_keyboard(message, "Added", reply_markup=markup)

    assert result is primary
    assert message.answer.await_count == 2
    assert message.answer.await_args_list[0].args == ("Added",)
    assert message.answer.await_args_list[0].kwargs["reply_markup"] is markup
    assert message.answer.await_args_list[1].args == ("Added",)
    assert message.answer.await_args_list[1].kwargs["reply_markup"].__class__.__name__ == (
        "ReplyKeyboardRemove"
    )
    cleanup.delete.assert_awaited_once_with()


async def test_keyboard_removal_without_inline_choices_sends_one_visible_message() -> None:
    sent = SimpleNamespace(delete=AsyncMock())
    message = SimpleNamespace(answer=AsyncMock(return_value=sent))

    result = await answer_with_inline_keyboard(message, "Keyboard cleared")

    assert result is sent
    message.answer.assert_awaited_once()
    assert message.answer.await_args.args == ("Keyboard cleared",)
    assert message.answer.await_args.kwargs["reply_markup"].__class__.__name__ == (
        "ReplyKeyboardRemove"
    )
    sent.delete.assert_not_awaited()


async def test_keyboard_cleanup_failure_does_not_undo_successful_inline_message(
    monkeypatch,
) -> None:
    warning = Mock()
    monkeypatch.setattr("app.bot.utils.messages.logger.warning", warning)
    primary = SimpleNamespace()
    message = SimpleNamespace(
        answer=AsyncMock(
            side_effect=[
                primary,
                TelegramBadRequest(
                    method=SimpleNamespace(), message="Bad Request: private api diagnostic"
                ),
            ]
        )
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[])

    result = await answer_with_inline_keyboard(message, "Added", reply_markup=markup)

    assert result is primary
    assert message.answer.await_count == 2
    warning.assert_called_once()
    warning_call = warning.call_args
    assert "cleanup" in warning_call.args[0].casefold()
    assert warning_call.kwargs["extra"]["telegram_error_type"] == "TelegramBadRequest"
    assert "private api diagnostic" not in str(warning_call)


async def test_initial_reply_keyboard_removal_send_error_still_propagates() -> None:
    message = SimpleNamespace(
        answer=AsyncMock(
            side_effect=TelegramBadRequest(
                method=SimpleNamespace(), message="Bad Request: chat not found"
            )
        )
    )

    with pytest.raises(TelegramBadRequest, match="chat not found"):
        await answer_with_inline_keyboard(
            message, "Added", reply_markup=InlineKeyboardMarkup(inline_keyboard=[])
        )


async def test_noop_with_full_bad_request_description_is_ignored() -> None:
    message = SimpleNamespace(
        photo=[],
        edit_text=AsyncMock(
            side_effect=TelegramBadRequest(
                method=SimpleNamespace(),
                message=(
                    "Bad Request: message is not modified: text and reply markup are "
                    "exactly the same as a current content of the message"
                ),
            )
        ),
    )

    result = await edit_or_send_message(message, "same text")

    assert result is message
    message.edit_text.assert_awaited_once_with("same text", reply_markup=None)


async def test_unrelated_bad_request_still_propagates() -> None:
    message = SimpleNamespace(
        photo=[],
        edit_text=AsyncMock(
            side_effect=TelegramBadRequest(
                method=SimpleNamespace(), message="Bad Request: chat not found"
            )
        ),
    )

    with pytest.raises(TelegramBadRequest, match="chat not found"):
        await edit_or_send_message(message, "text")


async def test_start_removes_legacy_reply_keyboard() -> None:
    message = SimpleNamespace(answer=AsyncMock())

    await start_handler.cmd_start(
        message,
        SimpleNamespace(args=None),
        SimpleNamespace(),
        SimpleNamespace(first_name="Buyer"),
        False,
        "uz",
        _translator,
        SimpleNamespace(get_state=AsyncMock(return_value=None)),
        None,
        SimpleNamespace(),
    )

    assert message.answer.await_args_list[0].kwargs["reply_markup"].__class__.__name__ == (
        "ReplyKeyboardRemove"
    )
    assert message.answer.await_args_list[1].kwargs["reply_markup"].__class__.__name__ == (
        "InlineKeyboardMarkup"
    )


async def test_start_preserves_checkout_reply_keyboard_inside_active_fsm() -> None:
    message = SimpleNamespace(answer=AsyncMock())

    await start_handler.cmd_start(
        message,
        SimpleNamespace(args=None),
        SimpleNamespace(),
        SimpleNamespace(first_name="Buyer"),
        False,
        "uz",
        _translator,
        SimpleNamespace(get_state=AsyncMock(return_value="checkout:entering_phone")),
        None,
        SimpleNamespace(),
    )

    assert "reply_markup" not in message.answer.await_args_list[0].kwargs


async def test_menu_command_removes_reply_keyboard_on_inline_menu_message() -> None:
    primary = SimpleNamespace()
    cleanup = SimpleNamespace(delete=AsyncMock())
    message = SimpleNamespace(answer=AsyncMock(side_effect=[primary, cleanup]))
    state = SimpleNamespace(clear=AsyncMock())

    await menu_handler.cmd_menu(message, None, _translator, state)

    state.clear.assert_awaited_once_with()
    assert message.answer.await_count == 2
    assert message.answer.await_args_list[0].args == (_translator("menu.choose_action"),)
    assert message.answer.await_args_list[0].kwargs["reply_markup"].__class__.__name__ == (
        "InlineKeyboardMarkup"
    )
    assert message.answer.await_args_list[1].kwargs["reply_markup"].__class__.__name__ == (
        "ReplyKeyboardRemove"
    )
    cleanup.delete.assert_awaited_once_with()


async def test_legacy_cart_reply_clears_fsm_and_keyboard_without_mutating_cart(
    monkeypatch,
) -> None:
    events = []
    primary = SimpleNamespace()
    cleanup = SimpleNamespace(delete=AsyncMock())
    message = SimpleNamespace(answer=AsyncMock(side_effect=[primary, cleanup]))

    async def clear_state() -> None:
        events.append("clear")

    async def get_cart(*_args):
        events.append("get_cart")
        return SimpleNamespace(items=[])

    monkeypatch.setattr(cart_handler.cart_service, "get_cart", get_cart)
    add_item = AsyncMock()
    monkeypatch.setattr(cart_handler.cart_service, "add_item", add_item)

    await cart_handler.open_cart(
        message,
        SimpleNamespace(),
        SimpleNamespace(id=9),
        SimpleNamespace(clear=clear_state),
        "uz",
        _translator,
    )

    assert events == ["clear", "get_cart"]
    assert message.answer.await_count == 2
    assert message.answer.await_args_list[0].args == (_translator("cart.empty"),)
    assert message.answer.await_args_list[0].kwargs["reply_markup"].__class__.__name__ == (
        "InlineKeyboardMarkup"
    )
    assert message.answer.await_args_list[1].kwargs["reply_markup"].__class__.__name__ == (
        "ReplyKeyboardRemove"
    )
    cleanup.delete.assert_awaited_once_with()
    add_item.assert_not_awaited()


async def test_checkout_entry_hides_legacy_keyboard_before_order_fields(monkeypatch) -> None:
    message = SimpleNamespace(answer=AsyncMock())
    callback = SimpleNamespace(answer=AsyncMock(), message=message)
    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
    monkeypatch.setattr(
        checkout_handler.cart_service,
        "get_cart",
        AsyncMock(return_value=SimpleNamespace(items=[object()])),
    )

    await checkout_handler.start_checkout(
        callback,
        SimpleNamespace(),
        SimpleNamespace(id=4),
        state,
        _translator,
    )

    assert message.answer.await_args_list[0].args == (_translator("checkout.starting"),)
    assert message.answer.await_args_list[0].kwargs["reply_markup"].__class__.__name__ == (
        "ReplyKeyboardRemove"
    )
    assert message.answer.await_args_list[1].args == (_translator("checkout.choose_type"),)


async def test_stale_checkout_callback_does_not_read_cart_or_start_fsm(monkeypatch) -> None:
    message = SimpleNamespace(answer=AsyncMock())
    callback = SimpleNamespace(
        answer=AsyncMock(
            side_effect=TelegramBadRequest(
                method=SimpleNamespace(),
                message="query is too old and response timeout expired",
            )
        ),
        message=message,
    )
    get_cart = AsyncMock()
    monkeypatch.setattr(checkout_handler.cart_service, "get_cart", get_cart)
    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())

    await checkout_handler.start_checkout(
        callback, SimpleNamespace(), SimpleNamespace(id=4), state, _translator
    )

    get_cart.assert_not_awaited()
    state.set_state.assert_not_awaited()
    state.update_data.assert_not_awaited()
    message.answer.assert_not_awaited()


async def test_fresh_checkout_callback_is_acknowledged_before_cart_read(monkeypatch) -> None:
    calls = []

    async def answer(*_args, **_kwargs):
        calls.append("ack")

    async def get_cart(*_args):
        calls.append("cart")
        return SimpleNamespace(items=[object()])

    message = SimpleNamespace(answer=AsyncMock())
    callback = SimpleNamespace(answer=answer, message=message)
    monkeypatch.setattr(checkout_handler.cart_service, "get_cart", get_cart)
    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())

    await checkout_handler.start_checkout(
        callback, SimpleNamespace(), SimpleNamespace(id=4), state, _translator
    )

    assert calls[:2] == ["ack", "cart"]


async def test_empty_cart_checkout_shows_message_without_second_callback_ack(
    monkeypatch,
) -> None:
    message = SimpleNamespace(answer=AsyncMock())
    callback = SimpleNamespace(answer=AsyncMock(), message=message)
    monkeypatch.setattr(
        checkout_handler.cart_service,
        "get_cart",
        AsyncMock(return_value=SimpleNamespace(items=[])),
    )
    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())

    await checkout_handler.start_checkout(
        callback, SimpleNamespace(), SimpleNamespace(id=4), state, _translator
    )

    callback.answer.assert_awaited_once_with()
    message.answer.assert_awaited_once_with(_translator("checkout.cart_empty"))
    state.set_state.assert_not_awaited()


async def test_checkout_cancel_does_not_restore_a_reply_keyboard() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock())

    await checkout_handler._cancel_checkout(message, state, _translator)

    state.clear.assert_awaited_once_with()
    assert message.answer.await_args_list[0].kwargs["reply_markup"].__class__.__name__ == (
        "ReplyKeyboardRemove"
    )
    assert message.answer.await_args_list[1].kwargs["reply_markup"].__class__.__name__ == (
        "InlineKeyboardMarkup"
    )


async def test_admin_entry_removes_old_customer_reply_keyboard(monkeypatch) -> None:
    sent = []

    async def send(text, reply_markup=None):
        sent.append((text, reply_markup))

    # A live authorized admin avoids the denial path while keeping this test DB-free.
    monkeypatch.setattr(admin_menu_handler, "_new_orders_count", AsyncMock(return_value=0))
    await admin_menu_handler.render_admin_menu(
        send,
        SimpleNamespace(),
        SimpleNamespace(is_active=True, role=AdminRole.MANAGER),
        translator=_translator,
        reset_browse_keyboard=True,
    )

    assert sent[0][1].__class__.__name__ == "ReplyKeyboardRemove"
    assert sent[1][0] == _translator("menu.choose_action")

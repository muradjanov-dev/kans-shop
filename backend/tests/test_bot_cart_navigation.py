from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest

from app.bot.handlers.admin import menu as admin_menu_handler
from app.bot.handlers.user import (
    cart as cart_handler,
)
from app.bot.handlers.user import (
    checkout as checkout_handler,
)
from app.bot.handlers.user import (
    menu as menu_handler,
)
from app.bot.keyboards.callback_data import MenuCallback
from app.bot.keyboards.reply.checkout import location_request_keyboard, phone_request_keyboard
from app.bot.keyboards.reply.menu import browse_cart_keyboard
from app.bot.utils.i18n import menu_button_texts, translate
from app.db.models.enums import AdminRole


def test_persistent_cart_button_has_localized_text_supported_by_existing_handler() -> None:
    keyboard = browse_cart_keyboard(lambda key, **kwargs: translate("uz", key, **kwargs))

    assert keyboard.is_persistent is True
    assert keyboard.resize_keyboard is True
    assert keyboard.keyboard[0][0].text == translate("uz", "menu.cart")
    assert {keyboard.keyboard[0][0].text, translate("ru", "menu.cart")} == menu_button_texts(
        "menu.cart"
    )


def test_checkout_reply_keyboards_keep_contact_and_location_requests() -> None:
    def translator(key, **kwargs):
        return translate("uz", key, **kwargs)

    phone = phone_request_keyboard(translator)
    location = location_request_keyboard(translator)

    assert phone.keyboard[0][0].request_contact is True
    assert location.keyboard[0][0].request_location is True
    assert all(
        button.text != translate("uz", "menu.cart") for row in phone.keyboard for button in row
    )
    assert all(
        button.text != translate("uz", "menu.cart")
        for row in location.keyboard
        for button in row
    )


def test_manager_role_label_matches_admin_wording_in_both_languages() -> None:
    assert translate("uz", "admin.role_manager") == "👔 Admin"
    assert translate("ru", "admin.role_manager") == "👔 Администратор"


async def test_checkout_entry_hides_browse_cart_keyboard_before_order_fields(
    monkeypatch,
) -> None:
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
        lambda key, **_: key,
    )

    first = message.answer.await_args_list[0]
    reply_markup = first.kwargs["reply_markup"]
    assert reply_markup.__class__.__name__ == "ReplyKeyboardRemove"
    assert first.args == ("checkout.starting",)
    assert message.answer.await_args_list[1].args == ("checkout.choose_type",)


async def test_menu_command_clears_checkout_state_and_restores_cart_keyboard() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock())

    await menu_handler.cmd_menu(
        message,
        None,
        lambda key, **_: key,
        state,
    )

    state.clear.assert_awaited_once_with()
    persistent_markups = [
        call.kwargs["reply_markup"]
        for call in message.answer.await_args_list
        if getattr(call.kwargs.get("reply_markup"), "is_persistent", False)
    ]
    assert len(persistent_markups) == 1
    assert persistent_markups[0].keyboard[0][0].text == "menu.cart"


async def test_cart_reply_shortcut_clears_checkout_state_before_loading_cart(
    monkeypatch,
) -> None:
    calls = []

    async def clear():
        calls.append("clear")

    async def get_cart(*_args):
        calls.append("cart")
        return SimpleNamespace(items=[])

    message = SimpleNamespace(answer=AsyncMock())
    monkeypatch.setattr(cart_handler.cart_service, "get_cart", get_cart)

    await cart_handler.open_cart(
        message,
        SimpleNamespace(),
        SimpleNamespace(id=4),
        SimpleNamespace(clear=clear),
        "uz",
        lambda key, **_: key,
    )

    assert calls == ["clear", "cart"]
    message.answer.assert_awaited_once()


async def test_admin_menu_entry_removes_cart_keyboard_before_inline_admin_menu(
    monkeypatch,
) -> None:
    sent = []

    async def send(text, reply_markup=None):
        sent.append((text, reply_markup))

    monkeypatch.setattr(admin_menu_handler, "_new_orders_count", AsyncMock(return_value=2))
    admin = SimpleNamespace(is_active=True, role=AdminRole.MANAGER)

    await admin_menu_handler.render_admin_menu(
        send,
        SimpleNamespace(),
        admin,
        translator=lambda key, **_: key,
        reset_browse_keyboard=True,
    )

    assert sent[0][0] == "admin.menu_title"
    assert sent[0][1].__class__.__name__ == "ReplyKeyboardRemove"
    assert sent[1][0] == "menu.choose_action"
    assert sent[1][1].__class__.__name__ == "InlineKeyboardMarkup"


async def test_direct_admin_command_guards_then_clears_state_and_resets_keyboard(
    monkeypatch,
) -> None:
    calls = []

    async def require_admin(*_args, **_kwargs):
        calls.append("guard")
        return True

    async def render_admin_menu(*_args, **kwargs):
        calls.append(("render", kwargs.get("reset_browse_keyboard")))

    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock(side_effect=lambda: calls.append("clear")))
    admin = SimpleNamespace(is_active=True)
    monkeypatch.setattr(admin_menu_handler, "require_admin", require_admin)
    monkeypatch.setattr(admin_menu_handler, "render_admin_menu", render_admin_menu)

    await admin_menu_handler.cmd_admin(
        message,
        SimpleNamespace(),
        admin,
        lambda key, **_: key,
        state,
    )

    assert calls == ["guard", "clear", ("render", True)]


async def test_user_menu_admin_action_checks_role_before_clearing_checkout(
    monkeypatch,
) -> None:
    callback = SimpleNamespace(answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))
    state = SimpleNamespace(clear=AsyncMock())
    render_admin = AsyncMock()
    monkeypatch.setattr(admin_menu_handler, "render_admin_menu", render_admin)

    await menu_handler.on_menu_action(
        callback,
        MenuCallback(action="admin"),
        SimpleNamespace(),
        SimpleNamespace(id=4),
        None,
        state,
        "uz",
        lambda key, **_: key,
    )

    state.clear.assert_not_awaited()
    render_admin.assert_not_awaited()


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
        callback,
        SimpleNamespace(),
        SimpleNamespace(id=4),
        state,
        lambda key, **_: key,
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
        callback,
        SimpleNamespace(),
        SimpleNamespace(id=4),
        state,
        lambda key, **_: key,
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
        callback,
        SimpleNamespace(),
        SimpleNamespace(id=4),
        state,
        lambda key, **_: key,
    )

    callback.answer.assert_awaited_once_with()
    message.answer.assert_awaited_once_with("checkout.cart_empty")
    state.set_state.assert_not_awaited()

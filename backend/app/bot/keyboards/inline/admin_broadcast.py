from collections.abc import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import (
    BroadcastButtonChoiceCallback,
    BroadcastConfirmCallback,
    BroadcastTargetCallback,
)
from app.bot.keyboards.inline.admin_common import cancel_button


def broadcast_button_choice_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.broadcast_yes"),
            callback_data=BroadcastButtonChoiceCallback(add_button=True).pack(),
        ),
        InlineKeyboardButton(
            text=translator("admin.broadcast_no"),
            callback_data=BroadcastButtonChoiceCallback(add_button=False).pack(),
        ),
    )
    builder.row(cancel_button(translator))
    return builder.as_markup()


def broadcast_target_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.broadcast_target_all"),
            callback_data=BroadcastTargetCallback(target="all").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.broadcast_target_active"),
            callback_data=BroadcastTargetCallback(target="active").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.broadcast_target_buyers"),
            callback_data=BroadcastTargetCallback(target="buyers").pack(),
        )
    )
    builder.row(cancel_button(translator))
    return builder.as_markup()


def broadcast_confirm_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.broadcast_confirm_send"),
            callback_data=BroadcastConfirmCallback(action="send").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.broadcast_cancel_button"),
            callback_data=BroadcastConfirmCallback(action="cancel").pack(),
        )
    )
    return builder.as_markup()


def broadcast_content_button(
    button_text: str | None, button_url: str | None
) -> InlineKeyboardMarkup | None:
    if not button_text or not button_url:
        return None
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=button_text, url=button_url))
    return builder.as_markup()

from collections.abc import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import CheckSubscriptionCallback


def subscription_gate_keyboard(
    translator: Callable[..., str], *, channel_url: str | None
) -> InlineKeyboardMarkup:
    """Join button (omitted when no link could be resolved — the check button still works
    for a user who reaches the channel some other way) plus the re-check button."""
    builder = InlineKeyboardBuilder()
    if channel_url:
        builder.row(
            InlineKeyboardButton(text=translator("subscription.join_button"), url=channel_url)
        )
    builder.row(
        InlineKeyboardButton(
            text=translator("subscription.check_button"),
            callback_data=CheckSubscriptionCallback().pack(),
        )
    )
    return builder.as_markup()

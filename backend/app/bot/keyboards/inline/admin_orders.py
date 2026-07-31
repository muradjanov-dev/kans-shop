from collections.abc import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import (
    AdminBackToOrderCallback,
    AdminCancelReasonCallback,
    AdminWriteViaBotCallback,
)

CANCEL_REASONS = ("out_of_stock", "no_response", "rejected", "other")


def cancel_reason_keyboard(
    order_id: int, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for reason in CANCEL_REASONS:
        builder.row(
            InlineKeyboardButton(
                text=translator(f"admin.cancel_reason_{reason}"),
                callback_data=AdminCancelReasonCallback(
                    order_id=order_id, reason=reason
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.back_button"),
            callback_data=AdminBackToOrderCallback(order_id=order_id).pack(),
        )
    )
    return builder.as_markup()


def message_customer_keyboard(
    order_id: int,
    customer_telegram_id: int,
    customer_username: str | None,
    translator: Callable[..., str],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    url = (
        f"https://t.me/{customer_username}"
        if customer_username
        else f"tg://user?id={customer_telegram_id}"
    )
    builder.row(InlineKeyboardButton(text=translator("admin.open_chat_button"), url=url))
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.write_via_bot_button"),
            callback_data=AdminWriteViaBotCallback(order_id=order_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.back_button"),
            callback_data=AdminBackToOrderCallback(order_id=order_id).pack(),
        )
    )
    return builder.as_markup()


def back_to_order_keyboard(
    order_id: int, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.back_button"),
            callback_data=AdminBackToOrderCallback(order_id=order_id).pack(),
        )
    )
    return builder.as_markup()

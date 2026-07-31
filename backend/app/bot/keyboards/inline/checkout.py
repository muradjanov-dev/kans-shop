from collections.abc import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import (
    CheckoutNavCallback,
    OrderTypeCallback,
    PaymentMethodCallback,
    SkipStepCallback,
    UseDefaultNameCallback,
)
from app.db.models.enums import OrderType, PaymentMethod


def _nav_row(
    translator: Callable[..., str],
    *,
    show_back: bool,
    show_skip: bool = False,
    skip_step: str = "",
) -> list[InlineKeyboardButton]:
    row = []
    if show_back:
        row.append(
            InlineKeyboardButton(
                text=translator("common.back"),
                callback_data=CheckoutNavCallback(action="back").pack(),
            )
        )
    if show_skip:
        row.append(
            InlineKeyboardButton(
                text=translator("checkout.skip_button"),
                callback_data=SkipStepCallback(step=skip_step).pack(),
            )
        )
    row.append(
        InlineKeyboardButton(
            text=translator("checkout.cancel_button"),
            callback_data=CheckoutNavCallback(action="cancel").pack(),
        )
    )
    return row


def order_type_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("checkout.type_delivery"),
            callback_data=OrderTypeCallback(value=OrderType.DELIVERY.value).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("checkout.type_pickup"),
            callback_data=OrderTypeCallback(value=OrderType.PICKUP.value).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("checkout.type_preorder"),
            callback_data=OrderTypeCallback(value=OrderType.PREORDER.value).pack(),
        )
    )
    builder.row(*_nav_row(translator, show_back=False))
    return builder.as_markup()


def name_step_keyboard(
    translator: Callable[..., str], default_name: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("checkout.use_default_name", name=default_name),
            callback_data=UseDefaultNameCallback().pack(),
        )
    )
    builder.row(*_nav_row(translator, show_back=True))
    return builder.as_markup()


def address_comment_step_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        *_nav_row(translator, show_back=True, show_skip=True, skip_step="address_comment")
    )
    return builder.as_markup()


def comment_step_keyboard(
    translator: Callable[..., str], *, show_back: bool
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        *_nav_row(translator, show_back=show_back, show_skip=True, skip_step="comment")
    )
    return builder.as_markup()


def payment_method_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("checkout.payment_cash"),
            callback_data=PaymentMethodCallback(value=PaymentMethod.CASH.value).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("checkout.payment_card"),
            callback_data=PaymentMethodCallback(
                value=PaymentMethod.CARD_TRANSFER.value
            ).pack(),
        )
    )
    builder.row(*_nav_row(translator, show_back=True))
    return builder.as_markup()


def back_cancel_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(*_nav_row(translator, show_back=True))
    return builder.as_markup()


def confirm_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("checkout.confirm_button"),
            callback_data=CheckoutNavCallback(action="confirm").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("checkout.edit_button"),
            callback_data=CheckoutNavCallback(action="edit").pack(),
        ),
        InlineKeyboardButton(
            text=translator("checkout.cancel_button"),
            callback_data=CheckoutNavCallback(action="cancel").pack(),
        ),
    )
    return builder.as_markup()

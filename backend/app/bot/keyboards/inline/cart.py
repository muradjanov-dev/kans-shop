from collections.abc import Callable, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import CartActionCallback, CartItemQtyCallback
from app.db.models.cart import CartItem


def cart_keyboard(
    items: Sequence[CartItem], *, lang: str, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        name = item.product.name_uz if lang == "uz" else item.product.name_ru
        builder.row(InlineKeyboardButton(text=name, callback_data="noop"))
        builder.row(
            InlineKeyboardButton(
                text="➖",
                callback_data=CartItemQtyCallback(
                    product_id=item.product_id, action="dec"
                ).pack(),
            ),
            InlineKeyboardButton(text=str(item.quantity), callback_data="noop"),
            InlineKeyboardButton(
                text="➕",
                callback_data=CartItemQtyCallback(
                    product_id=item.product_id, action="inc"
                ).pack(),
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=CartItemQtyCallback(
                    product_id=item.product_id, action="remove"
                ).pack(),
            ),
        )
    if items:
        builder.row(
            InlineKeyboardButton(
                text=translator("cart.clear_button"),
                callback_data=CartActionCallback(action="clear").pack(),
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=translator("cart.checkout_button"),
                callback_data=CartActionCallback(action="checkout").pack(),
            )
        )
    return builder.as_markup()


def cart_clear_confirm_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("cart.clear_confirm_yes"),
            callback_data=CartActionCallback(action="clear_confirm").pack(),
        ),
        InlineKeyboardButton(
            text=translator("cart.clear_confirm_no"),
            callback_data=CartActionCallback(action="clear_cancel").pack(),
        ),
    )
    return builder.as_markup()

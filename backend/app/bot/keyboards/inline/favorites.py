from collections.abc import Callable, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import FavoriteRemoveCallback
from app.db.models.product import Product


def favorites_keyboard(
    products: Sequence[Product], *, lang: str, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        name = product.name_uz if lang == "uz" else product.name_ru
        builder.row(
            InlineKeyboardButton(
                text=f"🗑 {name}",
                callback_data=FavoriteRemoveCallback(product_id=product.id).pack(),
            )
        )
    return builder.as_markup()

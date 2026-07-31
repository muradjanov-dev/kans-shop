from collections.abc import Callable, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import FavoriteRemoveCallback
from app.db.models.favorite import Favorite


def favorites_keyboard(
    favorites: Sequence[Favorite], *, lang: str, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for fav in favorites:
        name = fav.product.name_uz if lang == "uz" else fav.product.name_ru
        builder.row(
            InlineKeyboardButton(
                text=f"🗑 {name}",
                callback_data=FavoriteRemoveCallback(product_id=fav.product_id).pack(),
            )
        )
    return builder.as_markup()

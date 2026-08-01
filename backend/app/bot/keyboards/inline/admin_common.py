from collections.abc import Callable, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import AdminFormCancelCallback
from app.db.models.category import Category


def cancel_button(translator: Callable[..., str]) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=translator("checkout.cancel_button"),
        callback_data=AdminFormCancelCallback().pack(),
    )


def cancel_only_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(cancel_button(translator))
    return builder.as_markup()


def flat_category_picker_keyboard(
    categories: Sequence[Category],
    *,
    translator: Callable[..., str],
    make_callback_data: Callable[[int], str],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        prefix = "— " if category.parent_id else ""
        marker = "" if category.is_active else "🔴 "
        label = f"{marker}{prefix}{category.name_uz} / {category.name_ru}"
        builder.row(
            InlineKeyboardButton(text=label, callback_data=make_callback_data(category.id))
        )
    builder.row(cancel_button(translator))
    return builder.as_markup()

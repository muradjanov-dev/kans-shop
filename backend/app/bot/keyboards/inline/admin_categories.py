from collections.abc import Callable, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import (
    AdminCategoryActionCallback,
    AdminCategoryDetailCallback,
    AdminCategoryListCallback,
    AdminMenuCallback,
)
from app.db.models.category import Category


def admin_categories_list_keyboard(
    categories: Sequence[Category], *, parent_id: int, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.row(
            InlineKeyboardButton(
                text=f"{category.name_uz} / {category.name_ru}",
                callback_data=AdminCategoryDetailCallback(category_id=category.id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.category_add_button"),
            callback_data=AdminCategoryActionCallback(
                category_id=parent_id, action="add_sub"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.back_to_menu"),
            callback_data=AdminMenuCallback(section="menu").pack(),
        )
    )
    return builder.as_markup()


def admin_category_detail_keyboard(
    category: Category, *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.category_toggle_active"),
            callback_data=AdminCategoryActionCallback(
                category_id=category.id, action="toggle_active"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.category_add_sub_button"),
            callback_data=AdminCategoryActionCallback(
                category_id=category.id, action="add_sub"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.category_delete_button"),
            callback_data=AdminCategoryActionCallback(
                category_id=category.id, action="delete_request"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("common.back"),
            callback_data=AdminCategoryListCallback(parent_id=category.parent_id or 0).pack(),
        )
    )
    return builder.as_markup()


def admin_category_delete_confirm_keyboard(
    category: Category, *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.category_delete_confirm_yes"),
            callback_data=AdminCategoryActionCallback(
                category_id=category.id, action="delete_confirm"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("common.back"),
            callback_data=AdminCategoryDetailCallback(category_id=category.id).pack(),
        )
    )
    return builder.as_markup()

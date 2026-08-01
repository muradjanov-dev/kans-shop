from collections.abc import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import AdminMenuCallback
from app.core.config import settings


def admin_menu_keyboard(
    translator: Callable[..., str], *, new_orders_count: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    orders_label = translator("admin.menu_orders")
    if new_orders_count:
        orders_label += f" ({new_orders_count})"
    builder.row(
        InlineKeyboardButton(
            text=orders_label, callback_data=AdminMenuCallback(section="orders").pack()
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.menu_categories"),
            callback_data=AdminMenuCallback(section="categories").pack(),
        ),
        InlineKeyboardButton(
            text=translator("admin.menu_products"),
            callback_data=AdminMenuCallback(section="products").pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.menu_stats"),
            callback_data=AdminMenuCallback(section="stats").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.menu_broadcast"),
            callback_data=AdminMenuCallback(section="broadcast").pack(),
        ),
        InlineKeyboardButton(
            text=translator("admin.menu_users"),
            callback_data=AdminMenuCallback(section="users").pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.menu_settings"),
            callback_data=AdminMenuCallback(section="settings").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.menu_webapp"), url=f"{settings.webapp_url}/admin"
        )
    )
    return builder.as_markup()


def back_to_admin_menu_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.back_to_menu"),
            callback_data=AdminMenuCallback(section="menu").pack(),
        )
    )
    return builder.as_markup()

from collections.abc import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import MenuCallback
from app.core.config import settings


def _button(translator: Callable[..., str], key: str, action: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=translator(f"menu.{key}"), callback_data=MenuCallback(action=action).pack()
    )


def main_menu_inline_keyboard(
    translator: Callable[..., str], *, is_admin: bool = False
) -> InlineKeyboardMarkup:
    """Inline replacement for the old reply keyboard. The Mini App entry stays a web_app
    button (inline buttons support WebAppInfo just as reply buttons do)."""
    builder = InlineKeyboardBuilder()
    builder.row(
        _button(translator, "catalog", "catalog"),
        _button(translator, "cart", "cart"),
    )
    builder.row(
        _button(translator, "orders", "orders"),
        _button(translator, "favorites", "favorites"),
    )
    builder.row(
        _button(translator, "about", "about"),
        _button(translator, "contact", "contact"),
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("menu.webapp"),
            web_app=WebAppInfo(url=settings.webapp_url),
        ),
        _button(translator, "settings", "settings"),
    )
    if is_admin:
        builder.row(
            InlineKeyboardButton(
                text=translator("admin.menu_title"),
                callback_data=MenuCallback(action="admin").pack(),
            )
        )
    return builder.as_markup()


def back_to_menu_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    """Single "back to main menu" button, for leaf views that would otherwise dead-end now
    that the persistent reply keyboard is gone."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("menu.back_to_menu"),
            callback_data=MenuCallback(action="menu").pack(),
        )
    )
    return builder.as_markup()

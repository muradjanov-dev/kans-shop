from collections.abc import Callable

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.core.config import settings


def main_menu_keyboard(translator: Callable[..., str]) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=translator("menu.catalog")),
        KeyboardButton(text=translator("menu.cart")),
    )
    builder.row(
        KeyboardButton(text=translator("menu.orders")),
        KeyboardButton(text=translator("menu.favorites")),
    )
    builder.row(
        KeyboardButton(text=translator("menu.about")),
        KeyboardButton(text=translator("menu.contact")),
    )
    builder.row(
        KeyboardButton(
            text=translator("menu.webapp"),
            web_app=WebAppInfo(url=settings.webapp_url),
        ),
        KeyboardButton(text=translator("menu.settings")),
    )
    return builder.as_markup(resize_keyboard=True)

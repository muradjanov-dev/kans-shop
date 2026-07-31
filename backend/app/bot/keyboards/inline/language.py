from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import LanguageCallback


def language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🇺🇿 O'zbekcha", callback_data=LanguageCallback(code="uz").pack()
        ),
        InlineKeyboardButton(
            text="🇷🇺 Русский", callback_data=LanguageCallback(code="ru").pack()
        ),
    )
    return builder.as_markup()

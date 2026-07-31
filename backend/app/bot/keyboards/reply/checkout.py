from collections.abc import Callable

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def phone_request_keyboard(translator: Callable[..., str]) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=translator("checkout.send_contact_button"), request_contact=True)
    )
    builder.row(KeyboardButton(text=translator("checkout.cancel_button")))
    return builder.as_markup(resize_keyboard=True)


def location_request_keyboard(translator: Callable[..., str]) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=translator("checkout.send_location_button"), request_location=True)
    )
    builder.row(KeyboardButton(text=translator("checkout.cancel_button")))
    return builder.as_markup(resize_keyboard=True)

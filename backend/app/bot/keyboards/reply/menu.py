from collections.abc import Awaitable, Callable

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def browse_cart_keyboard(translator: Callable[..., str]) -> ReplyKeyboardMarkup:
    """Keep a single cart shortcut visible while customers browse the catalog."""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=translator("menu.cart")))
    return builder.as_markup(resize_keyboard=True, is_persistent=True)


async def install_browse_cart_keyboard(
    send: Callable[..., Awaitable[object]], translator: Callable[..., str]
) -> object:
    """Install the reply keyboard on its own message, separate from inline catalog controls."""
    return await send(
        translator("cart.keyboard_hint"), reply_markup=browse_cart_keyboard(translator)
    )

from collections.abc import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import AdminMenuCallback, AdminSettingEditCallback

SETTINGS_FIELDS = (
    "delivery_fee",
    "free_delivery_from",
    "min_order_amount",
    "work_hours",
    "card_number",
    "card_holder",
    "support_username",
    "shop_phone",
    "is_shop_open",
)


def settings_list_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key in SETTINGS_FIELDS:
        builder.row(
            InlineKeyboardButton(
                text=translator(f"admin.setting_{key}"),
                callback_data=AdminSettingEditCallback(key=key).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.back_to_menu"),
            callback_data=AdminMenuCallback(section="menu").pack(),
        )
    )
    return builder.as_markup()

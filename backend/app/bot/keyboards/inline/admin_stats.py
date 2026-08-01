from collections.abc import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import (
    AdminMenuCallback,
    StatsExportCallback,
    StatsPeriodCallback,
)


def stats_keyboard(translator: Callable[..., str], *, period: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.stats_period_today"),
            callback_data=StatsPeriodCallback(period="today").pack(),
        ),
        InlineKeyboardButton(
            text=translator("admin.stats_period_week"),
            callback_data=StatsPeriodCallback(period="week").pack(),
        ),
        InlineKeyboardButton(
            text=translator("admin.stats_period_month"),
            callback_data=StatsPeriodCallback(period="month").pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.stats_export_button"),
            callback_data=StatsExportCallback(period=period).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.back_to_menu"),
            callback_data=AdminMenuCallback(section="menu").pack(),
        )
    )
    return builder.as_markup()

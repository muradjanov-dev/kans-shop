from collections.abc import Callable, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import (
    AdminMenuCallback,
    AdminSourceActionCallback,
    AdminSourceAddCallback,
    AdminSourceDetailCallback,
)
from app.db.models.traffic_source import TrafficSource


def admin_sources_list_keyboard(
    sources: Sequence[TrafficSource], *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for source in sources:
        marker = "" if source.is_active else "🔴 "
        builder.row(
            InlineKeyboardButton(
                text=f"{marker}{source.name} · {source.clicks_count}",
                callback_data=AdminSourceDetailCallback(source_id=source.id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.source_add_button"),
            callback_data=AdminSourceAddCallback().pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.back_to_menu"),
            callback_data=AdminMenuCallback(section="menu").pack(),
        )
    )
    return builder.as_markup()


def admin_source_detail_keyboard(
    source: TrafficSource, *, translator: Callable[..., str], share_url: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=translator("admin.source_share_button"), url=share_url)
    )
    toggle_key = (
        "admin.source_deactivate_button"
        if source.is_active
        else "admin.source_activate_button"
    )
    builder.row(
        InlineKeyboardButton(
            text=translator(toggle_key),
            callback_data=AdminSourceActionCallback(
                source_id=source.id, action="toggle"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.source_delete_button"),
            callback_data=AdminSourceActionCallback(
                source_id=source.id, action="delete_request"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("common.back"),
            callback_data=AdminMenuCallback(section="sources").pack(),
        )
    )
    return builder.as_markup()


def admin_source_delete_confirm_keyboard(
    source: TrafficSource, *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.source_delete_confirm_yes"),
            callback_data=AdminSourceActionCallback(
                source_id=source.id, action="delete_confirm"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("common.back"),
            callback_data=AdminSourceDetailCallback(source_id=source.id).pack(),
        )
    )
    return builder.as_markup()

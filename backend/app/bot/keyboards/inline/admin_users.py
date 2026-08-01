from collections.abc import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import (
    AdminMenuCallback,
    AdminUserActionCallback,
    AdminUserListCallback,
)
from app.db.models.user import User
from app.services.common import Page


def admin_user_list_keyboard(
    page: Page[User], *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user in page.items:
        marker = "🔴 " if user.is_blocked else ""
        name = f"{user.first_name} {user.last_name or ''}".strip()
        builder.row(
            InlineKeyboardButton(
                text=f"{marker}{name}",
                callback_data=AdminUserActionCallback(user_id=user.id, action="view").pack(),
            )
        )
    nav_row = []
    if page.has_prev:
        nav_row.append(
            InlineKeyboardButton(
                text="◀️", callback_data=AdminUserListCallback(page=page.page - 1).pack()
            )
        )
    if page.total:
        nav_row.append(
            InlineKeyboardButton(
                text=translator(
                    "catalog.page_indicator", page=page.page, total_pages=page.total_pages
                ),
                callback_data="noop",
            )
        )
    if page.has_next:
        nav_row.append(
            InlineKeyboardButton(
                text="▶️", callback_data=AdminUserListCallback(page=page.page + 1).pack()
            )
        )
    if nav_row:
        builder.row(*nav_row)
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.back_to_menu"),
            callback_data=AdminMenuCallback(section="menu").pack(),
        )
    )
    return builder.as_markup()


def admin_user_detail_keyboard(
    user: User, *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    action = "unblock" if user.is_blocked else "block"
    label = (
        translator("admin.user_unblock_button")
        if user.is_blocked
        else translator("admin.user_block_button")
    )
    builder.row(
        InlineKeyboardButton(
            text=label,
            callback_data=AdminUserActionCallback(user_id=user.id, action=action).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("common.back"), callback_data=AdminUserListCallback(page=1).pack()
        )
    )
    return builder.as_markup()

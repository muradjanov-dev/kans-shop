from collections.abc import Callable, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import (
    AdminManageActionCallback,
    AdminManageAddCallback,
    AdminManageDetailCallback,
    AdminMenuCallback,
    AdminRoleChooseCallback,
)
from app.bot.keyboards.inline.admin_common import cancel_button
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole

ROLE_LABEL_KEYS = {
    AdminRole.SUPERADMIN: "admin.role_superadmin",
    AdminRole.MANAGER: "admin.role_manager",
    AdminRole.OPERATOR: "admin.role_operator",
}


def admins_list_keyboard(
    admins: Sequence[Admin], *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for admin in admins:
        marker = "" if admin.is_active else "🔴 "
        role = translator(ROLE_LABEL_KEYS[admin.role])
        builder.row(
            InlineKeyboardButton(
                text=f"{marker}{admin.full_name} · {role}",
                callback_data=AdminManageDetailCallback(admin_id=admin.id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.admin_add_button"),
            callback_data=AdminManageAddCallback().pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.back_to_menu"),
            callback_data=AdminMenuCallback(section="menu").pack(),
        )
    )
    return builder.as_markup()


def admin_detail_keyboard(
    admin: Admin, *, translator: Callable[..., str], is_self: bool
) -> InlineKeyboardMarkup:
    """`is_self` hides the destructive actions on your own row — an admin demoting or
    deactivating themselves would lock themselves out of the panel mid-session."""
    builder = InlineKeyboardBuilder()
    if not is_self:
        builder.row(
            InlineKeyboardButton(
                text=translator("admin.admin_change_role_button"),
                callback_data=AdminManageActionCallback(
                    admin_id=admin.id, action="role_menu"
                ).pack(),
            )
        )
        toggle_key = (
            "admin.admin_deactivate_button"
            if admin.is_active
            else "admin.admin_activate_button"
        )
        builder.row(
            InlineKeyboardButton(
                text=translator(toggle_key),
                callback_data=AdminManageActionCallback(
                    admin_id=admin.id, action="toggle"
                ).pack(),
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=translator("admin.admin_remove_button"),
                callback_data=AdminManageActionCallback(
                    admin_id=admin.id, action="remove_request"
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=translator("common.back"),
            callback_data=AdminMenuCallback(section="admins").pack(),
        )
    )
    return builder.as_markup()


def role_picker_keyboard(
    *, admin_id: int, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    """`admin_id=0` means "the admin currently being created" — the role is the last step of
    the add form, before the row exists."""
    builder = InlineKeyboardBuilder()
    for role, label_key in ROLE_LABEL_KEYS.items():
        builder.row(
            InlineKeyboardButton(
                text=translator(label_key),
                callback_data=AdminRoleChooseCallback(
                    admin_id=admin_id, role=role.value
                ).pack(),
            )
        )
    if admin_id:
        builder.row(
            InlineKeyboardButton(
                text=translator("common.back"),
                callback_data=AdminManageDetailCallback(admin_id=admin_id).pack(),
            )
        )
    else:
        builder.row(cancel_button(translator))
    return builder.as_markup()


def admin_remove_confirm_keyboard(
    admin: Admin, *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.admin_remove_confirm_yes"),
            callback_data=AdminManageActionCallback(
                admin_id=admin.id, action="remove_confirm"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("common.back"),
            callback_data=AdminManageDetailCallback(admin_id=admin.id).pack(),
        )
    )
    return builder.as_markup()

from collections.abc import Callable

from aiogram.types import CallbackQuery, Message

from app.db.models.admin import Admin
from app.db.models.enums import AdminRole

MANAGEMENT_ROLES = (AdminRole.SUPERADMIN, AdminRole.MANAGER)


async def require_admin(
    event: CallbackQuery | Message,
    admin: Admin | None,
    translator: Callable[..., str],
    *,
    roles: tuple[AdminRole, ...] | None = None,
) -> bool:
    """Guards admin-only handlers. Every admin can act on orders (Phase 5); `roles` restricts
    catalog/broadcast/settings/user-management actions to manager+superadmin per DB_SCHEMA.md's
    role matrix."""
    allowed = admin is not None and admin.is_active and (roles is None or admin.role in roles)
    if not allowed:
        if isinstance(event, CallbackQuery):
            await event.answer(translator("admin.not_admin_alert"), show_alert=True)
        else:
            await event.answer(translator("admin.not_admin_alert"))
    return allowed

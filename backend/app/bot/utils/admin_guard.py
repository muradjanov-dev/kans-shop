from collections.abc import Callable

from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AdminSessionRequiredError, ForbiddenError
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole
from app.services.admin_actor_service import load_live_admin

MANAGEMENT_ROLES = (AdminRole.SUPERADMIN, AdminRole.MANAGER)


async def require_admin(
    event: CallbackQuery | Message,
    admin: Admin | None,
    translator: Callable[..., str],
    *,
    roles: tuple[AdminRole, ...] | None = None,
    session: AsyncSession | None = None,
) -> bool:
    """Guards admin-only handlers. Every admin can act on orders (Phase 5); `roles` restricts
    catalog/broadcast/settings/user-management actions to manager+superadmin per DB_SCHEMA.md's
    role matrix."""
    current_admin = admin
    if admin is not None and session is not None:
        try:
            current_admin = await load_live_admin(
                session,
                admin_id=admin.id,
                allowed_roles=frozenset(roles) if roles is not None else None,
            )
        except (AdminSessionRequiredError, ForbiddenError):
            current_admin = None

    allowed = (
        current_admin is not None
        and current_admin.is_active
        and (roles is None or current_admin.role in roles)
    )
    if not allowed:
        if isinstance(event, CallbackQuery):
            await event.answer(translator("admin.not_admin_alert"), show_alert=True)
        else:
            await event.answer(translator("admin.not_admin_alert"))
    return allowed

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AdminSessionRequiredError, ForbiddenError
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole


async def load_live_admin(
    session: AsyncSession,
    *,
    admin_id: int,
    allowed_roles: frozenset[AdminRole] | None = None,
    lock: bool = False,
) -> Admin:
    """Reload an actor's current authorization state inside the caller's transaction."""
    statement = (
        select(Admin).where(Admin.id == admin_id).execution_options(populate_existing=True)
    )
    if lock:
        # PostgreSQL's FOR NO KEY UPDATE serializes role changes but remains compatible with
        # the key-share lock taken when a row references this admin through a foreign key.
        statement = statement.with_for_update(key_share=True)

    admin = await session.scalar(statement)
    if admin is None or not admin.is_active:
        raise AdminSessionRequiredError("Admin session required")
    if allowed_roles is not None and admin.role not in allowed_roles:
        raise ForbiddenError("Insufficient role for this action")
    return admin

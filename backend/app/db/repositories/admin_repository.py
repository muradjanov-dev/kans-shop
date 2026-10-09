from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin import Admin
from app.db.models.enums import AdminRole


async def get_by_telegram_id(
    session: AsyncSession, telegram_id: int, *, for_update: bool = False
) -> Admin | None:
    statement = select(Admin).where(Admin.telegram_id == telegram_id)
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement.execution_options(populate_existing=True))


async def get_by_id(
    session: AsyncSession, admin_id: int, *, for_update: bool = False
) -> Admin | None:
    if not for_update:
        return await session.get(Admin, admin_id)
    statement = (
        select(Admin)
        .where(Admin.id == admin_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await session.scalar(statement)


async def list_active(session: AsyncSession) -> Sequence[Admin]:
    stmt = select(Admin).where(Admin.is_active.is_(True))
    return (await session.scalars(stmt)).all()


async def list_active_notifiable(session: AsyncSession) -> Sequence[Admin]:
    stmt = select(Admin).where(
        Admin.is_active.is_(True), Admin.notifications_enabled.is_(True)
    )
    return (await session.scalars(stmt)).all()


async def create(
    session: AsyncSession, *, telegram_id: int, full_name: str, role: AdminRole
) -> Admin:
    admin = Admin(telegram_id=telegram_id, full_name=full_name, role=role)
    session.add(admin)
    await session.flush()
    return admin


async def list_all(session: AsyncSession) -> Sequence[Admin]:
    stmt = select(Admin).order_by(Admin.created_at.asc())
    return (await session.scalars(stmt)).all()


async def count_active_superadmins(session: AsyncSession) -> int:
    stmt = (
        select(func.count())
        .select_from(Admin)
        .where(Admin.role == AdminRole.SUPERADMIN, Admin.is_active.is_(True))
    )
    return await session.scalar(stmt) or 0


async def set_role(session: AsyncSession, admin: Admin, role: AdminRole) -> Admin:
    admin.role = role
    await session.flush()
    return admin


async def set_active(session: AsyncSession, admin: Admin, is_active: bool) -> Admin:
    admin.is_active = is_active
    await session.flush()
    return admin


async def delete(session: AsyncSession, admin: Admin) -> None:
    await session.delete(admin)
    await session.flush()

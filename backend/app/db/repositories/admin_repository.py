from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin import Admin
from app.db.models.enums import AdminRole


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> Admin | None:
    return await session.scalar(select(Admin).where(Admin.telegram_id == telegram_id))


async def get_by_id(session: AsyncSession, admin_id: int) -> Admin | None:
    return await session.get(Admin, admin_id)


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

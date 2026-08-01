from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.category import Category


async def get_by_id(session: AsyncSession, category_id: int) -> Category | None:
    return await session.get(Category, category_id)


async def get_by_slug(session: AsyncSession, slug: str) -> Category | None:
    return await session.scalar(select(Category).where(Category.slug == slug))


async def list_children(
    session: AsyncSession, parent_id: int | None, *, active_only: bool = True
) -> Sequence[Category]:
    stmt = select(Category).where(Category.parent_id == parent_id)
    if active_only:
        stmt = stmt.where(Category.is_active.is_(True))
    stmt = stmt.order_by(Category.sort_order, Category.id)
    return (await session.scalars(stmt)).all()


async def list_all(session: AsyncSession, *, active_only: bool = True) -> Sequence[Category]:
    stmt = select(Category)
    if active_only:
        stmt = stmt.where(Category.is_active.is_(True))
    stmt = stmt.order_by(Category.sort_order, Category.id)
    return (await session.scalars(stmt)).all()

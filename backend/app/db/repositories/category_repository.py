from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.category import Category


def public_category_ids():
    """Return active categories reachable from an active root through active ancestors.

    Starting at roots omits disconnected parent cycles. UNION removes repeated ids, so even a
    malformed cycle reachable through future schema changes cannot recurse indefinitely.
    """
    visible = (
        select(Category.id.label("id"))
        .where(Category.parent_id.is_(None), Category.is_active.is_(True))
        .cte("public_category_ids", recursive=True)
    )
    return visible.union(
        select(Category.id.label("id"))
        .join(visible, Category.parent_id == visible.c.id)
        .where(Category.is_active.is_(True))
    )


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


async def list_public_children(
    session: AsyncSession, parent_id: int | None
) -> Sequence[Category]:
    visible = public_category_ids()
    stmt = (
        select(Category)
        .where(
            Category.parent_id == parent_id,
            Category.id.in_(select(visible.c.id)),
        )
        .order_by(Category.sort_order, Category.id)
    )
    return (await session.scalars(stmt)).all()


async def get_public_by_id(session: AsyncSession, category_id: int) -> Category | None:
    visible = public_category_ids()
    stmt = select(Category).where(
        Category.id == category_id,
        Category.id.in_(select(visible.c.id)),
    )
    return await session.scalar(stmt)


async def get_public_by_slug(session: AsyncSession, slug: str) -> Category | None:
    visible = public_category_ids()
    stmt = select(Category).where(
        Category.slug == slug,
        Category.id.in_(select(visible.c.id)),
    )
    return await session.scalar(stmt)


async def list_all(session: AsyncSession, *, active_only: bool = True) -> Sequence[Category]:
    stmt = select(Category)
    if active_only:
        stmt = stmt.where(Category.is_active.is_(True))
    stmt = stmt.order_by(Category.sort_order, Category.id)
    return (await session.scalars(stmt)).all()

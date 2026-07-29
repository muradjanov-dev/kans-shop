from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.favorite import Favorite


async def list_by_user(session: AsyncSession, user_id: int) -> Sequence[Favorite]:
    stmt = (
        select(Favorite)
        .where(Favorite.user_id == user_id)
        .options(selectinload(Favorite.product))
        .order_by(Favorite.created_at.desc())
    )
    return (await session.scalars(stmt)).all()


async def get(session: AsyncSession, user_id: int, product_id: int) -> Favorite | None:
    stmt = select(Favorite).where(
        Favorite.user_id == user_id, Favorite.product_id == product_id
    )
    return await session.scalar(stmt)


async def add(session: AsyncSession, user_id: int, product_id: int) -> Favorite:
    existing = await get(session, user_id, product_id)
    if existing is not None:
        return existing
    favorite = Favorite(user_id=user_id, product_id=product_id)
    session.add(favorite)
    await session.flush()
    return favorite


async def remove(session: AsyncSession, user_id: int, product_id: int) -> None:
    existing = await get(session, user_id, product_id)
    if existing is not None:
        await session.delete(existing)
        await session.flush()

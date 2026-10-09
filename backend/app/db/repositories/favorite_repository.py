from collections.abc import Sequence

from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.favorite import Favorite
from app.db.models.product import Product
from app.db.repositories.product_repository import public_visibility_predicate


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


async def list_public_products_by_user(
    session: AsyncSession, user_id: int, *, page: int, limit: int
) -> tuple[Sequence[Product], int]:
    filters = (Favorite.user_id == user_id, public_visibility_predicate())
    total = await session.scalar(
        select(func.count())
        .select_from(Favorite)
        .join(Product, Favorite.product_id == Product.id)
        .where(*filters)
    )
    stmt = (
        select(Product)
        .join(Favorite, Favorite.product_id == Product.id)
        .where(*filters)
        .options(selectinload(Product.images))
        .order_by(Favorite.created_at.desc(), Favorite.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = (await session.scalars(stmt)).all()
    return items, total or 0


async def is_favorite(session: AsyncSession, user_id: int, product_id: int) -> bool:
    stmt = select(
        exists().where(Favorite.user_id == user_id, Favorite.product_id == product_id)
    )
    return bool(await session.scalar(stmt))


async def add(session: AsyncSession, user_id: int, product_id: int) -> None:
    stmt = (
        insert(Favorite)
        .values(user_id=user_id, product_id=product_id)
        .on_conflict_do_nothing(constraint="uq_favorites_user_product")
    )
    await session.execute(stmt)
    await session.flush()


async def remove(session: AsyncSession, user_id: int, product_id: int) -> None:
    await session.execute(
        delete(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
    )
    await session.flush()

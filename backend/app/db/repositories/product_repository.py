from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.product import Product


def _with_images(stmt):
    return stmt.options(selectinload(Product.images))


async def get_by_id(
    session: AsyncSession, product_id: int, *, for_update: bool = False
) -> Product | None:
    stmt = _with_images(select(Product).where(Product.id == product_id))
    if for_update:
        # SELECT ... FOR UPDATE is incompatible with eager-loading joins/subqueries in some
        # dialects; row-lock the bare product row here, callers load images separately if needed.
        stmt = select(Product).where(Product.id == product_id).with_for_update()
    return await session.scalar(stmt)


async def get_by_sku(session: AsyncSession, sku: str) -> Product | None:
    return await session.scalar(select(Product).where(Product.sku == sku))


async def list_by_category(
    session: AsyncSession,
    category_id: int,
    *,
    page: int = 1,
    limit: int = 8,
    active_only: bool = True,
) -> tuple[Sequence[Product], int]:
    stmt = select(Product).where(Product.category_id == category_id)
    if active_only:
        stmt = stmt.where(Product.is_active.is_(True))

    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))

    stmt = _with_images(stmt).order_by(Product.sort_order, Product.id)
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    items = (await session.scalars(stmt)).all()
    return items, total or 0


async def search(
    session: AsyncSession, query: str, *, page: int = 1, limit: int = 8
) -> tuple[Sequence[Product], int]:
    trgm_match = Product.name_uz.op("%")(query) | Product.name_ru.op("%")(query)
    ilike_match = Product.name_uz.ilike(f"%{query}%") | Product.name_ru.ilike(f"%{query}%")
    base = select(Product).where(Product.is_active.is_(True), trgm_match | ilike_match)

    total = await session.scalar(select(func.count()).select_from(base.subquery()))

    similarity = func.greatest(
        func.similarity(Product.name_uz, query), func.similarity(Product.name_ru, query)
    )
    stmt = _with_images(base).order_by(similarity.desc(), Product.id)
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    items = (await session.scalars(stmt)).all()
    return items, total or 0


async def list_featured(session: AsyncSession, *, limit: int = 10) -> Sequence[Product]:
    stmt = (
        _with_images(
            select(Product).where(Product.is_active.is_(True), Product.is_featured.is_(True))
        )
        .order_by(Product.sort_order, Product.id)
        .limit(limit)
    )
    return (await session.scalars(stmt)).all()


async def increment_views(session: AsyncSession, product: Product) -> None:
    product.views_count += 1
    await session.flush()


async def adjust_stock(session: AsyncSession, product: Product, delta: int) -> None:
    product.stock_qty += delta
    await session.flush()


async def increment_sold(session: AsyncSession, product: Product, quantity: int) -> None:
    product.sold_count += quantity
    await session.flush()


async def count_by_category(session: AsyncSession, category_id: int) -> int:
    stmt = select(func.count()).where(
        Product.category_id == category_id, Product.is_active.is_(True)
    )
    return (await session.scalar(stmt)) or 0

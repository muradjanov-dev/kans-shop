from collections.abc import Sequence
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.product import Product
from app.db.repositories import category_repository


def _with_images(stmt):
    return stmt.options(selectinload(Product.images))


def public_visibility_predicate():
    visible_categories = category_repository.public_category_ids()
    return Product.is_active.is_(True) & Product.category_id.in_(
        select(visible_categories.c.id)
    )


async def get_by_id(
    session: AsyncSession, product_id: int, *, for_update: bool = False
) -> Product | None:
    stmt = _with_images(select(Product).where(Product.id == product_id))
    if for_update:
        # SELECT ... FOR UPDATE is incompatible with eager-loading joins/subqueries in some
        # dialects; row-lock the bare product row here, callers load images separately if needed.
        # Cart loading may already have placed a stale Product in the identity map before this
        # lock waits. Refresh its columns from the locked row before validating stock or price.
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    return await session.scalar(stmt)


async def get_public_by_id(session: AsyncSession, product_id: int) -> Product | None:
    stmt = _with_images(
        select(Product).where(Product.id == product_id, public_visibility_predicate())
    ).execution_options(populate_existing=True)
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


async def list_public(
    session: AsyncSession,
    *,
    query: str | None,
    category_id: int | None,
    min_price: Decimal | None,
    max_price: Decimal | None,
    in_stock: bool,
    sort: Literal["default", "price_asc", "price_desc", "newest"],
    page: int,
    limit: int,
) -> tuple[Sequence[Product], int]:
    conditions = [public_visibility_predicate()]
    if category_id is not None:
        conditions.append(Product.category_id == category_id)
    if min_price is not None:
        conditions.append(Product.price >= min_price)
    if max_price is not None:
        conditions.append(Product.price <= max_price)
    if in_stock:
        conditions.extend([Product.stock_qty > 0, Product.stock_qty >= Product.min_order_qty])

    normalized_query = query.strip() if query is not None else None
    if normalized_query:
        trgm_match = Product.name_uz.op("%")(normalized_query) | Product.name_ru.op("%")(
            normalized_query
        )
        ilike_match = Product.name_uz.ilike(f"%{normalized_query}%") | Product.name_ru.ilike(
            f"%{normalized_query}%"
        )
        conditions.append(trgm_match | ilike_match)

    base = select(Product).where(*conditions)
    total = await session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )

    stmt = _with_images(base)
    if normalized_query:
        similarity = func.greatest(
            func.similarity(Product.name_uz, normalized_query),
            func.similarity(Product.name_ru, normalized_query),
        )
        stmt = stmt.order_by(similarity.desc(), Product.id)
    elif sort == "price_asc":
        stmt = stmt.order_by(Product.price, Product.id)
    elif sort == "price_desc":
        stmt = stmt.order_by(Product.price.desc(), Product.id)
    elif sort == "newest":
        stmt = stmt.order_by(Product.created_at.desc(), Product.id.desc())
    else:
        stmt = stmt.order_by(Product.sort_order, Product.id)

    stmt = stmt.offset((page - 1) * limit).limit(limit)
    items = (await session.scalars(stmt)).all()
    return items, total or 0


async def list_featured(session: AsyncSession, *, limit: int = 10) -> Sequence[Product]:
    stmt = (
        _with_images(
            select(Product).where(public_visibility_predicate(), Product.is_featured.is_(True))
        )
        .order_by(Product.sort_order, Product.id)
        .limit(limit)
    )
    return (await session.scalars(stmt)).all()


async def increment_views(session: AsyncSession, product: Product) -> None:
    product.views_count += 1
    await session.flush()


async def adjust_stock(session: AsyncSession, product: Product, delta: int) -> None:
    if delta:
        product.stock_qty += delta
        product.edit_version += 1
        await session.flush()


async def increment_sold(session: AsyncSession, product: Product, quantity: int) -> None:
    product.sold_count += quantity
    await session.flush()


async def count_by_category(session: AsyncSession, category_id: int) -> int:
    stmt = select(func.count()).where(
        Product.category_id == category_id, Product.is_active.is_(True)
    )
    return (await session.scalar(stmt)) or 0

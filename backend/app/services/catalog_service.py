from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CategoryNotFoundError, ProductNotFoundError
from app.db.models.category import Category
from app.db.models.product import Product
from app.db.repositories import category_repository, product_repository
from app.services.common import DEFAULT_CATALOG_PAGE_SIZE, PUBLIC_CATALOG_PAGE_SIZE, Page

CatalogSort = Literal["default", "price_asc", "price_desc", "newest"]


@dataclass(frozen=True)
class CatalogFilters:
    category_id: int | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    in_stock: bool = False
    sort: CatalogSort = "default"


async def list_root_categories(session: AsyncSession) -> Sequence[Category]:
    return await category_repository.list_public_children(session, parent_id=None)


async def list_subcategories(session: AsyncSession, parent_id: int) -> Sequence[Category]:
    await get_category(session, parent_id)
    return await category_repository.list_public_children(session, parent_id=parent_id)


async def get_category(session: AsyncSession, category_id: int) -> Category:
    category = await category_repository.get_public_by_id(session, category_id)
    if category is None:
        raise CategoryNotFoundError(f"Category {category_id} not found")
    return category


async def get_category_by_slug(session: AsyncSession, slug: str) -> Category:
    category = await category_repository.get_public_by_slug(session, slug)
    if category is None:
        raise CategoryNotFoundError(f"Category slug={slug!r} not found")
    return category


async def list_products(
    session: AsyncSession,
    category_id: int,
    *,
    page: int = 1,
    limit: int = DEFAULT_CATALOG_PAGE_SIZE,
    filters: CatalogFilters | None = None,
) -> Page[Product]:
    await get_category(session, category_id)
    return await list_public_products(
        session,
        query=None,
        filters=replace(filters or CatalogFilters(), category_id=category_id),
        page=page,
        limit=limit,
    )


async def list_public_products(
    session: AsyncSession,
    *,
    query: str | None,
    filters: CatalogFilters,
    page: int = 1,
    limit: int = PUBLIC_CATALOG_PAGE_SIZE,
) -> Page[Product]:
    if (
        filters.min_price is not None
        and filters.max_price is not None
        and filters.min_price > filters.max_price
    ):
        raise ValueError("min_price must be less than or equal to max_price")
    normalized_query = query.strip() if query is not None else None
    if query is not None and not normalized_query:
        return Page(items=[], total=0, page=page, limit=limit)
    items, total = await product_repository.list_public(
        session,
        query=normalized_query,
        category_id=filters.category_id,
        min_price=filters.min_price,
        max_price=filters.max_price,
        in_stock=filters.in_stock,
        sort=filters.sort,
        page=page,
        limit=limit,
    )
    return Page(items=items, total=total, page=page, limit=limit)


async def get_product(
    session: AsyncSession, product_id: int, *, track_view: bool = False
) -> Product:
    product = await product_repository.get_public_by_id(session, product_id)
    if product is None:
        raise ProductNotFoundError(f"Product {product_id} not found")
    if track_view:
        await product_repository.increment_views(session, product)
    return product


async def search_products(
    session: AsyncSession, query: str, *, page: int = 1, limit: int = DEFAULT_CATALOG_PAGE_SIZE
) -> Page[Product]:
    return await list_public_products(
        session,
        query=query,
        filters=CatalogFilters(),
        page=page,
        limit=limit,
    )


async def list_featured_products(
    session: AsyncSession, *, limit: int = 10
) -> Sequence[Product]:
    return await product_repository.list_featured(session, limit=limit)

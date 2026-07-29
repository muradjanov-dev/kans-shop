from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CategoryNotFoundError, ProductNotFoundError
from app.db.models.category import Category
from app.db.models.product import Product
from app.db.repositories import category_repository, product_repository
from app.services.common import DEFAULT_CATALOG_PAGE_SIZE, Page


async def list_root_categories(session: AsyncSession) -> Sequence[Category]:
    return await category_repository.list_children(session, parent_id=None)


async def list_subcategories(session: AsyncSession, parent_id: int) -> Sequence[Category]:
    await get_category(session, parent_id)
    return await category_repository.list_children(session, parent_id=parent_id)


async def get_category(session: AsyncSession, category_id: int) -> Category:
    category = await category_repository.get_by_id(session, category_id)
    if category is None or not category.is_active:
        raise CategoryNotFoundError(f"Category {category_id} not found")
    return category


async def get_category_by_slug(session: AsyncSession, slug: str) -> Category:
    category = await category_repository.get_by_slug(session, slug)
    if category is None or not category.is_active:
        raise CategoryNotFoundError(f"Category slug={slug!r} not found")
    return category


async def list_products(
    session: AsyncSession,
    category_id: int,
    *,
    page: int = 1,
    limit: int = DEFAULT_CATALOG_PAGE_SIZE,
) -> Page[Product]:
    await get_category(session, category_id)
    items, total = await product_repository.list_by_category(
        session, category_id, page=page, limit=limit
    )
    return Page(items=items, total=total, page=page, limit=limit)


async def get_product(
    session: AsyncSession, product_id: int, *, track_view: bool = False
) -> Product:
    product = await product_repository.get_by_id(session, product_id)
    if product is None or not product.is_active:
        raise ProductNotFoundError(f"Product {product_id} not found")
    if track_view:
        await product_repository.increment_views(session, product)
    return product


async def search_products(
    session: AsyncSession, query: str, *, page: int = 1, limit: int = DEFAULT_CATALOG_PAGE_SIZE
) -> Page[Product]:
    query = query.strip()
    if not query:
        return Page(items=[], total=0, page=page, limit=limit)
    items, total = await product_repository.search(session, query, page=page, limit=limit)
    return Page(items=items, total=total, page=page, limit=limit)


async def list_featured_products(
    session: AsyncSession, *, limit: int = 10
) -> Sequence[Product]:
    return await product_repository.list_featured(session, limit=limit)

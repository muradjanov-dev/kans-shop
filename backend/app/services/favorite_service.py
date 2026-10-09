from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import Product
from app.db.repositories import favorite_repository
from app.services import catalog_service
from app.services.common import Page


async def list_favorites(
    session: AsyncSession, user_id: int, page: int = 1, limit: int = 24
) -> Page[Product]:
    items, total = await favorite_repository.list_public_products_by_user(
        session, user_id, page=page, limit=limit
    )
    return Page(items=items, total=total, page=page, limit=limit)


async def is_favorite(session: AsyncSession, user_id: int, product_id: int) -> bool:
    return await favorite_repository.is_favorite(session, user_id, product_id)


async def add_favorite(session: AsyncSession, user_id: int, product_id: int) -> None:
    await catalog_service.get_product(session, product_id)
    await favorite_repository.add(session, user_id, product_id)


async def remove_favorite(session: AsyncSession, user_id: int, product_id: int) -> None:
    await favorite_repository.remove(session, user_id, product_id)

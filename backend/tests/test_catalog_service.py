from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CategoryNotFoundError, ProductNotFoundError
from app.db.models.category import Category
from app.db.models.enums import ProductUnit
from app.db.models.product import Product
from app.services import catalog_service


async def test_get_product_not_found_raises(db_session: AsyncSession) -> None:
    with pytest.raises(ProductNotFoundError):
        await catalog_service.get_product(db_session, 999_999)


async def test_get_category_not_found_raises(db_session: AsyncSession) -> None:
    with pytest.raises(CategoryNotFoundError):
        await catalog_service.get_category(db_session, 999_999)


async def test_get_product_track_view_increments_counter(
    db_session: AsyncSession, product: Product
) -> None:
    assert product.views_count == 0

    await catalog_service.get_product(db_session, product.id, track_view=True)
    await catalog_service.get_product(db_session, product.id, track_view=True)

    refreshed = await catalog_service.get_product(db_session, product.id)
    assert refreshed.views_count == 2


async def test_list_products_paginates(db_session: AsyncSession, category: Category) -> None:
    for i in range(10):
        db_session.add(
            Product(
                category_id=category.id,
                name_uz=f"Mahsulot {i}",
                name_ru=f"Товар {i}",
                sku=f"SKU-{i}",
                price=Decimal("1000"),
                stock_qty=5,
                unit=ProductUnit.DONA,
            )
        )
    await db_session.flush()

    page1 = await catalog_service.list_products(db_session, category.id, page=1, limit=4)
    page2 = await catalog_service.list_products(db_session, category.id, page=2, limit=4)

    assert page1.total == 10
    assert len(page1.items) == 4
    assert page1.total_pages == 3
    assert page1.has_next is True
    assert page2.has_prev is True
    assert {p.id for p in page1.items}.isdisjoint({p.id for p in page2.items})


async def test_search_products_finds_by_partial_name(
    db_session: AsyncSession, category: Category
) -> None:
    db_session.add(
        Product(
            category_id=category.id,
            name_uz="Ruchka Pilot ko'k",
            name_ru="Ручка Pilot синяя",
            sku="SEARCH-1",
            price=Decimal("5000"),
            stock_qty=5,
            unit=ProductUnit.DONA,
        )
    )
    await db_session.flush()

    result = await catalog_service.search_products(db_session, "Pilot")

    assert result.total == 1
    assert result.items[0].sku == "SEARCH-1"


async def test_search_products_empty_query_returns_empty_page(
    db_session: AsyncSession,
) -> None:
    result = await catalog_service.search_products(db_session, "   ")
    assert result.total == 0
    assert result.items == []

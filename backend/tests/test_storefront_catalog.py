from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.exceptions import CategoryNotFoundError, ProductNotFoundError
from app.db.models.category import Category
from app.db.models.enums import ProductUnit
from app.db.models.product import Product
from app.services import catalog_service
from app.services.catalog_service import CatalogFilters, CatalogSort, list_public_products

from .api_helpers import make_api_case


def _filters(*, sort: CatalogSort = "default") -> CatalogFilters:
    return CatalogFilters(sort=sort)


async def test_catalog_all_products_filters_with_decimal_prices(
    db_session: AsyncSession, category: Category
) -> None:
    minimum_satisfied_product = Product(
        category_id=category.id,
        name_uz="Eligible minimum",
        name_ru="Eligible minimum",
        sku="PUBLIC-CATALOG-MINIMUM",
        price=Decimal("10.10"),
        stock_qty=4,
        min_order_qty=4,
        unit=ProductUnit.DONA,
    )
    products = [
        minimum_satisfied_product,
        Product(
            category_id=category.id,
            name_uz="Below minimum price",
            name_ru="Below minimum price",
            sku="PUBLIC-CATALOG-BELOW",
            price=Decimal("10.09"),
            stock_qty=8,
            unit=ProductUnit.DONA,
        ),
        Product(
            category_id=category.id,
            name_uz="At maximum",
            name_ru="At maximum",
            sku="PUBLIC-CATALOG-MAXIMUM",
            price=Decimal("10.15"),
            stock_qty=0,
            unit=ProductUnit.DONA,
        ),
        Product(
            category_id=category.id,
            name_uz="Insufficient minimum stock",
            name_ru="Insufficient minimum stock",
            sku="PUBLIC-CATALOG-INSUFFICIENT",
            price=Decimal("10.12"),
            stock_qty=3,
            min_order_qty=4,
            unit=ProductUnit.DONA,
        ),
        Product(
            category_id=category.id,
            name_uz="Out of stock",
            name_ru="Out of stock",
            sku="PUBLIC-CATALOG-EMPTY",
            price=Decimal("10.12"),
            stock_qty=0,
            unit=ProductUnit.DONA,
        ),
    ]
    db_session.add_all(products)
    await db_session.flush()

    price_filtered = await list_public_products(
        db_session,
        query=None,
        filters=CatalogFilters(
            category_id=category.id,
            min_price=Decimal("10.10"),
            max_price=Decimal("10.15"),
            sort="default",
        ),
    )
    in_stock = await list_public_products(
        db_session,
        query=None,
        filters=CatalogFilters(
            category_id=category.id,
            min_price=Decimal("10.10"),
            max_price=Decimal("10.15"),
            in_stock=True,
            sort="default",
        ),
    )

    assert [product.sku for product in price_filtered.items] == [
        "PUBLIC-CATALOG-MINIMUM",
        "PUBLIC-CATALOG-MAXIMUM",
        "PUBLIC-CATALOG-INSUFFICIENT",
        "PUBLIC-CATALOG-EMPTY",
    ]
    in_stock_product_ids = [product.id for product in in_stock.items]
    assert in_stock_product_ids == [minimum_satisfied_product.id]


async def test_catalog_sorts_stably_and_paginates(
    db_session: AsyncSession, category: Category
) -> None:
    created_at = datetime(2026, 10, 1, tzinfo=UTC)
    products = [
        Product(
            category_id=category.id,
            name_uz="Catalog pen",
            name_ru="Catalog pen",
            sku=f"PUBLIC-CATALOG-SORT-{i:02}",
            price=Decimal(100 + i % 3),
            stock_qty=50,
            sort_order=i % 2,
            unit=ProductUnit.DONA,
            created_at=created_at,
        )
        for i in range(30)
    ]
    db_session.add_all(products)
    await db_session.flush()

    first_page = await list_public_products(
        db_session, query=None, filters=_filters(), page=1, limit=24
    )
    repeated_first_page = await list_public_products(
        db_session, query=None, filters=_filters(), page=1, limit=24
    )
    second_page = await list_public_products(
        db_session, query=None, filters=_filters(), page=2, limit=24
    )
    assert len(first_page.items) == 24
    assert [p.id for p in first_page.items] == [p.id for p in repeated_first_page.items]
    assert {p.id for p in first_page.items}.isdisjoint(p.id for p in second_page.items)
    assert first_page.total == 30
    assert [p.id for p in first_page.items] == [
        p.id
        for p in sorted(products, key=lambda product: (product.sort_order, product.id))[:24]
    ]

    price_asc = await list_public_products(
        db_session, query=None, filters=_filters(sort="price_asc"), limit=30
    )
    price_desc = await list_public_products(
        db_session, query=None, filters=_filters(sort="price_desc"), limit=30
    )
    newest = await list_public_products(
        db_session, query=None, filters=_filters(sort="newest"), limit=30
    )
    relevant = await list_public_products(
        db_session, query="Catalog", filters=_filters(sort="price_desc"), limit=30
    )

    assert [p.id for p in price_asc.items] == [
        p.id for p in sorted(products, key=lambda product: (product.price, product.id))
    ]
    assert [p.id for p in price_desc.items] == [
        p.id for p in sorted(products, key=lambda product: (-product.price, product.id))
    ]
    assert [p.id for p in newest.items] == [p.id for p in reversed(products)]
    assert [p.id for p in relevant.items] == [p.id for p in products]


async def test_catalog_hides_inactive_and_cyclic_ancestors(
    db_session: AsyncSession, category: Category
) -> None:
    inactive_root = Category(
        name_uz="Inactive root",
        name_ru="Inactive root",
        slug="catalog-inactive-root",
        is_active=False,
    )
    db_session.add(inactive_root)
    await db_session.flush()
    inactive_branch = Category(
        parent_id=inactive_root.id,
        name_uz="Active child under inactive root",
        name_ru="Active child under inactive root",
        slug="catalog-active-child-under-inactive",
    )
    cycle_a = Category(name_uz="Cycle A", name_ru="Cycle A", slug="catalog-cycle-a")
    cycle_b = Category(name_uz="Cycle B", name_ru="Cycle B", slug="catalog-cycle-b")
    db_session.add_all([inactive_branch, cycle_a, cycle_b])
    await db_session.flush()
    cycle_a.parent_id = cycle_b.id
    cycle_b.parent_id = cycle_a.id
    await db_session.flush()

    visible = Product(
        category_id=category.id,
        name_uz="Visible product",
        name_ru="Visible product",
        sku="PUBLIC-CATALOG-VISIBLE",
        price=Decimal("1.00"),
        stock_qty=1,
        unit=ProductUnit.DONA,
    )
    hidden_products = [
        Product(
            category_id=hidden_category.id,
            name_uz=sku,
            name_ru=sku,
            sku=sku,
            price=Decimal("1.00"),
            stock_qty=1,
            unit=ProductUnit.DONA,
        )
        for hidden_category, sku in [
            (inactive_branch, "PUBLIC-CATALOG-INACTIVE-ANCESTOR"),
            (cycle_a, "PUBLIC-CATALOG-CYCLIC-ANCESTOR"),
        ]
    ]
    db_session.add_all([visible, *hidden_products])
    await db_session.flush()

    result = await list_public_products(db_session, query=None, filters=CatalogFilters())

    assert [product.sku for product in result.items] == ["PUBLIC-CATALOG-VISIBLE"]


async def test_catalog_category_tree_requires_active_ancestors(
    db_session: AsyncSession, category: Category
) -> None:
    inactive_root = Category(
        name_uz="Inactive nav root",
        name_ru="Inactive nav root",
        slug="catalog-nav-inactive-root",
        is_active=False,
    )
    active_root = Category(
        name_uz="Visible nav root",
        name_ru="Visible nav root",
        slug="catalog-nav-visible-root",
    )
    db_session.add_all([inactive_root, active_root])
    await db_session.flush()
    hidden_child = Category(
        parent_id=inactive_root.id,
        name_uz="Child beneath inactive root",
        name_ru="Child beneath inactive root",
        slug="catalog-nav-hidden-child",
    )
    visible_child = Category(
        parent_id=active_root.id,
        name_uz="Visible child",
        name_ru="Visible child",
        slug="catalog-nav-visible-child",
    )
    db_session.add_all([hidden_child, visible_child])
    await db_session.flush()
    hidden_grandchild = Category(
        parent_id=hidden_child.id,
        name_uz="Descendant of hidden child",
        name_ru="Descendant of hidden child",
        slug="catalog-nav-hidden-grandchild",
    )
    db_session.add(hidden_grandchild)
    await db_session.flush()

    roots = await catalog_service.list_root_categories(db_session)
    children = await catalog_service.list_subcategories(db_session, active_root.id)

    assert {item.id for item in roots} == {category.id, active_root.id}
    assert [item.id for item in children] == [visible_child.id]
    with pytest.raises(CategoryNotFoundError):
        await catalog_service.list_subcategories(db_session, hidden_child.id)
    with pytest.raises(CategoryNotFoundError):
        await catalog_service.list_products(
            db_session, hidden_child.id, filters=CatalogFilters(in_stock=True)
        )


async def test_featured_and_detail_require_active_ancestors(
    db_session: AsyncSession,
) -> None:
    inactive_root = Category(
        name_uz="Featured hidden root",
        name_ru="Featured hidden root",
        slug="catalog-featured-hidden-root",
        is_active=False,
    )
    db_session.add(inactive_root)
    await db_session.flush()
    child = Category(
        parent_id=inactive_root.id,
        name_uz="Featured hidden child",
        name_ru="Featured hidden child",
        slug="catalog-featured-hidden-child",
    )
    db_session.add(child)
    await db_session.flush()
    hidden_featured = Product(
        category_id=child.id,
        name_uz="Hidden featured",
        name_ru="Hidden featured",
        sku="PUBLIC-CATALOG-HIDDEN-FEATURED",
        price=Decimal("1.00"),
        stock_qty=1,
        unit=ProductUnit.DONA,
        is_featured=True,
    )
    db_session.add(hidden_featured)
    await db_session.flush()

    assert await catalog_service.list_featured_products(db_session) == []
    with pytest.raises(ProductNotFoundError):
        await catalog_service.get_product(db_session, hidden_featured.id)


async def test_featured_endpoint_is_empty_without_real_flags(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine) as case:
        response = await case.client.get("/api/v1/catalog/featured")

    assert response.status_code == 200
    assert response.json() == []


async def test_catalog_rejects_invalid_price_range(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine) as case:
        response = await case.client.get(
            "/api/v1/catalog/products", params={"min_price": "20.00", "max_price": "10.00"}
        )

    assert response.status_code == 422


async def test_public_catalog_routes_share_filters_and_preserve_page_sizes(
    test_engine: AsyncEngine,
) -> None:
    async with make_api_case(test_engine) as case:
        async with case.session_maker() as session:
            base_product = await session.get(Product, case.product_id)
            assert base_product is not None
            category_id = base_product.category_id
            products = [
                Product(
                    category_id=category_id,
                    name_uz=f"Test pen {i}",
                    name_ru=f"Test pen {i}",
                    sku=f"PUBLIC-CATALOG-API-{i:02}",
                    price=Decimal(5000 + i % 3),
                    stock_qty=5 if i % 4 == 0 else 0,
                    min_order_qty=6 if i % 8 == 0 else 5,
                    unit=ProductUnit.DONA,
                )
                for i in range(29)
            ]
            session.add_all(products)
            await session.commit()

        all_products = await case.client.get("/api/v1/catalog/products")
        large_page = await case.client.get("/api/v1/catalog/products", params={"limit": 50})
        category_products = await case.client.get(
            f"/api/v1/catalog/categories/{category_id}/products"
        )
        search = await case.client.get("/api/v1/catalog/search", params={"q": "Test"})
        params = {
            "min_price": "5000.00",
            "max_price": "5002.00",
            "in_stock": "true",
        }
        filtered_all = await case.client.get("/api/v1/catalog/products", params=params)
        filtered_category = await case.client.get(
            f"/api/v1/catalog/categories/{category_id}/products", params=params
        )
        filtered_search = await case.client.get(
            "/api/v1/catalog/search", params={"q": "Test", **params}
        )
        async with case.session_maker() as session:
            await session.execute(
                delete(Product).where(Product.sku.like("PUBLIC-CATALOG-API-%"))
            )
            await session.commit()

    assert all_products.status_code == 200
    assert all_products.json()["total"] == 30
    assert all_products.json()["limit"] == 24
    assert large_page.json()["limit"] == 50
    assert len(large_page.json()["items"]) == 30
    assert category_products.json()["total"] == 30
    assert category_products.json()["limit"] == 8
    assert search.json()["total"] == 30
    assert search.json()["limit"] == 8
    assert filtered_all.json()["total"] == 5
    assert filtered_category.json()["total"] == 5
    assert filtered_search.json()["total"] == 5

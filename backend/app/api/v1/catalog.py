from dataclasses import replace
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas.catalog import CategoryOut, ProductOut, public_product_out
from app.api.schemas.common import PageOut
from app.db.models.product import Product
from app.db.repositories import product_repository
from app.services import catalog_service
from app.services.common import DEFAULT_CATALOG_PAGE_SIZE, PUBLIC_CATALOG_PAGE_SIZE
from app.services.inventory_policy import InventoryPolicy, get_inventory_policy

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _public_page(result, policy: InventoryPolicy) -> PageOut[ProductOut]:
    return PageOut[ProductOut](
        items=[public_product_out(product, policy) for product in result.items],
        total=result.total,
        page=result.page,
        limit=result.limit,
        total_pages=result.total_pages,
    )


def _catalog_options(
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    in_stock: bool = Query(default=False),
    sort: catalog_service.CatalogSort = Query(default="default"),
) -> catalog_service.CatalogFilters:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="min_price must not exceed max_price")
    return catalog_service.CatalogFilters(
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        sort=sort,
    )


def _catalog_filters(
    category_id: int | None = Query(default=None),
    options: catalog_service.CatalogFilters = Depends(_catalog_options),
) -> catalog_service.CatalogFilters:
    return replace(options, category_id=category_id)


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(
    parent_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> list[CategoryOut]:
    if parent_id is None:
        categories = await catalog_service.list_root_categories(session)
    else:
        categories = await catalog_service.list_subcategories(session, parent_id)
    return [CategoryOut.model_validate(c) for c in categories]


@router.get("/categories/{category_id}/products", response_model=PageOut[ProductOut])
async def list_category_products(
    category_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=DEFAULT_CATALOG_PAGE_SIZE, ge=1, le=50),
    options: catalog_service.CatalogFilters = Depends(_catalog_options),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> PageOut[ProductOut]:
    inventory_policy = await get_inventory_policy(session)
    result = await catalog_service.list_products(
        session,
        category_id,
        page=page,
        limit=limit,
        filters=options,
        inventory_policy=inventory_policy,
    )
    return _public_page(result, inventory_policy)


@router.get("/products", response_model=PageOut[ProductOut])
async def list_all_products(
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=PUBLIC_CATALOG_PAGE_SIZE, ge=1, le=50),
    filters: catalog_service.CatalogFilters = Depends(_catalog_filters),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> PageOut[ProductOut]:
    inventory_policy = await get_inventory_policy(session)
    result = await catalog_service.list_public_products(
        session,
        query=q,
        filters=filters,
        page=page,
        limit=limit,
        inventory_policy=inventory_policy,
    )
    return _public_page(result, inventory_policy)


@router.get("/featured", response_model=list[ProductOut])
async def list_featured_products(
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> list[ProductOut]:
    products = await catalog_service.list_featured_products(session, limit=limit)
    inventory_policy = await get_inventory_policy(session)
    return [public_product_out(product, inventory_policy) for product in products]


class ShowcaseProductOut(BaseModel):
    """The few fields the storefront's top carousel needs for every active product."""

    id: int
    name_uz: str
    name_ru: str
    price: Decimal
    old_price: Decimal | None
    image_url: str | None
    is_featured: bool
    min_order_qty: int
    available: bool


def _main_image_url(product: Product) -> str | None:
    images = sorted(product.images, key=lambda image: (not image.is_main, image.sort_order))
    return next(
        (image.url.strip() for image in images if image.url and image.url.strip()), None
    )


@router.get("/showcase", response_model=list[ShowcaseProductOut])
async def list_showcase_products(
    response: Response,
    limit: int = Query(default=300, ge=1, le=500),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> list[ShowcaseProductOut]:
    """Every active product in one light request, featured ones first (top carousel)."""
    policy = await get_inventory_policy(session)
    products, _total = await product_repository.list_public(
        session,
        query=None,
        category_id=None,
        min_price=None,
        max_price=None,
        in_stock=False,
        sort="default",
        page=1,
        limit=limit,
    )
    response.headers["Cache-Control"] = "public, max-age=60"
    showcase: list[ShowcaseProductOut] = []
    for product in sorted(products, key=lambda item: not item.is_featured):
        minimum = policy.minimum_quantity(product)
        available = not policy.stock_tracking_enabled or (product.stock_qty or 0) >= max(
            1, minimum
        )
        showcase.append(
            ShowcaseProductOut(
                id=product.id,
                name_uz=product.name_uz,
                name_ru=product.name_ru,
                price=product.price,
                old_price=product.old_price,
                image_url=_main_image_url(product),
                is_featured=product.is_featured,
                min_order_qty=minimum,
                available=available,
            )
        )
    return showcase


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int, session: AsyncSession = Depends(get_db, scope="function")
) -> ProductOut:
    product = await catalog_service.get_product(session, product_id, track_view=True)
    inventory_policy = await get_inventory_policy(session)
    return public_product_out(product, inventory_policy)


@router.get("/search", response_model=PageOut[ProductOut])
async def search_products(
    q: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=DEFAULT_CATALOG_PAGE_SIZE, ge=1, le=50),
    filters: catalog_service.CatalogFilters = Depends(_catalog_filters),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> PageOut[ProductOut]:
    inventory_policy = await get_inventory_policy(session)
    result = await catalog_service.list_public_products(
        session,
        query=q,
        filters=filters,
        page=page,
        limit=limit,
        inventory_policy=inventory_policy,
    )
    return _public_page(result, inventory_policy)

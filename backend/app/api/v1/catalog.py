from dataclasses import replace
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas.catalog import CategoryOut, ProductOut
from app.api.schemas.common import PageOut
from app.services import catalog_service
from app.services.common import DEFAULT_CATALOG_PAGE_SIZE, PUBLIC_CATALOG_PAGE_SIZE

router = APIRouter(prefix="/catalog", tags=["catalog"])


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
    parent_id: int | None = Query(default=None), session: AsyncSession = Depends(get_db)
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
    session: AsyncSession = Depends(get_db),
) -> PageOut[ProductOut]:
    result = await catalog_service.list_products(
        session, category_id, page=page, limit=limit, filters=options
    )
    return PageOut[ProductOut].from_page(result)


@router.get("/products", response_model=PageOut[ProductOut])
async def list_all_products(
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=PUBLIC_CATALOG_PAGE_SIZE, ge=1, le=50),
    filters: catalog_service.CatalogFilters = Depends(_catalog_filters),
    session: AsyncSession = Depends(get_db),
) -> PageOut[ProductOut]:
    result = await catalog_service.list_public_products(
        session, query=q, filters=filters, page=page, limit=limit
    )
    return PageOut[ProductOut].from_page(result)


@router.get("/featured", response_model=list[ProductOut])
async def list_featured_products(
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> list[ProductOut]:
    products = await catalog_service.list_featured_products(session, limit=limit)
    return [ProductOut.model_validate(product) for product in products]


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, session: AsyncSession = Depends(get_db)) -> ProductOut:
    product = await catalog_service.get_product(session, product_id, track_view=True)
    return ProductOut.model_validate(product)


@router.get("/search", response_model=PageOut[ProductOut])
async def search_products(
    q: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=DEFAULT_CATALOG_PAGE_SIZE, ge=1, le=50),
    filters: catalog_service.CatalogFilters = Depends(_catalog_filters),
    session: AsyncSession = Depends(get_db),
) -> PageOut[ProductOut]:
    result = await catalog_service.list_public_products(
        session, query=q, filters=filters, page=page, limit=limit
    )
    return PageOut[ProductOut].from_page(result)

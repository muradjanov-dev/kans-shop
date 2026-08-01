from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas.catalog import CategoryOut, ProductOut
from app.api.schemas.common import PageOut
from app.services import catalog_service
from app.services.common import DEFAULT_CATALOG_PAGE_SIZE

router = APIRouter(prefix="/catalog", tags=["catalog"])


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
    session: AsyncSession = Depends(get_db),
) -> PageOut[ProductOut]:
    result = await catalog_service.list_products(session, category_id, page=page, limit=limit)
    return PageOut[ProductOut].from_page(result)


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, session: AsyncSession = Depends(get_db)) -> ProductOut:
    product = await catalog_service.get_product(session, product_id, track_view=True)
    return ProductOut.model_validate(product)


@router.get("/search", response_model=PageOut[ProductOut])
async def search_products(
    q: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=DEFAULT_CATALOG_PAGE_SIZE, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> PageOut[ProductOut]:
    result = await catalog_service.search_products(session, q, page=page, limit=limit)
    return PageOut[ProductOut].from_page(result)

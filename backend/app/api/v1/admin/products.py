from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MANAGEMENT_ROLES, get_db, require_admin_roles
from app.api.schemas.admin import ProductCreateIn, ProductUpdateIn
from app.api.schemas.catalog import ProductOut
from app.api.schemas.common import PageOut
from app.core.config import settings
from app.core.exceptions import InvalidFileError, ProductNotFoundError, SkuAlreadyExistsError
from app.core.uploads import (
    ALLOWED_RECEIPT_MIME_TYPES,
    MAX_RECEIPT_SIZE_BYTES,
    MIME_EXTENSIONS,
)
from app.db.models.product import Product
from app.db.models.product_image import ProductImage
from app.db.repositories import category_repository, product_repository
from app.services.common import DEFAULT_CATALOG_PAGE_SIZE, Page

router = APIRouter(
    prefix="/admin/products",
    tags=["admin-products"],
    dependencies=[Depends(require_admin_roles(*MANAGEMENT_ROLES))],
)


async def _get_product_or_404(session: AsyncSession, product_id: int) -> Product:
    product = await product_repository.get_by_id(session, product_id)
    if product is None:
        raise ProductNotFoundError(f"Product {product_id} not found")
    return product


@router.get("", response_model=PageOut[ProductOut])
async def list_products(
    category_id: int = Query(...),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=DEFAULT_CATALOG_PAGE_SIZE, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> PageOut[ProductOut]:
    items, total = await product_repository.list_by_category(
        session, category_id, page=page, limit=limit, active_only=False
    )
    return PageOut[ProductOut].from_page(
        Page(items=items, total=total, page=page, limit=limit)
    )


@router.post("", response_model=ProductOut, status_code=201)
async def create_product(
    payload: ProductCreateIn, session: AsyncSession = Depends(get_db)
) -> ProductOut:
    if await product_repository.get_by_sku(session, payload.sku) is not None:
        raise SkuAlreadyExistsError(f"SKU {payload.sku} already exists")
    product = Product(**payload.model_dump())
    session.add(product)
    await session.flush()

    category = await category_repository.get_by_id(session, product.category_id)
    if category is not None:
        category.products_count = category.products_count + 1

    await session.refresh(product, attribute_names=["images"])
    return ProductOut.model_validate(product)


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int, payload: ProductUpdateIn, session: AsyncSession = Depends(get_db)
) -> ProductOut:
    product = await _get_product_or_404(session, product_id)
    changes = payload.model_dump(exclude_unset=True)
    new_sku = changes.get("sku")
    if new_sku and new_sku != product.sku:
        existing = await product_repository.get_by_sku(session, new_sku)
        if existing is not None and existing.id != product.id:
            raise SkuAlreadyExistsError(f"SKU {new_sku} already exists")

    new_category_id = changes.get("category_id")
    old_category_id = product.category_id
    if new_category_id is not None and new_category_id != old_category_id:
        old_category = await category_repository.get_by_id(session, old_category_id)
        if old_category is not None and old_category.products_count > 0:
            old_category.products_count = old_category.products_count - 1
        new_category = await category_repository.get_by_id(session, new_category_id)
        if new_category is not None:
            new_category.products_count = new_category.products_count + 1

    for field, value in changes.items():
        setattr(product, field, value)
    await session.flush()
    return ProductOut.model_validate(product)


@router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: int, session: AsyncSession = Depends(get_db)) -> None:
    product = await _get_product_or_404(session, product_id)
    category = await category_repository.get_by_id(session, product.category_id)
    if category is not None and category.products_count > 0:
        category.products_count = category.products_count - 1
    await session.delete(product)
    await session.flush()


@router.post("/{product_id}/images", response_model=ProductOut, status_code=201)
async def upload_product_image(
    product_id: int, file: UploadFile, session: AsyncSession = Depends(get_db)
) -> ProductOut:
    product = await _get_product_or_404(session, product_id)

    content_type = file.content_type or ""
    if content_type not in ALLOWED_RECEIPT_MIME_TYPES or content_type == "application/pdf":
        raise InvalidFileError(
            "Unsupported image type", details={"content_type": content_type}
        )
    data = await file.read()
    if len(data) > MAX_RECEIPT_SIZE_BYTES:
        raise InvalidFileError("File too large", details={"max_bytes": MAX_RECEIPT_SIZE_BYTES})

    product_dir = settings.media_root_path / "products" / str(product.id)
    product_dir.mkdir(parents=True, exist_ok=True)
    existing_count = len(product.images)
    ext = MIME_EXTENSIONS[content_type]
    destination = product_dir / f"{existing_count}.{ext}"
    destination.write_bytes(data)
    url = f"{settings.media_base_url}/products/{product.id}/{destination.name}"

    session.add(
        ProductImage(
            product_id=product.id,
            url=url,
            is_main=(existing_count == 0),
            sort_order=existing_count,
        )
    )
    await session.flush()
    await session.refresh(product, attribute_names=["images"])
    return ProductOut.model_validate(product)

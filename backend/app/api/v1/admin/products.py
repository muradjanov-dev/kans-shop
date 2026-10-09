from fastapi import APIRouter, Body, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MANAGEMENT_ROLES, get_current_admin, get_db, require_admin_roles
from app.api.schemas.admin import AdminProductOut, ProductCreateIn, ProductUpdateIn
from app.api.schemas.common import PageOut
from app.core.exceptions import InvalidFileError, ProductNotFoundError
from app.db.models.admin import Admin
from app.db.models.product import Product
from app.db.repositories import product_repository
from app.services import admin_catalog_service
from app.services.common import DEFAULT_CATALOG_PAGE_SIZE, Page

_MAX_IMAGE_BYTES = 5 * 1024 * 1024

router = APIRouter(
    prefix="/admin/products",
    tags=["admin-products"],
    dependencies=[Depends(require_admin_roles(*MANAGEMENT_ROLES))],
)


async def _load_product(session: AsyncSession, product_id: int) -> Product:
    product = await product_repository.get_by_id(session, product_id)
    if product is None:
        raise ProductNotFoundError(f"Product {product_id} not found")
    return product


async def _read_image(file: UploadFile) -> bytes:
    content = await file.read(_MAX_IMAGE_BYTES + 1)
    if len(content) > _MAX_IMAGE_BYTES:
        raise InvalidFileError("File too large", details={"max_bytes": _MAX_IMAGE_BYTES})
    return content


@router.get("", response_model=PageOut[AdminProductOut])
async def list_products(
    category_id: int = Query(...),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=DEFAULT_CATALOG_PAGE_SIZE, ge=1, le=100),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> PageOut[AdminProductOut]:
    items, total = await product_repository.list_by_category(
        session, category_id, page=page, limit=limit, active_only=False
    )
    return PageOut[AdminProductOut].from_page(
        Page(items=items, total=total, page=page, limit=limit)
    )


@router.post("", response_model=AdminProductOut, status_code=201)
async def create_product(
    payload: ProductCreateIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> AdminProductOut:
    product = await admin_catalog_service.create_product(
        session, admin_id=admin.id, values=payload
    )
    await session.refresh(product, attribute_names=["images"])
    return AdminProductOut.model_validate(product)


@router.patch("/{product_id}", response_model=AdminProductOut)
async def update_product(
    product_id: int,
    payload: ProductUpdateIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> AdminProductOut:
    product = await admin_catalog_service.update_product(
        session,
        admin_id=admin.id,
        product_id=product_id,
        expected_edit_version=payload.expected_edit_version,
        changes=payload,
    )
    return AdminProductOut.model_validate(product)


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: int,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> None:
    await admin_catalog_service.delete_product(
        session, admin_id=admin.id, product_id=product_id
    )


@router.post("/{product_id}/images", response_model=AdminProductOut, status_code=201)
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> AdminProductOut:
    await admin_catalog_service.add_product_image(
        session,
        admin_id=admin.id,
        product_id=product_id,
        content=await _read_image(file),
        content_type=file.content_type or "",
    )
    return AdminProductOut.model_validate(await _load_product(session, product_id))


@router.patch("/{product_id}/images/{image_id}", response_model=AdminProductOut)
async def update_product_image(
    product_id: int,
    image_id: int,
    is_main: bool = Body(...),
    sort_order: int = Body(..., ge=0),
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> AdminProductOut:
    await admin_catalog_service.set_product_image(
        session,
        admin_id=admin.id,
        product_id=product_id,
        image_id=image_id,
        is_main=is_main,
        sort_order=sort_order,
    )
    return AdminProductOut.model_validate(await _load_product(session, product_id))


@router.delete("/{product_id}/images/{image_id}", response_model=AdminProductOut)
async def delete_product_image(
    product_id: int,
    image_id: int,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> AdminProductOut:
    product = await admin_catalog_service.delete_product_image(
        session, admin_id=admin.id, product_id=product_id, image_id=image_id
    )
    return AdminProductOut.model_validate(product)

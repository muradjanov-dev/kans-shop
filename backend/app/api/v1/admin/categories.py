from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MANAGEMENT_ROLES, get_current_admin, get_db, require_admin_roles
from app.api.schemas.admin import CategoryCreateIn, CategoryMoveIn, CategoryUpdateIn
from app.api.schemas.catalog import CategoryOut
from app.core.exceptions import InvalidFileError
from app.db.models.admin import Admin
from app.db.repositories import category_repository
from app.services import admin_catalog_service

_MAX_IMAGE_BYTES = 5 * 1024 * 1024

router = APIRouter(
    prefix="/admin/categories",
    tags=["admin-categories"],
    dependencies=[Depends(require_admin_roles(*MANAGEMENT_ROLES))],
)


async def _read_image(file: UploadFile) -> bytes:
    content = await file.read(_MAX_IMAGE_BYTES + 1)
    if len(content) > _MAX_IMAGE_BYTES:
        raise InvalidFileError("File too large", details={"max_bytes": _MAX_IMAGE_BYTES})
    return content


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    session: AsyncSession = Depends(get_db, scope="function"),
) -> list[CategoryOut]:
    categories = await category_repository.list_all(session, active_only=False)
    return [CategoryOut.model_validate(category) for category in categories]


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(
    payload: CategoryCreateIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> CategoryOut:
    category = await admin_catalog_service.create_category(
        session, admin_id=admin.id, values=payload
    )
    return CategoryOut.model_validate(category)


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int,
    payload: CategoryUpdateIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> CategoryOut:
    category = await admin_catalog_service.update_category(
        session,
        admin_id=admin.id,
        category_id=category_id,
        expected_edit_version=payload.expected_edit_version,
        changes=payload,
    )
    return CategoryOut.model_validate(category)


@router.patch("/{category_id}/move", response_model=CategoryOut)
async def move_category(
    category_id: int,
    payload: CategoryMoveIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> CategoryOut:
    category = await admin_catalog_service.move_category(
        session,
        admin_id=admin.id,
        category_id=category_id,
        parent_id=payload.parent_id,
        expected_edit_version=payload.expected_edit_version,
    )
    return CategoryOut.model_validate(category)


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> None:
    await admin_catalog_service.delete_category(
        session, admin_id=admin.id, category_id=category_id
    )


@router.put("/{category_id}/image", response_model=CategoryOut)
async def upload_category_image(
    category_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> CategoryOut:
    category = await admin_catalog_service.set_category_image(
        session,
        admin_id=admin.id,
        category_id=category_id,
        content=await _read_image(file),
        content_type=file.content_type or "",
    )
    return CategoryOut.model_validate(category)


@router.delete("/{category_id}/image", response_model=CategoryOut)
async def delete_category_image(
    category_id: int,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> CategoryOut:
    category = await admin_catalog_service.delete_category_image(
        session, admin_id=admin.id, category_id=category_id
    )
    return CategoryOut.model_validate(category)

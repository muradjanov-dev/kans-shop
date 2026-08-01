import re
import unicodedata

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MANAGEMENT_ROLES, get_db, require_admin_roles
from app.api.schemas.admin import CategoryCreateIn, CategoryUpdateIn
from app.api.schemas.catalog import CategoryOut
from app.core.exceptions import CategoryInUseError, CategoryNotFoundError
from app.db.models.category import Category
from app.db.repositories import category_repository, product_repository

router = APIRouter(
    prefix="/admin/categories",
    tags=["admin-categories"],
    dependencies=[Depends(require_admin_roles(*MANAGEMENT_ROLES))],
)


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug or "category"


async def _unique_slug(session: AsyncSession, base: str) -> str:
    slug = base
    suffix = 2
    while await category_repository.get_by_slug(session, slug) is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


@router.get("", response_model=list[CategoryOut])
async def list_categories(session: AsyncSession = Depends(get_db)) -> list[CategoryOut]:
    categories = await category_repository.list_all(session, active_only=False)
    return [CategoryOut.model_validate(c) for c in categories]


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(
    payload: CategoryCreateIn,
    session: AsyncSession = Depends(get_db),
) -> CategoryOut:
    slug = await _unique_slug(session, _slugify(payload.name_uz))
    category = Category(
        name_uz=payload.name_uz,
        name_ru=payload.name_ru,
        slug=slug,
        parent_id=payload.parent_id,
    )
    session.add(category)
    await session.flush()
    return CategoryOut.model_validate(category)


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int, payload: CategoryUpdateIn, session: AsyncSession = Depends(get_db)
) -> CategoryOut:
    category = await category_repository.get_by_id(session, category_id)
    if category is None:
        raise CategoryNotFoundError(f"Category {category_id} not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    await session.flush()
    return CategoryOut.model_validate(category)


@router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: int, session: AsyncSession = Depends(get_db)) -> None:
    category = await category_repository.get_by_id(session, category_id)
    if category is None:
        raise CategoryNotFoundError(f"Category {category_id} not found")
    _items, product_count = await product_repository.list_by_category(
        session, category_id, page=1, limit=1, active_only=False
    )
    children = await category_repository.list_children(session, category_id, active_only=False)
    if product_count or children:
        raise CategoryInUseError("Category still has products or subcategories")
    await session.delete(category)
    await session.flush()

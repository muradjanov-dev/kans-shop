"""Shared transactional catalog writes for the admin API and Telegram bot."""

from __future__ import annotations

import re
import unicodedata
import warnings
from decimal import Decimal
from io import BytesIO
from urllib.parse import urlsplit
from uuid import uuid4

from PIL import Image
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.admin import (
    CategoryCreateIn,
    CategoryUpdateIn,
    ProductCreateIn,
    ProductUpdateIn,
)
from app.core.config import settings
from app.core.exceptions import (
    CatalogEditConflictError,
    CategoryInUseError,
    CategoryNotFoundError,
    InvalidFileError,
    ProductNotFoundError,
    SkuAlreadyExistsError,
)
from app.db.models.admin import Admin
from app.db.models.category import Category
from app.db.models.enums import AdminRole
from app.db.models.product import Product
from app.db.models.product_image import ProductImage
from app.db.repositories import category_repository, product_repository
from app.services.admin_actor_service import load_live_admin
from app.services.admin_audit_service import write_audit_event

_MANAGEMENT_ROLES = frozenset({AdminRole.SUPERADMIN, AdminRole.MANAGER})
_CATEGORY_TREE_LOCK = 2_026_100_904
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_IMAGE_TYPES = {
    "image/jpeg": ("JPEG", "jpg"),
    "image/png": ("PNG", "png"),
    "image/webp": ("WEBP", "webp"),
}


async def _lock_category_tree(session: AsyncSession) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": _CATEGORY_TREE_LOCK}
    )


async def _load_actor(session: AsyncSession, admin_id: int) -> Admin:
    return await load_live_admin(
        session,
        admin_id=admin_id,
        allowed_roles=_MANAGEMENT_ROLES,
        lock=True,
    )


async def _audit(
    session: AsyncSession,
    *,
    admin_id: int,
    action: str,
    resource_type: str,
    resource_id: int,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> None:
    await write_audit_event(
        session,
        admin_id=admin_id,
        action=action,
        entity=resource_type,
        entity_id=resource_id,
        request_id=uuid4().hex,
        before=before,
        after=after,
    )


def _product_snapshot(product: Product) -> dict[str, object]:
    return {
        "id": product.id,
        "category_id": product.category_id,
        "sku": product.sku,
        "barcode": product.barcode,
        "name_uz": product.name_uz,
        "name_ru": product.name_ru,
        "price": product.price,
        "old_price": product.old_price,
        "stock_qty": product.stock_qty,
        "min_order_qty": product.min_order_qty,
        "is_active": product.is_active,
        "is_featured": product.is_featured,
        "sort_order": product.sort_order,
        "lot_url": product.lot_url,
        "edit_version": product.edit_version,
    }


def _category_snapshot(category: Category) -> dict[str, object]:
    return {
        "id": category.id,
        "parent_id": category.parent_id,
        "slug": category.slug,
        "name_uz": category.name_uz,
        "name_ru": category.name_ru,
        "description_uz": category.description_uz,
        "description_ru": category.description_ru,
        "image_url": category.image_url,
        "image_file_id": category.image_file_id,
        "sort_order": category.sort_order,
        "is_active": category.is_active,
        "products_count": category.products_count,
        "edit_version": category.edit_version,
    }


def _check_product_values(values: dict[str, object]) -> None:
    price = values.get("price")
    if "price" in values and (price is None or not isinstance(price, Decimal) or price <= 0):
        raise ValueError("price must be greater than zero")
    stock_qty = values.get("stock_qty")
    if "stock_qty" in values and (
        stock_qty is None or not isinstance(stock_qty, int) or stock_qty < 0
    ):
        raise ValueError("stock_qty must be nonnegative")
    min_order_qty = values.get("min_order_qty")
    if "min_order_qty" in values and (
        min_order_qty is None or not isinstance(min_order_qty, int) or min_order_qty < 1
    ):
        raise ValueError("min_order_qty must be at least one")
    if "sku" in values and (values["sku"] is None or not str(values["sku"]).strip()):
        raise ValueError("sku must not be empty")
    if "lot_url" in values and values["lot_url"] is not None:
        parsed = urlsplit(str(values["lot_url"]))
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("lot_url must be an HTTPS URL")


def _slugify(text_value: str) -> str:
    normalized = unicodedata.normalize("NFKD", text_value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug or "category"


async def _unique_slug(session: AsyncSession, base: str) -> str:
    slug = base
    suffix = 2
    while await category_repository.get_by_slug(session, slug) is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


async def _locked_category_tree(session: AsyncSession) -> dict[int, Category]:
    stmt = (
        select(Category)
        .order_by(Category.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    categories = (await session.scalars(stmt)).all()
    return {category.id: category for category in categories}


def _check_parent_change(
    categories: dict[int, Category], category: Category, parent_id: int | None
) -> None:
    if parent_id == category.id:
        raise CatalogEditConflictError("A category cannot be its own parent")
    if parent_id is not None and parent_id not in categories:
        raise CategoryNotFoundError(f"Category {parent_id} not found")

    seen: set[int] = set()
    current_id = parent_id
    while current_id is not None:
        if current_id == category.id:
            raise CatalogEditConflictError("A category cannot be moved below its descendant")
        if current_id in seen:
            raise CatalogEditConflictError("The category tree already contains a cycle")
        seen.add(current_id)
        parent = categories.get(current_id)
        current_id = parent.parent_id if parent is not None else None


async def _load_locked_product(session: AsyncSession, product_id: int) -> Product:
    product = await product_repository.get_by_id(session, product_id, for_update=True)
    if product is None:
        raise ProductNotFoundError(f"Product {product_id} not found")
    return product


async def _load_locked_category(session: AsyncSession, category_id: int) -> Category:
    category = await session.scalar(
        select(Category)
        .where(Category.id == category_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if category is None:
        raise CategoryNotFoundError(f"Category {category_id} not found")
    return category


async def _check_edit_version(entity: Product | Category, expected: int) -> None:
    if entity.edit_version != expected:
        raise CatalogEditConflictError(
            "Catalog item changed since it was loaded",
            details={
                "expected_edit_version": expected,
                "current_edit_version": entity.edit_version,
            },
        )


async def create_product(
    session: AsyncSession, *, admin_id: int, values: ProductCreateIn
) -> Product:
    await _lock_category_tree(session)
    await _load_actor(session, admin_id)
    category = await _load_locked_category(session, values.category_id)
    data = values.model_dump()
    _check_product_values(data)
    if await product_repository.get_by_sku(session, values.sku) is not None:
        raise SkuAlreadyExistsError(f"SKU {values.sku} already exists")

    product = Product(**data)
    session.add(product)
    try:
        await session.flush()
    except IntegrityError as exc:
        if "sku" in str(exc).lower():
            raise SkuAlreadyExistsError(f"SKU {values.sku} already exists") from exc
        raise
    category.products_count += 1
    await session.flush()
    await _audit(
        session,
        admin_id=admin_id,
        action="create",
        resource_type="product",
        resource_id=product.id,
        before=None,
        after=_product_snapshot(product),
    )
    return product


async def update_product(
    session: AsyncSession,
    *,
    admin_id: int,
    product_id: int,
    expected_edit_version: int,
    changes: ProductUpdateIn,
) -> Product:
    await _lock_category_tree(session)
    await _load_actor(session, admin_id)
    product = await _load_locked_product(session, product_id)
    await _check_edit_version(product, expected_edit_version)
    updates = changes.model_dump(exclude_unset=True, exclude={"expected_edit_version"})
    _check_product_values(updates)
    if "category_id" in updates and updates["category_id"] is None:
        raise ValueError("category_id cannot be cleared")
    updates = {
        field: value for field, value in updates.items() if getattr(product, field) != value
    }
    if not updates:
        await session.refresh(product, attribute_names=["images"])
        return product

    new_sku = updates.get("sku")
    if new_sku and new_sku != product.sku:
        existing = await product_repository.get_by_sku(session, str(new_sku))
        if existing is not None and existing.id != product.id:
            raise SkuAlreadyExistsError(f"SKU {new_sku} already exists")

    old_category_id = product.category_id
    new_category_id = updates.get("category_id", old_category_id)
    categories: dict[int, Category] = {}
    if new_category_id != old_category_id:
        ids = sorted({old_category_id, int(new_category_id)})
        rows = (
            await session.scalars(
                select(Category)
                .where(Category.id.in_(ids))
                .order_by(Category.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        categories = {category.id: category for category in rows}
        if int(new_category_id) not in categories:
            raise CategoryNotFoundError(f"Category {new_category_id} not found")

    before = _product_snapshot(product)
    for field, value in updates.items():
        setattr(product, field, value)
    if new_category_id != old_category_id:
        categories[old_category_id].products_count = max(
            0, categories[old_category_id].products_count - 1
        )
        categories[int(new_category_id)].products_count += 1
    product.edit_version += 1
    try:
        await session.flush()
    except IntegrityError as exc:
        if "sku" in str(exc).lower():
            raise SkuAlreadyExistsError(f"SKU {new_sku} already exists") from exc
        raise
    await session.refresh(product, attribute_names=["images"])
    await _audit(
        session,
        admin_id=admin_id,
        action="update",
        resource_type="product",
        resource_id=product.id,
        before=before,
        after=_product_snapshot(product),
    )
    return product


async def delete_product(session: AsyncSession, *, admin_id: int, product_id: int) -> None:
    await _lock_category_tree(session)
    await _load_actor(session, admin_id)
    product = await _load_locked_product(session, product_id)
    category = await _load_locked_category(session, product.category_id)
    snapshot = _product_snapshot(product)
    category.products_count = max(0, category.products_count - 1)
    await session.delete(product)
    await session.flush()
    await _audit(
        session,
        admin_id=admin_id,
        action="delete",
        resource_type="product",
        resource_id=product_id,
        before=snapshot,
        after=None,
    )


async def adjust_product_stock(
    session: AsyncSession, *, admin_id: int, product_id: int, delta: int
) -> Product:
    await _lock_category_tree(session)
    await _load_actor(session, admin_id)
    product = await _load_locked_product(session, product_id)
    adjustment = max(delta, -product.stock_qty)
    if adjustment:
        before = _product_snapshot(product)
        await product_repository.adjust_stock(session, product, adjustment)
        await _audit(
            session,
            admin_id=admin_id,
            action="stock_adjust",
            resource_type="product",
            resource_id=product_id,
            before=before,
            after=_product_snapshot(product),
        )
    await session.refresh(product, attribute_names=["images"])
    return product


async def create_category(
    session: AsyncSession, *, admin_id: int, values: CategoryCreateIn
) -> Category:
    await _lock_category_tree(session)
    await _load_actor(session, admin_id)
    if values.parent_id is not None:
        await _load_locked_category(session, values.parent_id)
    slug = await _unique_slug(session, _slugify(values.name_uz))
    category = Category(
        name_uz=values.name_uz,
        name_ru=values.name_ru,
        slug=slug,
        parent_id=values.parent_id,
        description_uz=values.description_uz,
        description_ru=values.description_ru,
        sort_order=values.sort_order,
    )
    session.add(category)
    await session.flush()
    await _audit(
        session,
        admin_id=admin_id,
        action="create",
        resource_type="category",
        resource_id=category.id,
        before=None,
        after=_category_snapshot(category),
    )
    return category


async def _update_category(
    session: AsyncSession,
    *,
    admin_id: int,
    category_id: int,
    expected_edit_version: int,
    updates: dict[str, object],
) -> Category:
    await _lock_category_tree(session)
    await _load_actor(session, admin_id)
    categories = await _locked_category_tree(session)
    category = categories.get(category_id)
    if category is None:
        raise CategoryNotFoundError(f"Category {category_id} not found")
    await _check_edit_version(category, expected_edit_version)
    if "parent_id" in updates:
        parent_id = updates["parent_id"]
        if parent_id is not None and not isinstance(parent_id, int):
            raise ValueError("parent_id must be an integer or null")
        _check_parent_change(categories, category, parent_id)
    updates = {
        field: value for field, value in updates.items() if getattr(category, field) != value
    }
    if not updates:
        return category
    before = _category_snapshot(category)
    for field, value in updates.items():
        setattr(category, field, value)
    category.edit_version += 1
    await session.flush()
    await _audit(
        session,
        admin_id=admin_id,
        action="update",
        resource_type="category",
        resource_id=category.id,
        before=before,
        after=_category_snapshot(category),
    )
    return category


async def update_category(
    session: AsyncSession,
    *,
    admin_id: int,
    category_id: int,
    expected_edit_version: int,
    changes: CategoryUpdateIn,
) -> Category:
    updates = changes.model_dump(exclude_unset=True, exclude={"expected_edit_version"})
    return await _update_category(
        session,
        admin_id=admin_id,
        category_id=category_id,
        expected_edit_version=expected_edit_version,
        updates=updates,
    )


async def move_category(
    session: AsyncSession,
    *,
    admin_id: int,
    category_id: int,
    parent_id: int | None,
    expected_edit_version: int,
) -> Category:
    return await _update_category(
        session,
        admin_id=admin_id,
        category_id=category_id,
        expected_edit_version=expected_edit_version,
        updates={"parent_id": parent_id},
    )


async def delete_category(session: AsyncSession, *, admin_id: int, category_id: int) -> None:
    await _lock_category_tree(session)
    await _load_actor(session, admin_id)
    categories = await _locked_category_tree(session)
    category = categories.get(category_id)
    if category is None:
        raise CategoryNotFoundError(f"Category {category_id} not found")
    product_count = await session.scalar(
        select(func.count()).select_from(Product).where(Product.category_id == category_id)
    )
    has_children = any(child.parent_id == category_id for child in categories.values())
    if product_count or has_children:
        raise CategoryInUseError("Category still has products or subcategories")
    before = _category_snapshot(category)
    await session.delete(category)
    await session.flush()
    await _audit(
        session,
        admin_id=admin_id,
        action="delete",
        resource_type="category",
        resource_id=category_id,
        before=before,
        after=None,
    )


def _validated_image(content: bytes, content_type: str) -> tuple[str, str]:
    if content_type not in _IMAGE_TYPES:
        raise InvalidFileError(
            "Unsupported image type", details={"content_type": content_type}
        )
    if not content or len(content) > _MAX_IMAGE_BYTES:
        raise InvalidFileError(
            "File too large or empty", details={"max_bytes": _MAX_IMAGE_BYTES}
        )
    expected_format, extension = _IMAGE_TYPES[content_type]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                actual_format = image.format
                image.verify()
            with Image.open(BytesIO(content)) as image:
                image.load()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        ValueError,
    ) as exc:
        raise InvalidFileError("Image content is invalid") from exc
    if actual_format != expected_format:
        raise InvalidFileError(
            "Image content does not match its media type",
            details={"content_type": content_type},
        )
    return expected_format, extension


def _store_public_image(
    *, owner_type: str, owner_id: int, content: bytes, extension: str
) -> str:
    directory = settings.media_root_path / owner_type / str(owner_id)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.{extension}"
    path = directory / filename
    with path.open("xb") as output:
        output.write(content)
    return f"{settings.media_base_url.rstrip('/')}/{owner_type}/{owner_id}/{filename}"


async def add_product_image(
    session: AsyncSession,
    *,
    admin_id: int,
    product_id: int,
    content: bytes,
    content_type: str,
) -> ProductImage:
    _format, extension = _validated_image(content, content_type)
    await _lock_category_tree(session)
    await _load_actor(session, admin_id)
    product = await _load_locked_product(session, product_id)
    images = (
        await session.scalars(
            select(ProductImage)
            .where(ProductImage.product_id == product_id)
            .order_by(ProductImage.sort_order, ProductImage.id)
            .with_for_update()
        )
    ).all()
    before = _product_snapshot(product)
    url = _store_public_image(
        owner_type="products", owner_id=product_id, content=content, extension=extension
    )
    image = ProductImage(
        product_id=product_id,
        url=url,
        is_main=not any(current.is_main for current in images),
        sort_order=len(images),
    )
    session.add(image)
    product.edit_version += 1
    await session.flush()
    await _audit(
        session,
        admin_id=admin_id,
        action="image_add",
        resource_type="product",
        resource_id=product_id,
        before=before,
        after={**_product_snapshot(product), "image_id": image.id},
    )
    return image


async def set_product_image(
    session: AsyncSession,
    *,
    admin_id: int,
    product_id: int,
    image_id: int,
    is_main: bool,
    sort_order: int,
) -> ProductImage:
    if sort_order < 0:
        raise ValueError("sort_order must be nonnegative")
    await _lock_category_tree(session)
    await _load_actor(session, admin_id)
    product = await _load_locked_product(session, product_id)
    images = list(
        (
            await session.scalars(
                select(ProductImage)
                .where(ProductImage.product_id == product_id)
                .order_by(ProductImage.sort_order, ProductImage.id)
                .with_for_update()
            )
        ).all()
    )
    image = next((current for current in images if current.id == image_id), None)
    if image is None:
        raise ProductNotFoundError(f"Image {image_id} does not belong to product {product_id}")

    before = _product_snapshot(product)
    original_order = [(current.id, current.sort_order, current.is_main) for current in images]
    images.remove(image)
    images.insert(min(sort_order, len(images)), image)
    for index, current in enumerate(images):
        current.sort_order = index
    if is_main:
        for current in images:
            current.is_main = current.id == image.id
    elif image.is_main:
        replacement = next((current for current in images if current.id != image.id), image)
        for current in images:
            current.is_main = current.id == replacement.id

    final_order = [(current.id, current.sort_order, current.is_main) for current in images]
    if final_order != original_order:
        product.edit_version += 1
        await session.flush()
        await _audit(
            session,
            admin_id=admin_id,
            action="image_update",
            resource_type="product",
            resource_id=product_id,
            before=before,
            after={**_product_snapshot(product), "images": final_order},
        )
    return image


async def delete_product_image(
    session: AsyncSession,
    *,
    admin_id: int,
    product_id: int,
    image_id: int,
) -> Product:
    await _lock_category_tree(session)
    await _load_actor(session, admin_id)
    product = await _load_locked_product(session, product_id)
    images = list(
        (
            await session.scalars(
                select(ProductImage)
                .where(ProductImage.product_id == product_id)
                .order_by(ProductImage.sort_order, ProductImage.id)
                .with_for_update()
            )
        ).all()
    )
    image = next((current for current in images if current.id == image_id), None)
    if image is None:
        raise ProductNotFoundError(f"Image {image_id} does not belong to product {product_id}")
    before = _product_snapshot(product)
    was_main = image.is_main
    images.remove(image)
    await session.delete(image)
    if images:
        if was_main:
            images[0].is_main = True
        for index, current in enumerate(images):
            current.sort_order = index
            if was_main and index > 0:
                current.is_main = False
    product.edit_version += 1
    await session.flush()
    await _audit(
        session,
        admin_id=admin_id,
        action="image_delete",
        resource_type="product",
        resource_id=product_id,
        before=before,
        after={**_product_snapshot(product), "deleted_image_id": image_id},
    )
    await session.refresh(product, attribute_names=["images"])
    return product


async def set_category_image(
    session: AsyncSession,
    *,
    admin_id: int,
    category_id: int,
    content: bytes,
    content_type: str,
) -> Category:
    _format, extension = _validated_image(content, content_type)
    await _lock_category_tree(session)
    await _load_actor(session, admin_id)
    category = await _load_locked_category(session, category_id)
    before = _category_snapshot(category)
    category.image_url = _store_public_image(
        owner_type="categories", owner_id=category_id, content=content, extension=extension
    )
    category.image_file_id = None
    category.edit_version += 1
    await session.flush()
    await _audit(
        session,
        admin_id=admin_id,
        action="image_update",
        resource_type="category",
        resource_id=category_id,
        before=before,
        after=_category_snapshot(category),
    )
    return category


async def delete_category_image(
    session: AsyncSession, *, admin_id: int, category_id: int
) -> Category:
    await _lock_category_tree(session)
    await _load_actor(session, admin_id)
    category = await _load_locked_category(session, category_id)
    before = _category_snapshot(category)
    if category.image_url is not None or category.image_file_id is not None:
        category.image_url = None
        category.image_file_id = None
        category.edit_version += 1
        await session.flush()
        await _audit(
            session,
            admin_id=admin_id,
            action="image_delete",
            resource_type="category",
            resource_id=category_id,
            before=before,
            after=_category_snapshot(category),
        )
    return category

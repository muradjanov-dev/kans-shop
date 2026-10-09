import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from secrets import token_hex, token_urlsafe

import pytest
from fastapi.routing import APIRoute
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.admin_security import ADMIN_COOKIE_NAME
from app.api.deps import get_db
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
    ForbiddenError,
    SkuAlreadyExistsError,
)
from app.db.models.admin import Admin
from app.db.models.admin_audit_event import AdminAuditEvent
from app.db.models.admin_session import AdminSession
from app.db.models.cart import Cart, CartItem
from app.db.models.category import Category
from app.db.models.enums import AdminRole, OrderType, PaymentMethod, ProductUnit
from app.db.models.product import Product
from app.db.models.product_image import ProductImage
from app.db.models.user import User
from app.db.repositories import product_repository, setting_repository
from app.services import admin_catalog_service, order_service, purchase_service
from tests.api_helpers import ApiCase, make_api_case


def _product_payload(**changes: object) -> dict[str, object]:
    return {
        "category_id": 1,
        "name_uz": "Daftar",
        "name_ru": "Тетрадь",
        "sku": "NOTE-1",
        "price": Decimal("5000"),
        "stock_qty": 3,
        "unit": ProductUnit.DONA,
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"price": Decimal("0")},
        {"price": Decimal("-1")},
        {"stock_qty": -1},
        {"min_order_qty": 0},
        {"lot_url": "http://example.com/lot"},
        {"lot_url": "javascript:alert(1)"},
    ],
)
def test_product_catalog_validation_rejects_invalid_values(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ProductCreateIn.model_validate(_product_payload(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"price": Decimal("0")},
        {"stock_qty": -1},
        {"min_order_qty": 0},
        {"lot_url": "http://example.com/lot"},
    ],
)
def test_product_update_validation_rejects_invalid_values(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ProductUpdateIn.model_validate({"expected_edit_version": 0, **changes})


@pytest.mark.asyncio
async def test_product_catalog_validation(
    db_session: AsyncSession, admin, category, product
) -> None:
    values = ProductCreateIn(
        category_id=category.id,
        name_uz="Duplicate",
        name_ru="Duplicate",
        sku=product.sku,
        price=Decimal("100"),
        unit=ProductUnit.DONA,
    )

    with pytest.raises(SkuAlreadyExistsError):
        await admin_catalog_service.create_product(
            db_session, admin_id=admin.id, values=values
        )

    assert category.products_count == 0


@pytest.mark.asyncio
async def test_shared_catalog_service_rechecks_live_actor(
    db_session: AsyncSession, admin, category
) -> None:
    await db_session.execute(
        update(Admin)
        .where(Admin.id == admin.id)
        .values(role=AdminRole.OPERATOR)
        .execution_options(synchronize_session=False)
    )
    values = ProductCreateIn(
        category_id=category.id,
        name_uz="Live actor product",
        name_ru="Live actor product",
        sku="LIVE-ACTOR-PRODUCT",
        price=Decimal("100"),
        unit=ProductUnit.DONA,
    )

    with pytest.raises(ForbiddenError):
        await admin_catalog_service.create_product(
            db_session, admin_id=admin.id, values=values
        )


@pytest.mark.asyncio
async def test_product_audit_records_description_and_unit_changes(
    db_session: AsyncSession, admin, product
) -> None:
    changes = ProductUpdateIn(
        expected_edit_version=product.edit_version,
        description_uz="New Uzbek description",
        unit=ProductUnit.QUTI,
    )
    await admin_catalog_service.update_product(
        db_session,
        admin_id=admin.id,
        product_id=product.id,
        expected_edit_version=product.edit_version,
        changes=changes,
    )
    event = await db_session.scalar(
        select(AdminAuditEvent)
        .where(
            AdminAuditEvent.actor_admin_id == admin.id,
            AdminAuditEvent.resource_type == "product",
            AdminAuditEvent.resource_id == str(product.id),
            AdminAuditEvent.action == "update",
        )
        .order_by(AdminAuditEvent.id.desc())
    )
    assert event is not None
    assert event.before_json is not None and event.after_json is not None
    assert event.before_json["description_uz"] is None
    assert event.after_json["description_uz"] == "New Uzbek description"
    assert event.before_json["unit"] == ProductUnit.DONA.value
    assert event.after_json["unit"] == ProductUnit.QUTI.value


def test_catalog_routes_use_function_scoped_db_dependencies() -> None:
    from app.api.v1.admin import categories, products

    for router in (categories.router, products.router):
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            dependencies = [dep for dep in route.dependant.dependencies if dep.call is get_db]
            assert len(dependencies) == 1, route.path
            assert dependencies[0].scope == "function", route.path


@pytest.mark.asyncio
async def test_category_move_requires_parent_field_but_accepts_null_root(
    test_engine: AsyncEngine,
) -> None:
    suffix = token_hex(4)
    async with (
        make_api_case(test_engine, base_url="https://testserver") as case,
        _admin_cookie(case) as (_admin, csrf_token),
    ):
        async with case.session_maker() as session:
            parent = Category(
                name_uz="Move parent",
                name_ru="Move parent",
                slug=f"move-parent-{suffix}",
            )
            session.add(parent)
            await session.flush()
            child = Category(
                name_uz="Move child",
                name_ru="Move child",
                slug=f"move-child-{suffix}",
                parent_id=parent.id,
            )
            session.add(child)
            await session.commit()
            parent_id, child_id = parent.id, child.id

        headers = {
            "Origin": settings.webapp_origin,
            "X-CSRF-Token": csrf_token,
        }
        try:
            missing_parent = await case.client.patch(
                f"/api/v1/admin/categories/{child_id}/move",
                headers=headers,
                json={"expected_edit_version": 0},
            )
            assert missing_parent.status_code == 422
            async with case.session_maker() as session:
                child_after_missing = await session.get(Category, child_id)
            assert child_after_missing is not None
            assert child_after_missing.parent_id == parent_id

            move_to_root = await case.client.patch(
                f"/api/v1/admin/categories/{child_id}/move",
                headers=headers,
                json={"expected_edit_version": 0, "parent_id": None},
            )
            assert move_to_root.status_code == 200
            assert move_to_root.json()["parent_id"] is None
        finally:
            async with case.session_maker() as session:
                await session.execute(delete(Category).where(Category.id == child_id))
                await session.execute(delete(Category).where(Category.id == parent_id))
                await session.commit()


@pytest.mark.asyncio
async def test_checkout_stock_write_bumps_product_version(
    db_session: AsyncSession, admin, user: User, product: Product
) -> None:
    initial_version = product.edit_version
    cart = Cart(user_id=user.id, is_active=True)
    db_session.add(cart)
    await db_session.flush()
    db_session.add(
        CartItem(
            cart_id=cart.id,
            product_id=product.id,
            quantity=2,
            price_snapshot=product.price,
        )
    )
    await db_session.flush()
    for key, value in {"is_shop_open": True, "min_order_amount": 0}.items():
        await setting_repository.set_value(db_session, key, value)

    checkout = await purchase_service.submit_checkout(
        db_session,
        user_id=user.id,
        command=purchase_service.CheckoutCommand(
            order_type=OrderType.PICKUP,
            customer_name="Test Buyer",
            customer_phone="+998901234567",
            payment_method=PaymentMethod.CASH,
        ),
        checkout_key=None,
        expected_quote=None,
        expected_total=None,
        source="bot",
        lang="uz",
    )
    await db_session.refresh(product)
    stock_after_checkout = product.stock_qty

    stale_changes = ProductUpdateIn.model_validate(
        {"expected_edit_version": initial_version, "stock_qty": 9}
    )
    with pytest.raises(CatalogEditConflictError):
        await admin_catalog_service.update_product(
            db_session,
            admin_id=admin.id,
            product_id=product.id,
            expected_edit_version=initial_version,
            changes=stale_changes,
        )

    await db_session.refresh(product)
    assert stock_after_checkout == 8
    assert product.stock_qty == stock_after_checkout
    assert product.edit_version == initial_version + 1

    await order_service.cancel_order(
        db_session, checkout.order, admin_id=admin.id, reason="test"
    )
    await db_session.refresh(product)
    assert product.stock_qty == 10
    assert product.edit_version == initial_version + 2


@pytest.mark.asyncio
async def test_product_view_count_does_not_change_edit_version(
    db_session: AsyncSession, product
) -> None:
    initial_version = product.edit_version
    await product_repository.increment_views(db_session, product)
    await db_session.refresh(product)

    assert product.views_count == 1
    assert product.edit_version == initial_version


@asynccontextmanager
async def _admin_cookie(case: ApiCase) -> AsyncIterator[tuple[Admin, str]]:
    raw_cookie = token_urlsafe(32)
    csrf_token = token_urlsafe(64)
    now = datetime.now(UTC)
    async with case.session_maker() as session:
        admin = Admin(
            telegram_id=9_100_000_000_000_001,
            full_name="Catalog API test admin",
            role=AdminRole.SUPERADMIN,
        )
        session.add(admin)
        await session.flush()
        session.add(
            AdminSession(
                admin_id=admin.id,
                token_hash=sha256(raw_cookie.encode("ascii")).hexdigest(),
                csrf_token=csrf_token,
                auth_epoch=admin.auth_epoch,
                idle_expires_at=now + timedelta(hours=12),
                absolute_expires_at=now + timedelta(days=7),
            )
        )
        await session.commit()
        admin_id = admin.id
    case.client.cookies.set(ADMIN_COOKIE_NAME, raw_cookie, path="/")
    try:
        async with case.session_maker() as session:
            current_admin = await session.get(Admin, admin_id)
            assert current_admin is not None
            yield current_admin, csrf_token
    finally:
        async with case.session_maker() as session:
            await session.execute(delete(Admin).where(Admin.id == admin_id))
            await session.commit()


@pytest.mark.asyncio
async def test_admin_product_http_round_trip_preserves_editable_fields(
    test_engine: AsyncEngine,
) -> None:
    async with (
        make_api_case(test_engine, base_url="https://testserver") as case,
        _admin_cookie(case) as (_admin, csrf_token),
    ):
        async with case.session_maker() as session:
            product = await session.get(Product, case.product_id)
            assert product is not None
            product.barcode = "EXISTING-BARCODE"
            product.sort_order = 7
            category_id = product.category_id
            destination = Category(
                name_uz="Admin detail destination",
                name_ru="Admin detail destination",
                slug=f"admin-detail-{token_hex(4)}",
            )
            session.add(destination)
            await session.flush()
            destination_id = destination.id
            await session.commit()

        try:
            listed = await case.client.get(
                "/api/v1/admin/products", params={"category_id": category_id}
            )
            assert listed.status_code == 200
            listed_product = next(
                item for item in listed.json()["items"] if item["id"] == case.product_id
            )
            assert listed_product["barcode"] == "EXISTING-BARCODE"
            assert listed_product["sort_order"] == 7

            mutation_headers = {
                "Origin": settings.webapp_origin,
                "X-CSRF-Token": csrf_token,
            }
            changed = await case.client.patch(
                f"/api/v1/admin/products/{case.product_id}",
                headers=mutation_headers,
                json={
                    "expected_edit_version": 0,
                    "barcode": "UPDATED-BARCODE",
                    "sort_order": 3,
                },
            )
            assert changed.status_code == 200
            assert changed.json()["barcode"] == "UPDATED-BARCODE"
            assert changed.json()["sort_order"] == 3

            public_product = await case.client.get(
                f"/api/v1/catalog/products/{case.product_id}"
            )
            assert public_product.status_code == 200
            assert "barcode" not in public_product.json()
            assert "sort_order" not in public_product.json()

            moved_out = await case.client.patch(
                f"/api/v1/admin/products/{case.product_id}",
                headers=mutation_headers,
                json={
                    "expected_edit_version": 1,
                    "name_uz": "Renamed product",
                    "category_id": destination_id,
                    "is_active": False,
                },
            )
            assert moved_out.status_code == 200
            assert moved_out.json()["name_uz"] == "Renamed product"
            assert moved_out.json()["barcode"] == "UPDATED-BARCODE"
            assert moved_out.json()["sort_order"] == 3

            old_page = await case.client.get(
                "/api/v1/admin/products", params={"category_id": category_id}
            )
            assert old_page.status_code == 200
            assert all(item["id"] != case.product_id for item in old_page.json()["items"])

            detail = await case.client.get(f"/api/v1/admin/products/{case.product_id}")
            assert detail.status_code == 200
            assert detail.json()["category_id"] == destination_id
            assert detail.json()["is_active"] is False
            assert detail.json()["barcode"] == "UPDATED-BARCODE"
            assert detail.json()["sort_order"] == 3

            public_inactive = await case.client.get(
                f"/api/v1/catalog/products/{case.product_id}"
            )
            assert public_inactive.status_code == 404
        finally:
            async with case.session_maker() as session:
                await session.execute(delete(Product).where(Product.id == case.product_id))
                await session.execute(delete(Category).where(Category.id == destination_id))
                await session.commit()


@pytest.mark.asyncio
async def test_checkout_stock_version_rejects_stale_admin_edit(
    test_engine: AsyncEngine,
) -> None:
    from tests.test_purchase_checkout import _delete_case_orders, _prepare_api_cart

    async with make_api_case(test_engine, base_url="https://testserver") as case:
        await _prepare_api_cart(case, quantity=2)
        try:
            checkout = await case.client.post(
                "/api/v1/orders",
                headers={"Authorization": f"Bearer {case.token}"},
                json={
                    "order_type": "pickup",
                    "customer_name": "Test Buyer",
                    "customer_phone": "+998901234567",
                    "payment_method": "cash",
                },
            )
            assert checkout.status_code == 201

            async with _admin_cookie(case) as (_admin, csrf_token):
                stale_stock_response = await case.client.patch(
                    f"/api/v1/admin/products/{case.product_id}",
                    headers={
                        "Origin": settings.webapp_origin,
                        "X-CSRF-Token": csrf_token,
                    },
                    json={"expected_edit_version": 0, "stock_qty": 9},
                )
            async with case.session_maker() as session:
                stock_after = await session.scalar(
                    select(Product.stock_qty).where(Product.id == case.product_id)
                )
            assert stale_stock_response.status_code == 409
            assert stale_stock_response.json()["error"]["code"] == "ENTITY_CONFLICT"
            assert stock_after == 10 - 2
        finally:
            await _delete_case_orders(case)


@pytest.mark.asyncio
async def test_catalog_multipart_requires_csrf_and_bounds(
    test_engine: AsyncEngine,
) -> None:
    async with (
        make_api_case(test_engine, base_url="https://testserver") as case,
        _admin_cookie(case) as (_admin, csrf_token),
    ):
        missing_csrf = await case.client.post(
            f"/api/v1/admin/products/{case.product_id}/images",
            headers={"Origin": settings.webapp_origin},
            files={"file": ("photo.png", b"invalid", "image/png")},
        )
        assert missing_csrf.status_code == 403
        assert missing_csrf.json()["error"]["code"] == "CSRF_FAILED"

        headers = {
            "Origin": settings.webapp_origin,
            "X-CSRF-Token": csrf_token,
        }
        invalid_image = await case.client.post(
            f"/api/v1/admin/products/{case.product_id}/images",
            headers=headers,
            files={"file": ("photo.png", b"not a PNG", "image/png")},
        )
        assert invalid_image.status_code == 400
        assert invalid_image.json()["error"]["code"] == "INVALID_FILE"

        oversized = await case.client.post(
            f"/api/v1/admin/products/{case.product_id}/images",
            headers=headers,
            files={"file": ("large.png", b"x" * (5 * 1024 * 1024 + 1), "image/png")},
        )
        assert oversized.status_code == 400
        assert oversized.json()["error"]["code"] == "INVALID_FILE"

        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), color="green").save(image_buffer, format="PNG")
        png_content = image_buffer.getvalue()
        uploaded = await case.client.post(
            f"/api/v1/admin/products/{case.product_id}/images",
            headers=headers,
            files={"file": ("photo.png", png_content, "image/png")},
        )
        assert uploaded.status_code == 201
        assert uploaded.json()["edit_version"] == 1
        assert uploaded.json()["images"][0]["is_main"] is True

        async with case.session_maker() as session:
            category_id = await session.scalar(
                select(Product.category_id).where(Product.id == case.product_id)
            )
        assert category_id is not None
        category_image = await case.client.put(
            f"/api/v1/admin/categories/{category_id}/image",
            headers=headers,
            files={"file": ("cover.png", png_content, "image/png")},
        )
        assert category_image.status_code == 200
        assert category_image.json()["image_url"]
        assert category_image.json()["edit_version"] == 1
        removed_cover = await case.client.delete(
            f"/api/v1/admin/categories/{category_id}/image", headers=headers
        )
        assert removed_cover.status_code == 200
        assert removed_cover.json()["image_url"] is None
        assert removed_cover.json()["edit_version"] == 2


@pytest.mark.asyncio
async def test_bot_and_web_share_catalog_service(test_engine: AsyncEngine) -> None:
    from app.bot.handlers.admin.products_form import create_product_from_form

    async with (
        make_api_case(test_engine, base_url="https://testserver") as case,
        _admin_cookie(case) as (admin, csrf_token),
    ):
        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), color="blue").save(image_buffer, format="JPEG")
        jpeg_content = image_buffer.getvalue()

        class FakeBot:
            async def download(self, file_id: str, *, destination: BytesIO) -> BytesIO:
                assert file_id == "synthetic-telegram-file"
                destination.write(jpeg_content)
                return destination

        product_id: int | None = None
        try:
            async with case.session_maker() as session:
                category_id = await session.scalar(
                    select(Product.category_id).where(Product.id == case.product_id)
                )
                assert category_id is not None
                product = await create_product_from_form(
                    session,
                    admin_id=admin.id,
                    bot=FakeBot(),
                    values=ProductCreateIn(
                        category_id=category_id,
                        name_uz="Shared service product",
                        name_ru="Shared service product",
                        sku="SHARED-SERVICE-TEST",
                        price=Decimal("1250"),
                        unit=ProductUnit.DONA,
                    ),
                    file_ids=["synthetic-telegram-file"],
                )
                product_id = product.id
                assert product.edit_version == 1
                assert len(product.images) == 1
                await session.commit()

            response = await case.client.patch(
                f"/api/v1/admin/products/{product_id}",
                headers={
                    "Origin": settings.webapp_origin,
                    "X-CSRF-Token": csrf_token,
                },
                json={
                    "expected_edit_version": 1,
                    "name_uz": "Updated through web",
                },
            )
            assert response.status_code == 200
            assert response.json()["name_uz"] == "Updated through web"
            assert response.json()["edit_version"] == 2
            assert response.json()["images"][0]["telegram_file_id"] == (
                "synthetic-telegram-file"
            )
        finally:
            if product_id is not None:
                async with case.session_maker() as session:
                    await session.execute(delete(Product).where(Product.id == product_id))
                    await session.commit()


@pytest.mark.asyncio
async def test_category_in_use_conflict(db_session: AsyncSession, admin, product) -> None:
    product.is_active = False
    await db_session.flush()
    with pytest.raises(CategoryInUseError):
        await admin_catalog_service.delete_category(
            db_session, admin_id=admin.id, category_id=product.category_id
        )


@pytest.mark.asyncio
async def test_category_admin_lifecycle_uses_shared_version(
    db_session: AsyncSession, admin
) -> None:
    root = await admin_catalog_service.create_category(
        db_session,
        admin_id=admin.id,
        values=CategoryCreateIn(name_uz="Admin root", name_ru="Admin root"),
    )
    child = await admin_catalog_service.create_category(
        db_session,
        admin_id=admin.id,
        values=CategoryCreateIn(
            name_uz="Admin child", name_ru="Admin child", parent_id=root.id
        ),
    )
    updated = await admin_catalog_service.update_category(
        db_session,
        admin_id=admin.id,
        category_id=child.id,
        expected_edit_version=0,
        changes=CategoryUpdateIn(expected_edit_version=0, sort_order=4),
    )
    unchanged = await admin_catalog_service.update_category(
        db_session,
        admin_id=admin.id,
        category_id=child.id,
        expected_edit_version=1,
        changes=CategoryUpdateIn(expected_edit_version=1, sort_order=4),
    )
    assert unchanged.edit_version == 1
    with pytest.raises(CatalogEditConflictError) as stale_category:
        await admin_catalog_service.update_category(
            db_session,
            admin_id=admin.id,
            category_id=child.id,
            expected_edit_version=0,
            changes=CategoryUpdateIn(expected_edit_version=0, is_active=False),
        )
    assert stale_category.value.details == {
        "expected_edit_version": 0,
        "current_edit_version": 1,
    }
    moved = await admin_catalog_service.move_category(
        db_session,
        admin_id=admin.id,
        category_id=updated.id,
        parent_id=None,
        expected_edit_version=1,
    )
    assert moved.parent_id is None
    assert moved.sort_order == 4
    assert moved.edit_version == 2

    await admin_catalog_service.delete_category(
        db_session, admin_id=admin.id, category_id=moved.id
    )
    await admin_catalog_service.delete_category(
        db_session, admin_id=admin.id, category_id=root.id
    )


@pytest.mark.asyncio
async def test_product_admin_lifecycle_keeps_category_counts(
    db_session: AsyncSession, admin, category
) -> None:
    target_category = await admin_catalog_service.create_category(
        db_session,
        admin_id=admin.id,
        values=CategoryCreateIn(name_uz="Count target", name_ru="Count target"),
    )
    product = await admin_catalog_service.create_product(
        db_session,
        admin_id=admin.id,
        values=ProductCreateIn(
            category_id=category.id,
            name_uz="Counted product",
            name_ru="Counted product",
            sku="COUNTED-PRODUCT",
            price=Decimal("100"),
            unit=ProductUnit.DONA,
        ),
    )
    assert category.products_count == 1

    product = await admin_catalog_service.update_product(
        db_session,
        admin_id=admin.id,
        product_id=product.id,
        expected_edit_version=0,
        changes=ProductUpdateIn(
            expected_edit_version=0,
            category_id=target_category.id,
            is_active=False,
        ),
    )
    assert product.edit_version == 1
    unchanged = await admin_catalog_service.update_product(
        db_session,
        admin_id=admin.id,
        product_id=product.id,
        expected_edit_version=1,
        changes=ProductUpdateIn(expected_edit_version=1, is_active=False),
    )
    assert unchanged.edit_version == 1
    assert category.products_count == 0
    assert target_category.products_count == 1

    await admin_catalog_service.delete_product(
        db_session, admin_id=admin.id, product_id=product.id
    )
    assert target_category.products_count == 0


@pytest.mark.asyncio
async def test_admin_stock_adjustment_bumps_version_and_is_audited(
    db_session: AsyncSession, admin, product
) -> None:
    initial_version = product.edit_version
    product = await admin_catalog_service.adjust_product_stock(
        db_session, admin_id=admin.id, product_id=product.id, delta=-20
    )
    assert product.stock_qty == 0
    assert product.edit_version == initial_version + 1

    product = await admin_catalog_service.adjust_product_stock(
        db_session, admin_id=admin.id, product_id=product.id, delta=3
    )
    actions = (
        await db_session.scalars(
            select(AdminAuditEvent.action)
            .where(
                AdminAuditEvent.resource_type == "product",
                AdminAuditEvent.actor_admin_id == admin.id,
            )
            .order_by(AdminAuditEvent.id)
        )
    ).all()
    assert product.stock_qty == 3
    assert product.edit_version == initial_version + 2
    assert actions == ["stock_adjust", "stock_adjust"]


@pytest.mark.asyncio
async def test_image_primary_reorder_is_atomic(
    db_session: AsyncSession, admin, product
) -> None:
    second_product = Product(
        category_id=product.category_id,
        name_uz="Second",
        name_ru="Second",
        sku="TEST-SKU-SECOND",
        price=Decimal("100"),
        stock_qty=1,
        unit=ProductUnit.DONA,
    )
    db_session.add(second_product)
    await db_session.flush()
    first_images = [
        ProductImage(
            product_id=product.id,
            url=f"https://cdn.test/{index}.jpg",
            sort_order=index,
            is_main=index == 0,
        )
        for index in range(3)
    ]
    other_image = ProductImage(
        product_id=second_product.id,
        url="https://cdn.test/other.jpg",
        sort_order=0,
        is_main=True,
    )
    db_session.add_all([*first_images, other_image])
    await db_session.flush()
    selected_id = first_images[2].id
    other_id = other_image.id

    selected = await admin_catalog_service.set_product_image(
        db_session,
        admin_id=admin.id,
        product_id=product.id,
        image_id=selected_id,
        is_main=True,
        sort_order=0,
    )

    current_images = (
        await db_session.scalars(
            select(ProductImage)
            .where(ProductImage.product_id == product.id)
            .order_by(ProductImage.sort_order)
        )
    ).all()
    untouched = await db_session.get(ProductImage, other_id)
    assert selected.id == selected_id
    assert [image.id for image in current_images] == [
        selected_id,
        first_images[0].id,
        first_images[1].id,
    ]
    assert [image.is_main for image in current_images] == [True, False, False]
    assert untouched is not None and untouched.is_main and untouched.sort_order == 0

    updated = await admin_catalog_service.delete_product_image(
        db_session,
        admin_id=admin.id,
        product_id=product.id,
        image_id=selected_id,
    )
    assert [image.is_main for image in updated.images] == [True, False]
    assert [image.sort_order for image in updated.images] == [0, 1]


@pytest.mark.asyncio
async def test_category_cycle_parallel_edits(
    test_engine: AsyncEngine,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.models.admin import Admin
    from app.db.models.enums import AdminRole

    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    async with maker() as session:
        admin = Admin(
            telegram_id=9_100_000_001,
            full_name="Catalog concurrency test",
            role=AdminRole.SUPERADMIN,
        )
        left = Category(name_uz="Left", name_ru="Left", slug="cycle-left")
        right = Category(name_uz="Right", name_ru="Right", slug="cycle-right")
        session.add_all([admin, left, right])
        await session.commit()
        admin_id, left_id, right_id = admin.id, left.id, right.id

    async def move(category_id: int, parent_id: int) -> str:
        async with maker() as session:
            try:
                await admin_catalog_service.move_category(
                    session,
                    admin_id=admin_id,
                    category_id=category_id,
                    parent_id=parent_id,
                    expected_edit_version=0,
                )
                await session.commit()
                return "moved"
            except CatalogEditConflictError:
                await session.rollback()
                return "conflict"

    outcomes = await asyncio.gather(move(left_id, right_id), move(right_id, left_id))
    assert sorted(outcomes) == ["conflict", "moved"]

    async with maker() as session:
        await session.execute(delete(Category).where(Category.id.in_([left_id, right_id])))
        await session.execute(delete(Admin).where(Admin.id == admin_id))
        await session.commit()

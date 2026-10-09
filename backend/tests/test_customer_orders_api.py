from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from secrets import token_hex

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models.admin import Admin
from app.db.models.enums import (
    AdminRole,
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentStatus,
)
from app.db.models.order import Order
from app.db.models.order_status_history import OrderStatusHistory
from app.db.models.setting import Setting
from app.db.repositories import setting_repository

from .api_helpers import ApiCase, make_api_case


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _new_order(user_id: int, *, status: OrderStatus = OrderStatus.NEW) -> Order:
    return Order(
        order_number=f"KANS-{token_hex(6).upper()}",
        user_id=user_id,
        order_type=OrderType.PICKUP,
        status=status,
        customer_name="History Test Buyer",
        customer_phone="+998901234567",
        subtotal=Decimal("12000.00"),
        delivery_fee=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("12000.00"),
        payment_method=PaymentMethod.CASH,
        payment_status=PaymentStatus.PENDING,
        source="webapp",
        admin_message_ids={},
    )


@asynccontextmanager
async def _customer_orders_api_case(test_engine: AsyncEngine) -> AsyncIterator[ApiCase]:
    async with make_api_case(test_engine) as case:
        try:
            yield case
        finally:
            async with case.session_maker() as session:
                await session.execute(
                    delete(Order).where(Order.user_id.in_([case.user_id, case.other_user_id]))
                )
                await session.execute(
                    delete(Admin).where(Admin.telegram_id == 9_500_000_000_000_001)
                )
                await session.commit()


@asynccontextmanager
async def _isolated_public_settings(case: ApiCase) -> AsyncIterator[None]:
    keys = {
        "support_username",
        "welcome_text_uz",
        "admin_password",
        "telegram_bot_token",
    }
    async with case.session_maker() as session:
        existing = await setting_repository.get_all(session)
        original = {key: existing[key] for key in keys if key in existing}
    try:
        yield
    finally:
        async with case.session_maker() as session:
            for key in keys:
                if key in original:
                    await setting_repository.set_value(session, key, original[key])
                else:
                    await session.execute(delete(Setting).where(Setting.key == key))
            await session.commit()


async def test_order_history_pages_by_owner(test_engine: AsyncEngine) -> None:
    async with _customer_orders_api_case(test_engine) as case:
        created_at = datetime.now(UTC) - timedelta(days=1)
        async with case.session_maker() as session:
            own_orders = [_new_order(case.user_id) for _ in range(25)]
            other_order = _new_order(case.other_user_id)
            session.add_all([*own_orders, other_order])
            await session.flush()
            for order in [*own_orders, other_order]:
                order.created_at = created_at
            await session.commit()

        first_page = await case.client.get("/api/v1/orders/history", headers=_auth(case.token))
        assert first_page.status_code == 200
        payload = first_page.json()
        own_ids_desc = sorted((order.id for order in own_orders), reverse=True)
        assert payload["total"] == 25
        assert payload["page"] == 1
        assert payload["limit"] == 24
        assert payload["total_pages"] == 2
        assert len(payload["items"]) == 24
        assert [item["id"] for item in payload["items"]] == own_ids_desc[:24]
        assert all(
            set(item)
            == {
                "id",
                "order_number",
                "created_at",
                "status",
                "payment_status",
                "order_type",
                "total",
            }
            for item in payload["items"]
        )
        assert all(item["id"] != other_order.id for item in payload["items"])

        second_page = await case.client.get(
            "/api/v1/orders/history?page=2", headers=_auth(case.token)
        )
        assert second_page.status_code == 200
        assert [item["id"] for item in second_page.json()["items"]] == own_ids_desc[24:]

        legacy_list = await case.client.get("/api/v1/orders", headers=_auth(case.token))
        assert legacy_list.status_code == 200
        assert len(legacy_list.json()) == 25
        assert all(item["id"] in set(own_ids_desc) for item in legacy_list.json())
        assert {"customer_name", "items", "payment_method"} <= set(legacy_list.json()[0])


async def test_customer_timeline_is_safe_for_cancelled_and_sparse_history(
    test_engine: AsyncEngine,
) -> None:
    async with _customer_orders_api_case(test_engine) as case:
        async with case.session_maker() as session:
            admin = Admin(
                telegram_id=9_500_000_000_000_001,
                full_name="Private Timeline Admin",
                role=AdminRole.SUPERADMIN,
            )
            cancelled = _new_order(case.user_id, status=OrderStatus.CANCELLED)
            sparse = _new_order(case.user_id, status=OrderStatus.PREPARING)
            no_history = _new_order(case.user_id, status=OrderStatus.CONFIRMED)
            session.add_all([admin, cancelled, sparse, no_history])
            await session.flush()

            base_time = datetime.now(UTC) - timedelta(days=3)
            session.add_all(
                [
                    OrderStatusHistory(
                        order_id=cancelled.id,
                        from_status=None,
                        to_status=OrderStatus.NEW,
                        created_at=base_time,
                        changed_by_admin_id=admin.id,
                        comment="private setup detail",
                    ),
                    OrderStatusHistory(
                        order_id=cancelled.id,
                        from_status=OrderStatus.NEW,
                        to_status=OrderStatus.CANCELLED,
                        created_at=base_time + timedelta(days=1),
                        changed_by_admin_id=admin.id,
                        comment="private cancellation detail",
                    ),
                    # Corrupt or legacy rows after cancellation must not reopen its lifecycle.
                    OrderStatusHistory(
                        order_id=cancelled.id,
                        from_status=OrderStatus.CANCELLED,
                        to_status=OrderStatus.COMPLETED,
                        created_at=base_time + timedelta(days=2),
                        changed_by_admin_id=admin.id,
                        comment="private post-cancel detail",
                    ),
                    OrderStatusHistory(
                        order_id=sparse.id,
                        from_status=None,
                        to_status=OrderStatus.NEW,
                        created_at=base_time,
                        changed_by_admin_id=admin.id,
                        comment="private sparse detail",
                    ),
                    # Future-dated history is not a customer-visible event.
                    OrderStatusHistory(
                        order_id=sparse.id,
                        from_status=OrderStatus.NEW,
                        to_status=OrderStatus.PREPARING,
                        created_at=datetime.now(UTC) + timedelta(days=1),
                        changed_by_admin_id=admin.id,
                        comment="private future detail",
                    ),
                ]
            )
            await session.commit()

        cancelled_response = await case.client.get(
            f"/api/v1/orders/{cancelled.id}/timeline", headers=_auth(case.token)
        )
        assert cancelled_response.status_code == 200
        assert cancelled_response.json() == [
            {"status": "new", "occurred_at": base_time.isoformat().replace("+00:00", "Z")},
            {
                "status": "cancelled",
                "occurred_at": (base_time + timedelta(days=1))
                .isoformat()
                .replace("+00:00", "Z"),
            },
        ]
        assert "changed_by_admin_id" not in cancelled_response.text
        assert "Private Timeline Admin" not in cancelled_response.text
        assert "comment" not in cancelled_response.text
        assert "private" not in cancelled_response.text
        assert "completed" not in cancelled_response.text

        sparse_response = await case.client.get(
            f"/api/v1/orders/{sparse.id}/timeline", headers=_auth(case.token)
        )
        assert sparse_response.status_code == 200
        assert sparse_response.json() == [
            {"status": "new", "occurred_at": base_time.isoformat().replace("+00:00", "Z")}
        ]
        assert "preparing" not in sparse_response.text

        empty_response = await case.client.get(
            f"/api/v1/orders/{no_history.id}/timeline", headers=_auth(case.token)
        )
        assert empty_response.status_code == 200
        assert empty_response.json() == []


async def test_foreign_order_timeline_is_not_found(test_engine: AsyncEngine) -> None:
    async with _customer_orders_api_case(test_engine) as case:
        async with case.session_maker() as session:
            foreign_order = _new_order(case.other_user_id, status=OrderStatus.CONFIRMED)
            session.add(foreign_order)
            await session.commit()

        response = await case.client.get(
            f"/api/v1/orders/{foreign_order.id}/timeline", headers=_auth(case.token)
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"


async def test_public_settings_has_only_allowlisted_customer_fields(
    test_engine: AsyncEngine,
) -> None:
    async with make_api_case(test_engine) as case, _isolated_public_settings(case):
        async with case.session_maker() as session:
            await setting_repository.set_value(session, "support_username", "@kans_support")
            await setting_repository.set_value(session, "welcome_text_uz", "Xush kelibsiz")
            await setting_repository.set_value(session, "admin_password", "synthetic-secret")
            await setting_repository.set_value(
                session, "telegram_bot_token", "synthetic-token"
            )
            await session.commit()

        response = await case.client.get("/api/v1/settings/public")
        assert response.status_code == 200
        payload = response.json()
        assert payload["support_username"] == "@kans_support"
        assert payload["welcome_text_uz"] == "Xush kelibsiz"
        assert "admin_password" not in payload
        assert "telegram_bot_token" not in payload
        assert set(payload) == {
            "delivery_fee",
            "free_delivery_from",
            "min_order_amount",
            "work_hours",
            "card_number",
            "card_holder",
            "support_username",
            "shop_phone",
            "is_shop_open",
            "welcome_text_uz",
            "welcome_text_ru",
            "enabled_payment_providers",
            "checkout_type_readiness",
            "payment_method_readiness",
        }


async def test_customer_order_routes_require_buyer_token_and_validate_page(
    test_engine: AsyncEngine,
) -> None:
    async with _customer_orders_api_case(test_engine) as case:
        no_token = await case.client.get("/api/v1/orders/history")
        assert no_token.status_code == 401
        assert no_token.json()["error"]["code"] == "UNAUTHORIZED"

        invalid_page = await case.client.get(
            "/api/v1/orders/history?page=0&limit=51", headers=_auth(case.token)
        )
        assert invalid_page.status_code == 422
        assert invalid_page.json()["error"]["code"] == "VALIDATION_ERROR"

        missing_timeline_token = await case.client.get("/api/v1/orders/1/timeline")
        assert missing_timeline_token.status_code == 401

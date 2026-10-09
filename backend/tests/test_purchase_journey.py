"""HTTP integration proof for the customer purchase and manual-payment journey.

Browser tests deliberately use API fixtures; this test keeps the FastAPI routes,
SQLAlchemy sessions, PostgreSQL transactions, auth checks, and private file storage real.
"""

import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from io import BytesIO
from unittest.mock import patch
from urllib.parse import urlencode
from uuid import UUID

import pytest
import pytest_asyncio
from PIL import Image
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings
from app.core.security import decode_token
from app.db.models.admin import Admin
from app.db.models.admin_audit_event import AdminAuditEvent
from app.db.models.cart import Cart
from app.db.models.cart_mutation import CartMutation
from app.db.models.enums import AdminRole
from app.db.models.order import Order
from app.db.models.order_item import OrderItem
from app.db.models.order_status_history import OrderStatusHistory
from app.db.models.product import Product
from app.db.models.setting import Setting
from app.db.models.user import User
from app.db.repositories import setting_repository
from app.services.receipt_storage import PrivateReceiptStorage

from .api_helpers import make_api_case


def _signed_init_data(telegram_id: int) -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps(
            {"id": telegram_id, "first_name": "Journey Buyer", "language_code": "uz"},
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (3, 2), color=(20, 80, 140)).save(buffer, format="PNG")
    return buffer.getvalue()


@contextmanager
def _telegram_effects_are_injected(redis: Redis) -> Iterator[None]:
    # Existing customer/admin rows make auth pure database work. Durable outbox events are
    # written in the business transaction and no Telegram call runs in the HTTP request.
    with (
        patch("app.api.rate_limit.get_redis", return_value=redis),
        patch("app.api.v1.auth.get_redis", return_value=redis),
        patch("app.api.admin_security.get_redis", return_value=redis),
    ):
        yield


@pytest_asyncio.fixture
async def journey_redis() -> AsyncIterator[Redis]:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    keys = ("ratelimit:general:127.0.0.1", "ratelimit:auth_code:127.0.0.1")
    await redis.delete(*keys)
    try:
        yield redis
    finally:
        await redis.delete(*keys, "customer_login:code:12345678", "admin_login:654321")
        await redis.aclose()


@pytest.mark.asyncio
async def test_purchase_journey_auth_add_quote_checkout_private_receipt_and_admin_accept(
    test_engine: AsyncEngine,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    journey_redis: Redis,
) -> None:
    """One Telegram identity works across both login methods and owns every purchase step."""
    monkeypatch.setattr(settings, "private_media_root", str(tmp_path / "private-receipts"))
    redis = journey_redis

    async with make_api_case(test_engine) as case:
        previous_settings: dict[str, tuple[bool, object]] = {}
        order_id: int | None = None
        admin_id: int | None = None
        try:
            async with case.session_maker() as session:
                customer = await session.get(User, case.user_id)
                assert customer is not None
                customer_telegram_id = customer.telegram_id
                current_settings = await setting_repository.get_all(session)
                keys = (
                    "is_shop_open",
                    "min_order_amount",
                    "delivery_fee",
                    "free_delivery_from",
                    "card_number",
                    "card_holder",
                )
                previous_settings = {
                    key: (key in current_settings, current_settings.get(key)) for key in keys
                }
                admin = Admin(
                    telegram_id=customer_telegram_id + 20_000,
                    full_name="Synthetic Journey Admin",
                    role=AdminRole.MANAGER,
                )
                session.add(admin)
                await session.flush()
                admin_id = admin.id
                for key, value in {
                    "is_shop_open": True,
                    "min_order_amount": "0",
                    "delivery_fee": "0",
                    "free_delivery_from": "0",
                    "card_number": "8600 0000 0000 0000",
                    "card_holder": "TEST MERCHANT",
                }.items():
                    await setting_repository.set_value(session, key, value)
                await session.commit()

            with _telegram_effects_are_injected(redis):
                # A private bot code and signed Mini App initData resolve to the same user.
                await redis.set(
                    "customer_login:code:12345678", str(customer_telegram_id), ex=300
                )
                code_login = await case.client.post(
                    "/api/v1/auth/customer/code", json={"code": "12345678"}
                )
                assert code_login.status_code == 200, code_login.text
                code_claims = decode_token(
                    code_login.json()["access_token"], expected_type="access"
                )

                mini_app_login = await case.client.post(
                    "/api/v1/auth/telegram",
                    json={"init_data": _signed_init_data(customer_telegram_id)},
                )
                assert mini_app_login.status_code == 200, mini_app_login.text
                mini_app_claims = decode_token(
                    mini_app_login.json()["access_token"], expected_type="access"
                )
                assert code_claims["sub"] == mini_app_claims["sub"] == str(case.user_id)
                assert code_claims["telegram_id"] == mini_app_claims["telegram_id"]

                buyer_headers = {
                    "Authorization": f"Bearer {code_login.json()['access_token']}"
                }
                add_key = "11111111-1111-4111-8111-111111111111"
                add_headers = {**buyer_headers, "Idempotency-Key": add_key}
                add_payload = {"product_id": case.product_id, "quantity": 2}
                added = await case.client.post(
                    "/api/v1/cart/items", headers=add_headers, json=add_payload
                )
                replayed_add = await case.client.post(
                    "/api/v1/cart/items", headers=add_headers, json=add_payload
                )
                assert added.status_code == replayed_add.status_code == 201
                assert added.json()["items_count"] == replayed_add.json()["items_count"] == 2

                # A new request/session sees the committed cart through the other auth method.
                mini_app_headers = {
                    "Authorization": f"Bearer {mini_app_login.json()['access_token']}"
                }
                fresh_cart = await case.client.get("/api/v1/cart", headers=mini_app_headers)
                assert fresh_cart.status_code == 200
                assert fresh_cart.json()["items"][0]["quantity"] == 2
                assert fresh_cart.json()["items"][0]["product"]["images"][0]["url"] == (
                    "https://cdn.example.test/products/test-image.jpg"
                )

                foreign_cart = await case.client.get(
                    "/api/v1/cart",
                    headers={"Authorization": f"Bearer {case.other_token}"},
                )
                assert foreign_cart.status_code == 200
                assert foreign_cart.json()["items"] == []

                quote_response = await case.client.post(
                    "/api/v1/orders/quote",
                    headers=buyer_headers,
                    json={"order_type": "pickup", "payment_method": "card_transfer"},
                )
                assert quote_response.status_code == 200, quote_response.text
                quote = quote_response.json()
                assert quote["ready"] is True
                assert "card_transfer" in quote["payment_methods"]
                assert quote["total"] == "10000.00"

                checkout_key = "22222222-2222-4222-8222-222222222222"
                checkout_headers = {**buyer_headers, "Idempotency-Key": checkout_key}
                checkout_payload = {
                    "order_type": "pickup",
                    "customer_name": "Journey Buyer",
                    "customer_phone": "+998901234567",
                    "payment_method": "card_transfer",
                    "purchase_contract_version": 1,
                    "expected_total": quote["total"],
                    "expected_quote": quote["quote_fingerprint"],
                }
                created = await case.client.post(
                    "/api/v1/orders", headers=checkout_headers, json=checkout_payload
                )
                assert created.status_code == 201, created.text
                order_id = created.json()["id"]
                replayed_checkout = await case.client.post(
                    "/api/v1/orders", headers=checkout_headers, json=checkout_payload
                )
                assert replayed_checkout.status_code == 200, replayed_checkout.text
                assert replayed_checkout.json()["id"] == order_id
                assert created.json()["payment_instructions"] == {
                    "card_number": "8600 0000 0000 0000",
                    "card_holder": "TEST MERCHANT",
                }

                upload = await case.client.post(
                    f"/api/v1/orders/{order_id}/receipt",
                    headers=buyer_headers,
                    files={"file": ("receipt.png", _png_bytes(), "image/png")},
                )
                assert upload.status_code == 200, upload.text
                assert upload.json()["payment_status"] == "receipt_uploaded"
                assert upload.json()["receipt_version"] == 1

                owner_receipt = await case.client.get(
                    f"/api/v1/orders/{order_id}/receipt", headers=mini_app_headers
                )
                assert owner_receipt.status_code == 200
                assert owner_receipt.headers["cache-control"] == "private, no-store"
                assert owner_receipt.content.startswith(b"\x89PNG\r\n\x1a\n")
                foreign_order = await case.client.get(
                    f"/api/v1/orders/{order_id}",
                    headers={"Authorization": f"Bearer {case.other_token}"},
                )
                foreign_receipt = await case.client.get(
                    f"/api/v1/orders/{order_id}/receipt",
                    headers={"Authorization": f"Bearer {case.other_token}"},
                )
                assert foreign_order.status_code == foreign_receipt.status_code == 403

                assert admin_id is not None
                async with case.session_maker() as session:
                    admin = await session.get(Admin, admin_id)
                    assert admin is not None
                    admin_telegram_id = admin.telegram_id
                await redis.set("admin_login:654321", str(admin_telegram_id), ex=300)
                admin_login = await case.client.post(
                    "/api/v1/auth/admin/code/exchange",
                    headers={"Origin": settings.webapp_origin},
                    json={"code": "654321"},
                )
                assert admin_login.status_code == 200, admin_login.text
                cookie_header = admin_login.headers["set-cookie"].split(";", maxsplit=1)[0]
                admin_accept = await case.client.post(
                    f"/api/v1/admin/orders/{order_id}/payment/accept",
                    headers={
                        "Origin": settings.webapp_origin,
                        "Cookie": cookie_header,
                        "X-CSRF-Token": admin_login.json()["csrf_token"],
                    },
                    json={"expected_receipt_version": 1},
                )
                assert admin_accept.status_code == 200, admin_accept.text
                assert admin_accept.json()["payment_status"] == "paid"
                assert admin_accept.json()["status"] == "new"

                # Re-read persisted rows independently of the HTTP response objects. These
                # counters show a replay did not double-add, decrement stock, or create orders.
                async with case.session_maker() as session:
                    product = await session.get(Product, case.product_id)
                    stored_order = await session.get(Order, order_id)
                    assert product is not None and stored_order is not None
                    assert product.stock_qty == 8
                    assert product.sold_count == 2
                    assert stored_order.payment_status.value == "paid"
                    assert stored_order.payment_reviewed_by_admin_id == admin_id
                    assert stored_order.payment_reviewed_at is not None
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(CartMutation)
                            .where(CartMutation.user_id == case.user_id)
                        )
                        == 1
                    )
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(Order)
                            .where(Order.user_id == case.user_id)
                        )
                        == 1
                    )
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(OrderItem)
                            .where(OrderItem.order_id == order_id)
                        )
                        == 1
                    )
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(OrderStatusHistory)
                            .where(OrderStatusHistory.order_id == order_id)
                        )
                        == 1
                    )
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(AdminAuditEvent)
                            .where(
                                AdminAuditEvent.resource_type == "payment",
                                AdminAuditEvent.resource_id == str(order_id),
                                AdminAuditEvent.action
                                == "manual_card_transfer_payment_accepted",
                            )
                        )
                        == 1
                    )
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(Cart)
                            .where(Cart.user_id == case.user_id)
                        )
                        == 1
                    )
                    assert stored_order.checkout_key == str(UUID(checkout_key))
        finally:
            async with case.session_maker() as session:
                if order_id is not None:
                    stored_order = await session.get(Order, order_id)
                    if stored_order is not None and stored_order.receipt_storage_key:
                        storage = PrivateReceiptStorage(settings.private_media_root_path)
                        storage.resolve(stored_order.receipt_storage_key).unlink(
                            missing_ok=True
                        )
                    await session.execute(delete(Order).where(Order.id == order_id))
                if admin_id is not None:
                    await session.execute(delete(Admin).where(Admin.id == admin_id))
                for key, (existed, value) in previous_settings.items():
                    if existed:
                        await setting_repository.set_value(session, key, value)
                    else:
                        await session.execute(delete(Setting).where(Setting.key == key))
                await session.commit()

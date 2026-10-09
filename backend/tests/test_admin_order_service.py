from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from secrets import token_hex, token_urlsafe
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.db.models.admin import Admin
from app.db.models.admin_audit_event import AdminAuditEvent
from app.db.models.admin_order_message import AdminOrderMessage
from app.db.models.admin_session import AdminSession
from app.db.models.enums import (
    AdminRole,
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
    PaymentTxState,
)
from app.db.models.notification_outbox import NotificationOutbox
from app.db.models.order import Order
from app.db.models.order_item import OrderItem
from app.db.models.payment_transaction import PaymentTransaction
from app.db.models.user import User
from app.services.receipt_storage import PrivateReceiptStorage

from .api_helpers import ApiCase, make_api_case


async def _make_order(
    session: AsyncSession,
    user_id: int,
    *,
    payment_method: PaymentMethod = PaymentMethod.CASH,
    payment_status: PaymentStatus = PaymentStatus.PENDING,
    receipt_file_id: str | None = None,
) -> Order:
    order = Order(
        order_number=f"KANS-{token_hex(6).upper()}",
        user_id=user_id,
        order_type=OrderType.PICKUP,
        status=OrderStatus.NEW,
        customer_name="Synthetic Receipt Buyer",
        customer_phone="+998901234567",
        subtotal=Decimal("25000"),
        delivery_fee=Decimal("0"),
        discount=Decimal("0"),
        total=Decimal("25000"),
        payment_method=payment_method,
        payment_status=payment_status,
        receipt_file_id=receipt_file_id,
        receipt_version=1 if receipt_file_id else 0,
        admin_message_ids={},
        source="webapp",
    )
    session.add(order)
    await session.flush()
    session.add(
        OrderItem(
            order_id=order.id,
            product_name_snapshot="Synthetic notebook",
            product_sku_snapshot="SYNTHETIC-NOTEBOOK",
            price=Decimal("25000"),
            quantity=1,
            total=Decimal("25000"),
        )
    )
    await session.flush()
    return order


async def _make_admin_session(
    session: AsyncSession, role: AdminRole
) -> tuple[Admin, str, str]:
    actor = Admin(
        telegram_id=9_000_000_000_000_000 + int(token_hex(6), 16),
        full_name=f"Synthetic {role.value}",
        role=role,
    )
    session.add(actor)
    await session.flush()
    raw_cookie = token_urlsafe(32)
    csrf_token = token_urlsafe(48)
    now = datetime.now(UTC)
    session.add(
        AdminSession(
            admin_id=actor.id,
            token_hash=sha256(raw_cookie.encode("ascii")).hexdigest(),
            csrf_token=csrf_token,
            auth_epoch=actor.auth_epoch,
            idle_expires_at=now + timedelta(hours=1),
            absolute_expires_at=now + timedelta(days=1),
        )
    )
    await session.flush()
    return actor, raw_cookie, csrf_token


def _admin_headers(raw_cookie: str, csrf_token: str | None = None) -> dict[str, str]:
    headers = {"Cookie": f"__Host-kans-admin={raw_cookie}"}
    if csrf_token is not None:
        headers["Origin"] = settings.webapp_origin
        headers["X-CSRF-Token"] = csrf_token
    return headers


@asynccontextmanager
async def _api_fixture(
    case: ApiCase, *, order_ids: list[int], admin_ids: list[int]
) -> AsyncIterator[None]:
    try:
        yield
    finally:
        async with case.session_maker() as session:
            await session.execute(
                delete(NotificationOutbox).where(
                    NotificationOutbox.aggregate_id.in_([str(value) for value in order_ids])
                )
            )
            await session.execute(
                delete(AdminAuditEvent).where(AdminAuditEvent.actor_admin_id.in_(admin_ids))
            )
            await session.execute(delete(Order).where(Order.id.in_(order_ids)))
            await session.execute(delete(Admin).where(Admin.id.in_(admin_ids)))
            await session.commit()


@pytest.mark.asyncio
async def test_order_permissions_and_detail_history(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        async with case.session_maker() as session:
            actors = [
                await _make_admin_session(session, role)
                for role in (AdminRole.SUPERADMIN, AdminRole.MANAGER, AdminRole.OPERATOR)
            ]
            transition_orders = [
                await _make_order(session, case.user_id)
                for _role in (AdminRole.SUPERADMIN, AdminRole.MANAGER, AdminRole.OPERATOR)
            ]
            payment_orders = [
                await _make_order(
                    session,
                    case.user_id,
                    payment_method=PaymentMethod.CARD_TRANSFER,
                    payment_status=PaymentStatus.RECEIPT_UPLOADED,
                    receipt_file_id=f"synthetic-receipt-{index}",
                )
                for index, _role in enumerate(
                    (AdminRole.SUPERADMIN, AdminRole.MANAGER, AdminRole.OPERATOR)
                )
            ]
            for order in transition_orders:
                session.add(
                    PaymentTransaction(
                        order_id=order.id,
                        provider=PaymentProvider.CLICK,
                        provider_transaction_id=f"synthetic-{order.id}",
                        state=PaymentTxState.PENDING,
                        amount=order.total,
                        raw_payload={"must_not_be_returned": "synthetic-secret"},
                    )
                )
            await session.commit()
            order_ids = [order.id for order in [*transition_orders, *payment_orders]]
            admin_ids = [actor.id for actor, _cookie, _csrf in actors]

        async with _api_fixture(case, order_ids=order_ids, admin_ids=admin_ids):
            for index, (actor, raw_cookie, csrf_token) in enumerate(actors):
                headers = _admin_headers(raw_cookie, csrf_token)
                order = transition_orders[index]
                payment_order = payment_orders[index]

                listing = await case.client.get(
                    f"/api/v1/admin/orders?query={order.order_number[-6:]}&page=1&limit=1",
                    headers=_admin_headers(raw_cookie),
                )
                assert listing.status_code == 200, listing.text
                listing_body = listing.json()
                assert listing_body["total"] == 1
                assert listing_body["items"][0]["id"] == order.id
                assert listing.headers["cache-control"] == "private, no-store"

                detail = await case.client.get(
                    f"/api/v1/admin/orders/{order.id}", headers=_admin_headers(raw_cookie)
                )
                assert detail.status_code == 200, detail.text
                assert detail.json()["items"][0]["product_name_snapshot"] == (
                    "Synthetic notebook"
                )
                assert detail.json()["payment_history"][0]["state"] == "pending"
                assert "must_not_be_returned" not in detail.text

                with patch("app.api.v1.admin.orders.register_order_status_notifications"):
                    transitioned = await case.client.patch(
                        f"/api/v1/admin/orders/{order.id}/status",
                        headers=headers,
                        json={"status": "confirmed", "comment": "Synthetic confirmation"},
                    )
                assert transitioned.status_code == 200, transitioned.text
                assert transitioned.json()["status"] == "confirmed"

                with patch("app.api.v1.admin.payments.register_order_status_notifications"):
                    accepted = await case.client.post(
                        f"/api/v1/admin/orders/{payment_order.id}/payment/accept",
                        headers=headers,
                        json={"expected_receipt_version": 1},
                    )
                assert accepted.status_code == 200, accepted.text
                assert accepted.json()["payment_status"] == "paid"
                assert accepted.json()["status"] == "new"

                changed_detail = await case.client.get(
                    f"/api/v1/admin/orders/{payment_order.id}",
                    headers=_admin_headers(raw_cookie),
                )
                assert changed_detail.status_code == 200, changed_detail.text
                history = changed_detail.json()["payment_review_history"]
                assert len(history) == 1
                assert history[0]["actor_admin_id"] == actor.id


@pytest.mark.asyncio
async def test_admin_receipt_requires_live_order_role(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        order_id: int | None = None
        admin_ids: list[int] = []
        receipt_key: str | None = None
        try:
            async with case.session_maker() as session:
                order = await _make_order(session, case.user_id)
                actor, raw_cookie, _csrf = await _make_admin_session(
                    session, AdminRole.OPERATOR
                )
                inactive, inactive_cookie, _ = await _make_admin_session(
                    session, AdminRole.MANAGER
                )
                stored = PrivateReceiptStorage(settings.private_media_root_path).store(
                    b"synthetic private receipt", "application/pdf"
                )
                order.receipt_storage_key = stored.storage_key
                order.receipt_content_type = stored.content_type
                await session.commit()
                order_id = order.id
                receipt_key = stored.storage_key
                admin_ids = [actor.id, inactive.id]

            async with case.session_maker() as session:
                current_admin = await session.get(Admin, inactive.id)
                assert current_admin is not None
                current_admin.is_active = False
                await session.commit()

            endpoint = f"/api/v1/orders/{order_id}/receipt"
            operator_read = await case.client.get(endpoint, headers=_admin_headers(raw_cookie))
            assert operator_read.status_code == 200, operator_read.text
            assert operator_read.content == b"synthetic private receipt"
            assert operator_read.headers["cache-control"] == "private, no-store"
            assert operator_read.headers["x-content-type-options"] == "nosniff"

            inactive_read = await case.client.get(
                endpoint, headers=_admin_headers(inactive_cookie)
            )
            assert inactive_read.status_code == 401
            assert inactive_read.json()["error"]["code"] == "ADMIN_SESSION_REQUIRED"
        finally:
            if receipt_key:
                (settings.private_media_root_path / receipt_key).unlink(missing_ok=True)
            if order_id is not None:
                async with case.session_maker() as session:
                    await session.execute(delete(Order).where(Order.id == order_id))
                    await session.execute(delete(Admin).where(Admin.id.in_(admin_ids)))
                    await session.commit()


@pytest.mark.asyncio
async def test_bearer_receipt_is_owner_only(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        order_id: int | None = None
        receipt_key: str | None = None
        try:
            async with case.session_maker() as session:
                order = await _make_order(session, case.user_id)
                stored = PrivateReceiptStorage(settings.private_media_root_path).store(
                    b"synthetic owner-only receipt", "application/pdf"
                )
                order.receipt_storage_key = stored.storage_key
                order.receipt_content_type = stored.content_type
                await session.commit()
                order_id = order.id
                receipt_key = stored.storage_key

            endpoint = f"/api/v1/orders/{order_id}/receipt"
            owner = await case.client.get(
                endpoint, headers={"Authorization": f"Bearer {case.token}"}
            )
            assert owner.status_code == 200
            assert owner.content == b"synthetic owner-only receipt"
            assert owner.headers["cache-control"] == "private, no-store"

            buyer_order = await case.client.get(
                f"/api/v1/orders/{order_id}",
                headers={"Authorization": f"Bearer {case.token}"},
            )
            buyer_history = await case.client.get(
                "/api/v1/orders/history",
                headers={"Authorization": f"Bearer {case.token}"},
            )
            assert buyer_order.status_code == buyer_history.status_code == 200
            assert buyer_order.headers["cache-control"] == "private, no-store"
            assert buyer_history.headers["cache-control"] == "private, no-store"

            foreign_admin_claim = create_access_token(
                user_id=case.other_user_id,
                telegram_id=8_000_000_000_000_001,
                is_admin=True,
            )
            foreign = await case.client.get(
                endpoint, headers={"Authorization": f"Bearer {foreign_admin_claim}"}
            )
            assert foreign.status_code == 403
            assert foreign.json()["error"]["code"] == "FORBIDDEN"
        finally:
            if receipt_key:
                (settings.private_media_root_path / receipt_key).unlink(missing_ok=True)
            if order_id is not None:
                async with case.session_maker() as session:
                    await session.execute(delete(Order).where(Order.id == order_id))
                    await session.commit()


@pytest.mark.asyncio
async def test_order_message_is_deduped_and_uses_order_owner(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        async with case.session_maker() as session:
            order = await _make_order(session, case.user_id)
            actor, raw_cookie, csrf_token = await _make_admin_session(
                session, AdminRole.OPERATOR
            )
            await session.commit()
            order_id, admin_id = order.id, actor.id

        async with _api_fixture(case, order_ids=[order_id], admin_ids=[admin_id]):
            key = str(uuid4())
            payload = {"text": "Synthetic order update", "idempotency_key": key}
            headers = _admin_headers(raw_cookie, csrf_token)
            endpoint = f"/api/v1/admin/orders/{order_id}/message"
            first = await case.client.post(endpoint, headers=headers, json=payload)
            replay = await case.client.post(endpoint, headers=headers, json=payload)

            assert first.status_code == 202, first.text
            assert replay.status_code == 202, replay.text
            first_body = first.json()
            replay_body = replay.json()
            assert first_body["state"] == replay_body["state"] == "queued"
            assert replay_body["message_id"] == first_body["message_id"]
            assert "text" not in first_body
            assert "telegram_id" not in first_body
            assert first.headers["cache-control"] == "private, no-store"

            async with case.session_maker() as session:
                message = await session.get(AdminOrderMessage, first_body["message_id"])
                assert message is not None
                assert message.order_id == order_id
                assert message.admin_id == admin_id
                assert message.text == payload["text"]
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(AdminOrderMessage)
                        .where(AdminOrderMessage.order_id == order_id)
                    )
                    == 1
                )
                event = await session.scalar(
                    select(NotificationOutbox).where(
                        NotificationOutbox.event_type == "admin.order_message.queued",
                        NotificationOutbox.aggregate_id == str(order_id),
                    )
                )
                assert event is not None
                assert event.recipient_user_id == case.user_id
                assert event.recipient_admin_id is None
                assert event.payload_id == str(message.id)
                assert event.dedupe_key == f"admin-order-message:{message.id}"

                audit = await session.scalar(
                    select(AdminAuditEvent).where(
                        AdminAuditEvent.actor_admin_id == admin_id,
                        AdminAuditEvent.resource_type == "admin_order_message",
                        AdminAuditEvent.resource_id == str(message.id),
                    )
                )
                assert audit is not None
                assert audit.action == "order_message_queued"
                assert audit.after_json == {
                    "message_id": message.id,
                    "text_length": len(payload["text"]),
                    "text_sha256": sha256(payload["text"].encode("utf-8")).hexdigest(),
                }
                assert payload["text"] not in str(audit.before_json)
                assert payload["text"] not in str(audit.after_json)
                assert "+998901234567" not in str(audit.before_json)
                assert "+998901234567" not in str(audit.after_json)


@pytest.mark.asyncio
async def test_order_message_validation_and_audit(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        async with case.session_maker() as session:
            order = await _make_order(session, case.user_id)
            actor, raw_cookie, csrf_token = await _make_admin_session(
                session, AdminRole.MANAGER
            )
            await session.commit()
            order_id, admin_id = order.id, actor.id

        async with _api_fixture(case, order_ids=[order_id], admin_ids=[admin_id]):
            endpoint = f"/api/v1/admin/orders/{order_id}/message"
            headers = _admin_headers(raw_cookie, csrf_token)
            invalid_payloads = [
                {"text": "", "idempotency_key": str(uuid4())},
                {"text": "   ", "idempotency_key": str(uuid4())},
                {"text": "x" * 4097, "idempotency_key": str(uuid4())},
                {"text": "valid", "idempotency_key": "not-a-uuid"},
                {"text": "valid", "idempotency_key": str(uuid4()), "telegram_id": 123},
                {"text": "valid"},
            ]
            for payload in invalid_payloads:
                response = await case.client.post(endpoint, headers=headers, json=payload)
                assert response.status_code == 422, (payload.keys(), response.text)

            missing_csrf = await case.client.post(
                endpoint,
                headers={
                    "Cookie": f"__Host-kans-admin={raw_cookie}",
                    "Origin": settings.webapp_origin,
                },
                json={"text": "valid", "idempotency_key": str(uuid4())},
            )
            assert missing_csrf.status_code == 403
            assert missing_csrf.json()["error"]["code"] == "CSRF_FAILED"

            max_text = "x" * 4096
            accepted = await case.client.post(
                endpoint,
                headers=headers,
                json={"text": max_text, "idempotency_key": str(uuid4())},
            )
            assert accepted.status_code == 202, accepted.text
            body = accepted.json()
            assert body["state"] == "queued"
            assert body["message_id"] > 0

            async with case.session_maker() as session:
                message = await session.get(AdminOrderMessage, body["message_id"])
                assert message is not None
                event = await session.scalar(
                    select(AdminAuditEvent).where(
                        AdminAuditEvent.actor_admin_id == admin_id,
                        AdminAuditEvent.resource_id == str(message.id),
                        AdminAuditEvent.resource_type == "admin_order_message",
                    )
                )
                assert event is not None
                audit_text = str(event.before_json) + str(event.after_json)
                assert max_text not in audit_text
                assert str(len(max_text)) in audit_text
                assert sha256(max_text.encode("utf-8")).hexdigest() in audit_text


@pytest.mark.asyncio
async def test_legacy_receipt_url_is_not_payment_evidence(
    db_session: AsyncSession, user: User
) -> None:
    from app.services import receipt_service

    has_evidence = getattr(receipt_service, "has_private_receipt_evidence", None)
    assert callable(has_evidence), "receipt_service must expose shared private evidence check"

    order = await _make_order(
        db_session,
        user.id,
        payment_method=PaymentMethod.CARD_TRANSFER,
        payment_status=PaymentStatus.RECEIPT_UPLOADED,
    )
    order.receipt_url = "https://legacy.example.test/receipt.png"
    assert has_evidence(order) is False

    from app.bot.utils.admin_order_card import build_admin_order_keyboard

    keyboard = build_admin_order_keyboard(order, translator=lambda key, **_values: key)
    callback_data = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert not any(value.startswith("apay:") for value in callback_data)


@pytest.mark.asyncio
async def test_bot_message_fsm_rechecks_live_admin_before_queueing(
    db_session: AsyncSession, user: User, admin: Admin
) -> None:
    from app.bot.handlers.admin.orders import on_customer_message_entered

    order = await _make_order(db_session, user.id)
    await db_session.execute(
        update(Admin)
        .where(Admin.id == admin.id)
        .values(is_active=False)
        .execution_options(synchronize_session=False)
    )

    class FakeState:
        def __init__(self) -> None:
            self.data = {"order_id": order.id, "idempotency_key": str(uuid4())}
            self.cleared = False

        async def get_data(self) -> dict[str, object]:
            return self.data

        async def clear(self) -> None:
            self.cleared = True

    class FakeMessage:
        text = "Synthetic delayed FSM message"

        def __init__(self) -> None:
            self.answers: list[str] = []

        async def answer(self, text: str, **_kwargs: object) -> None:
            self.answers.append(text)

    state = FakeState()
    message = FakeMessage()
    await on_customer_message_entered(
        message,
        db_session,
        admin,
        state,
        lambda key, **_values: key,
    )

    assert state.cleared is True
    assert message.answers == ["admin.not_admin_alert"]
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AdminOrderMessage)
            .where(AdminOrderMessage.order_id == order.id)
        )
        == 0
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.aggregate_id == str(order.id))
        )
        == 0
    )

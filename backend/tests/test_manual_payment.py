import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from secrets import token_hex, token_urlsafe

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas.admin import AdminAcceptPaymentIn
from app.core.config import settings
from app.core.exceptions import (
    PaymentAcceptanceUnavailableError,
    ReceiptVersionConflictError,
)
from app.db.models.admin import Admin
from app.db.models.admin_audit_event import AdminAuditEvent
from app.db.models.admin_session import AdminSession
from app.db.models.enums import (
    AdminRole,
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentStatus,
)
from app.db.models.order import Order
from app.db.models.user import User
from app.db.repositories import order_repository
from app.services.manual_payment_service import (
    accept_card_transfer_payment,
    consume_new_acceptance_event,
)
from app.services.receipt_service import attach_card_transfer_receipt
from app.services.receipt_storage import PrivateReceiptStorage

from .api_helpers import make_api_case


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color=(32, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


async def _make_order(session: AsyncSession, user_id: int) -> Order:
    order = Order(
        order_number=f"KANS-{token_hex(6).upper()}",
        user_id=user_id,
        order_type=OrderType.PICKUP,
        status=OrderStatus.NEW,
        customer_name="Manual Payment Test",
        customer_phone="+998901234567",
        subtotal=Decimal("10000"),
        delivery_fee=Decimal("0"),
        discount=Decimal("0"),
        total=Decimal("10000"),
        payment_method=PaymentMethod.CARD_TRANSFER,
        payment_status=PaymentStatus.PENDING,
        receipt_version=0,
        admin_message_ids={},
        source="webapp",
    )
    session.add(order)
    await session.flush()
    return order


async def _upload_receipt(
    session: AsyncSession, order_id: int, user_id: int, storage: PrivateReceiptStorage
) -> Order:
    return await attach_card_transfer_receipt(
        session,
        storage,
        order_id=order_id,
        owner_user_id=user_id,
        content=_png_bytes(),
        declared_content_type="image/png",
    )


async def test_manual_accept_keeps_order_status(
    db_session: AsyncSession, user: User, admin: Admin, tmp_path
) -> None:
    storage = PrivateReceiptStorage(tmp_path / "private")
    order = await _make_order(db_session, user.id)
    order = await _upload_receipt(db_session, order.id, user.id, storage)
    original_status = order.status

    accepted = await accept_card_transfer_payment(
        db_session,
        order_id=order.id,
        admin_id=admin.id,
        expected_receipt_version=1,
    )

    assert accepted.payment_status == PaymentStatus.PAID
    assert accepted.status == original_status
    assert accepted.payment_reviewed_by_admin_id == admin.id
    assert accepted.payment_reviewed_at is not None


async def test_manual_accept_audit_and_replay(
    db_session: AsyncSession, user: User, admin: Admin, tmp_path
) -> None:
    storage = PrivateReceiptStorage(tmp_path / "private")
    order = await _make_order(db_session, user.id)
    order = await _upload_receipt(db_session, order.id, user.id, storage)
    replay_admin = Admin(
        telegram_id=admin.telegram_id + 1,
        full_name="Other active reviewer",
        role=AdminRole.OPERATOR,
    )
    db_session.add(replay_admin)
    await db_session.flush()

    first = await accept_card_transfer_payment(
        db_session,
        order_id=order.id,
        admin_id=admin.id,
        expected_receipt_version=1,
    )
    first_reviewer = first.payment_reviewed_by_admin_id
    first_reviewed_at = first.payment_reviewed_at
    assert consume_new_acceptance_event(db_session, order.id) is True
    order.status = OrderStatus.COMPLETED
    replay = await accept_card_transfer_payment(
        db_session,
        order_id=order.id,
        admin_id=replay_admin.id,
        expected_receipt_version=1,
    )
    audit_count = await db_session.scalar(
        select(func.count())
        .select_from(AdminAuditEvent)
        .where(
            AdminAuditEvent.resource_type == "payment",
            AdminAuditEvent.resource_id == str(order.id),
        )
    )

    assert replay.payment_status == PaymentStatus.PAID
    assert replay.payment_reviewed_by_admin_id == first_reviewer == admin.id
    assert replay.payment_reviewed_at == first_reviewed_at
    assert replay.status == OrderStatus.COMPLETED
    assert replay.status_history == []
    assert consume_new_acceptance_event(db_session, order.id) is False
    assert audit_count == 1
    audit_event = await db_session.scalar(
        select(AdminAuditEvent).where(
            AdminAuditEvent.resource_type == "payment",
            AdminAuditEvent.resource_id == str(order.id),
        )
    )
    assert audit_event is not None
    assert audit_event.actor_admin_id == admin.id
    assert audit_event.action == "manual_card_transfer_payment_accepted"
    assert audit_event.before_json == {
        "order_status": "new",
        "payment_status": "receipt_uploaded",
        "receipt_version": 1,
    }
    assert audit_event.after_json is not None
    assert audit_event.after_json["payment_status"] == "paid"
    assert audit_event.after_json["payment_reviewed_by_admin_id"] == admin.id


async def test_manual_accept_requires_receipt_uploaded_evidence(
    db_session: AsyncSession, user: User, admin: Admin, tmp_path
) -> None:
    no_evidence = await _make_order(db_session, user.id)
    no_evidence.payment_status = PaymentStatus.RECEIPT_UPLOADED
    no_evidence.receipt_version = 1

    cash = await _make_order(db_session, user.id)
    cash.payment_method = PaymentMethod.CASH
    cash.payment_status = PaymentStatus.RECEIPT_UPLOADED
    cash.receipt_version = 1
    cash.receipt_file_id = "synthetic-receipt"

    pending_with_evidence = await _make_order(db_session, user.id)
    pending_with_evidence.receipt_version = 1
    pending_with_evidence.receipt_file_id = "synthetic-receipt"

    terminal = await _make_order(db_session, user.id)
    terminal = await _upload_receipt(
        db_session,
        terminal.id,
        user.id,
        PrivateReceiptStorage(tmp_path / "private"),
    )
    terminal.status = OrderStatus.COMPLETED

    for order in (no_evidence, cash, pending_with_evidence, terminal):
        with pytest.raises(PaymentAcceptanceUnavailableError):
            await accept_card_transfer_payment(
                db_session,
                order_id=order.id,
                admin_id=admin.id,
                expected_receipt_version=1,
            )


async def test_replaced_receipt_invalidates_old_acceptance(test_engine, tmp_path) -> None:
    session_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    storage = PrivateReceiptStorage(tmp_path / "private")
    telegram_id = 8_200_000_000_000_000 + int(token_hex(4), 16)
    async with session_maker() as session:
        user = User(telegram_id=telegram_id, first_name="Replacement race", language="uz")
        admin = Admin(
            telegram_id=telegram_id + 1,
            full_name="Concurrent reviewer",
            role=AdminRole.MANAGER,
        )
        session.add_all([user, admin])
        await session.flush()
        order = await _make_order(session, user.id)
        order = await _upload_receipt(session, order.id, user.id, storage)
        order_id, user_id, admin_id = order.id, user.id, admin.id
        await session.commit()

    replacement_started = asyncio.Event()
    acceptance_started = asyncio.Event()
    try:
        async with session_maker() as replacing_session:
            await order_repository.get_by_id_for_update(replacing_session, order_id)
            replacement_started.set()

            async def accept_old_version() -> Order:
                async with session_maker() as accepting_session:
                    acceptance_started.set()
                    return await accept_card_transfer_payment(
                        accepting_session,
                        order_id=order_id,
                        admin_id=admin_id,
                        expected_receipt_version=1,
                    )

            await replacement_started.wait()
            acceptance = asyncio.create_task(accept_old_version())
            await acceptance_started.wait()
            replaced = await _upload_receipt(replacing_session, order_id, user_id, storage)
            assert replaced.receipt_version == 2
            await replacing_session.commit()

        with pytest.raises(ReceiptVersionConflictError):
            await asyncio.wait_for(acceptance, timeout=5)

        async with session_maker() as accepting_session:
            accepted = await accept_card_transfer_payment(
                accepting_session,
                order_id=order_id,
                admin_id=admin_id,
                expected_receipt_version=2,
            )
            await accepting_session.commit()
            assert accepted.receipt_version == 2
            assert accepted.payment_status == PaymentStatus.PAID
            assert accepted.payment_reviewed_by_admin_id == admin_id

        async with session_maker() as verify_session:
            stored = await order_repository.get_by_id(verify_session, order_id)
            assert stored is not None
            assert stored.receipt_version == 2
            assert stored.payment_status == PaymentStatus.PAID
    finally:
        async with session_maker() as cleanup_session:
            stored = await cleanup_session.get(Order, order_id)
            if stored is not None and stored.receipt_storage_key:
                storage.resolve(stored.receipt_storage_key).unlink(missing_ok=True)
            if stored is not None:
                await cleanup_session.delete(stored)
            await cleanup_session.execute(
                AdminAuditEvent.__table__.delete().where(
                    AdminAuditEvent.resource_type == "payment",
                    AdminAuditEvent.resource_id == str(order_id),
                )
            )
            await cleanup_session.execute(User.__table__.delete().where(User.id == user_id))
            await cleanup_session.execute(Admin.__table__.delete().where(Admin.id == admin_id))
            await cleanup_session.commit()


async def test_manual_accept_authorization(test_engine) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        order_id: int | None = None
        admin_ids: list[int] = []
        receipt_key: str | None = None
        try:
            async with case.session_maker() as session:
                order = await _make_order(session, case.user_id)
                inactive = Admin(
                    telegram_id=8_300_000_000_000_000 + int(token_hex(4), 16),
                    full_name="Inactive order admin",
                    role=AdminRole.SUPERADMIN,
                    is_active=False,
                )
                operator = Admin(
                    telegram_id=8_400_000_000_000_000 + int(token_hex(4), 16),
                    full_name="Active operator",
                    role=AdminRole.OPERATOR,
                )
                session.add_all([inactive, operator])
                await session.flush()
                now = datetime.now(UTC)
                inactive_cookie = token_urlsafe(32)
                operator_cookie = token_urlsafe(32)
                csrf_token = token_urlsafe(48)
                for actor, raw_cookie, csrf in (
                    (inactive, inactive_cookie, token_urlsafe(48)),
                    (operator, operator_cookie, csrf_token),
                ):
                    session.add(
                        AdminSession(
                            admin_id=actor.id,
                            token_hash=sha256(raw_cookie.encode("ascii")).hexdigest(),
                            csrf_token=csrf,
                            auth_epoch=actor.auth_epoch,
                            idle_expires_at=now + timedelta(hours=1),
                            absolute_expires_at=now + timedelta(days=1),
                        )
                    )
                await session.commit()
                order_id = order.id
                admin_ids = [inactive.id, operator.id]

            upload = await case.client.post(
                f"/api/v1/orders/{order_id}/receipt",
                headers={"Authorization": f"Bearer {case.token}"},
                files={"file": ("receipt.png", _png_bytes(), "image/png")},
            )
            assert upload.status_code == 200
            async with case.session_maker() as session:
                stored = await session.get(Order, order_id)
                assert stored is not None
                receipt_key = stored.receipt_storage_key

            endpoint = f"/api/v1/admin/orders/{order_id}/payment/accept"
            payload = AdminAcceptPaymentIn(expected_receipt_version=1).model_dump()
            anonymous = await case.client.post(endpoint, json=payload)
            assert anonymous.status_code == 401
            assert anonymous.json()["error"]["code"] == "ADMIN_SESSION_REQUIRED"
            bearer_only = await case.client.post(
                endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {case.token}"},
            )
            assert bearer_only.status_code == 401

            inactive_response = await case.client.post(
                endpoint,
                json=payload,
                headers={
                    "Cookie": f"__Host-kans-admin={inactive_cookie}",
                    "Origin": settings.webapp_origin,
                    "X-CSRF-Token": token_urlsafe(48),
                },
            )
            assert inactive_response.status_code == 401

            missing_csrf = await case.client.post(
                endpoint,
                json=payload,
                headers={
                    "Cookie": f"__Host-kans-admin={operator_cookie}",
                    "Origin": settings.webapp_origin,
                },
            )
            assert missing_csrf.status_code == 403
            assert missing_csrf.json()["error"]["code"] == "CSRF_FAILED"

            boolean_version = await case.client.post(
                endpoint,
                json={"expected_receipt_version": True},
                headers={
                    "Cookie": f"__Host-kans-admin={operator_cookie}",
                    "Origin": settings.webapp_origin,
                    "X-CSRF-Token": csrf_token,
                },
            )
            assert boolean_version.status_code == 422

            accepted = await case.client.post(
                endpoint,
                json=payload,
                headers={
                    "Cookie": f"__Host-kans-admin={operator_cookie}",
                    "Origin": settings.webapp_origin,
                    "X-CSRF-Token": csrf_token,
                },
            )
            assert accepted.status_code == 200
            body = accepted.json()
            assert body["payment_status"] == "paid"
            assert body["payment_reviewed_by_admin_id"] == admin_ids[1]
            assert body["payment_reviewed_at"] is not None
            assert body["status"] == "new"

            stale = await case.client.post(
                endpoint,
                json={"expected_receipt_version": 0},
                headers={
                    "Cookie": f"__Host-kans-admin={operator_cookie}",
                    "Origin": settings.webapp_origin,
                    "X-CSRF-Token": csrf_token,
                },
            )
            assert stale.status_code == 409
            assert stale.json()["error"]["code"] == "RECEIPT_VERSION_CONFLICT"

            client_actor_fields = await case.client.post(
                endpoint,
                json={
                    "expected_receipt_version": 1,
                    "admin_id": admin_ids[0],
                    "role": "superadmin",
                },
                headers={
                    "Cookie": f"__Host-kans-admin={operator_cookie}",
                    "Origin": settings.webapp_origin,
                    "X-CSRF-Token": csrf_token,
                },
            )
            assert client_actor_fields.status_code == 422
        finally:
            if order_id is not None:
                if receipt_key:
                    (settings.private_media_root_path / receipt_key).unlink(missing_ok=True)
                async with case.session_maker() as session:
                    await session.execute(
                        AdminAuditEvent.__table__.delete().where(
                            AdminAuditEvent.resource_type == "payment",
                            AdminAuditEvent.resource_id == str(order_id),
                        )
                    )
                    await session.execute(Order.__table__.delete().where(Order.id == order_id))
                    if admin_ids:
                        await session.execute(
                            AdminSession.__table__.delete().where(
                                AdminSession.admin_id.in_(admin_ids)
                            )
                        )
                        await session.execute(
                            Admin.__table__.delete().where(Admin.id.in_(admin_ids))
                        )
                    await session.commit()

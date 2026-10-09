from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models.admin import Admin
from app.db.models.admin_audit_event import AdminAuditEvent
from app.db.models.admin_session import AdminSession
from app.db.models.enums import AdminRole
from app.db.models.notification_outbox import NotificationOutbox
from app.db.models.user import User


async def test_audit_redacts_sensitive_values_and_rolls_back_with_write(
    db_session: AsyncSession, user: User, admin: Admin
) -> None:
    try:
        from app.services.admin_audit_service import write_audit_event
        from app.services.notification_outbox_service import enqueue_outbox_event
    except ImportError:
        pytest.fail("audit and outbox services are missing")

    user_id = user.id
    business_transaction = await db_session.begin_nested()
    user.is_blocked = True
    event = await write_audit_event(
        db_session,
        admin_id=admin.id,
        action="user.block",
        entity="user",
        entity_id=user.id,
        request_id="req-audit-redaction-0001",
        before={
            "phone": "+998901234567",
            "payment": {
                "card_number": "8600 1234 5678 9012",
                "payment_card": {"number": "4111 1111 1111 9876", "holder": "Test"},
                "csrf_token": "full-csrf-token-value",
                "receipt_version": 3,
                "receipt_bytes": "base64-encoded-receipt-bytes",
                "raw_gateway_payload": {"Authorization": "secret-provider-value"},
            },
            "login_code": "734921",
        },
        after={"is_blocked": True},
    )
    await enqueue_outbox_event(
        db_session,
        event_type="user.blocked",
        aggregate_id=user_id,
        dedupe_key=f"user:{user_id}:blocked",
        recipient_admin_id=admin.id,
    )
    assert event.before_json == {
        "payment": {
            "card_number": "****9012",
            "payment_card": "****9876",
            "receipt_version": 3,
        }
    }

    await db_session.flush()
    await business_transaction.rollback()

    remaining = await db_session.scalar(
        select(func.count())
        .select_from(AdminAuditEvent)
        .where(AdminAuditEvent.request_id == "req-audit-redaction-0001")
    )
    assert remaining == 0
    remaining_outbox = await db_session.scalar(
        select(func.count())
        .select_from(NotificationOutbox)
        .where(NotificationOutbox.dedupe_key == f"user:{user_id}:blocked")
    )
    assert remaining_outbox == 0
    blocked_after_rollback = await db_session.scalar(
        select(User.is_blocked).where(User.id == user_id)
    )
    assert blocked_after_rollback is False


async def test_outbox_dedupe_is_transactional(db_session: AsyncSession, user: User) -> None:
    try:
        from app.services.notification_outbox_service import enqueue_outbox_event
    except ImportError:
        pytest.fail("notification_outbox_service.enqueue_outbox_event is missing")

    first = await enqueue_outbox_event(
        db_session,
        event_type="order.confirmed",
        aggregate_id=91,
        dedupe_key="order:91:confirmed:user:1",
        recipient_user_id=user.id,
    )
    duplicate = await enqueue_outbox_event(
        db_session,
        event_type="order.delivering",
        aggregate_id=92,
        dedupe_key="order:91:confirmed:user:1",
        recipient_user_id=user.id,
        payload_id=19,
    )
    assert duplicate.id == first.id
    assert duplicate.event_type == "order.confirmed"
    assert duplicate.aggregate_id == "91"

    await db_session.flush()
    await db_session.rollback()

    remaining = await db_session.scalar(
        select(func.count())
        .select_from(NotificationOutbox)
        .where(NotificationOutbox.dedupe_key == "order:91:confirmed:user:1")
    )
    assert remaining == 0


async def test_audit_actor_name_survives_admin_hard_delete(
    db_session: AsyncSession, admin: Admin
) -> None:
    try:
        from app.services.admin_audit_service import write_audit_event
    except ImportError:
        pytest.fail("admin_audit_service.write_audit_event is missing")

    admin_id = admin.id
    event = await write_audit_event(
        db_session,
        admin_id=admin_id,
        action="product.update",
        entity="product",
        entity_id=23,
        request_id="req-actor-snapshot-delete",
        before={"price": "5000"},
        after={"price": "6000"},
    )
    event_id = event.id
    assert event.actor_name_snapshot == "Test Admin"

    await db_session.execute(delete(Admin).where(Admin.id == admin_id))
    preserved = (
        await db_session.execute(
            select(AdminAuditEvent.actor_admin_id, AdminAuditEvent.actor_name_snapshot).where(
                AdminAuditEvent.id == event_id
            )
        )
    ).one()
    assert preserved == (None, "Test Admin")


async def test_audit_visibility_roles(test_engine: AsyncEngine) -> None:
    """Audit scopes are computed from the role attached to the live cookie session."""
    from .api_helpers import make_api_case

    async with make_api_case(test_engine, base_url="https://testserver") as case:
        actors: dict[AdminRole, Admin] = {}
        async with case.session_maker() as session:
            for index, role in enumerate(
                (AdminRole.SUPERADMIN, AdminRole.MANAGER, AdminRole.OPERATOR), start=1
            ):
                actor = Admin(
                    telegram_id=9_111_000_000_000_000 + index,
                    full_name=f"Audit {role.value}",
                    role=role,
                )
                session.add(actor)
                actors[role] = actor
            await session.flush()
            superadmin_id = actors[AdminRole.SUPERADMIN].id
            manager_id = actors[AdminRole.MANAGER].id
            operator_id = actors[AdminRole.OPERATOR].id
            session.add_all(
                [
                    AdminAuditEvent(
                        actor_admin_id=superadmin_id,
                        action="order.status",
                        resource_type="order",
                        resource_id="91",
                        request_id="audit-visibility-order",
                    ),
                    AdminAuditEvent(
                        actor_admin_id=manager_id,
                        action="product.update",
                        resource_type="product",
                        resource_id="17",
                        request_id="audit-visibility-product",
                    ),
                    AdminAuditEvent(
                        actor_admin_id=operator_id,
                        action="order.status",
                        resource_type="order",
                        resource_id="92",
                        request_id="audit-visibility-operator-order",
                    ),
                    AdminAuditEvent(
                        actor_admin_id=operator_id,
                        action="customer.block",
                        resource_type="customer",
                        resource_id="19",
                        request_id="audit-visibility-customer",
                    ),
                    AdminAuditEvent(
                        actor_admin_id=operator_id,
                        action="team.role",
                        resource_type="team",
                        resource_id="8",
                        request_id="audit-visibility-team",
                    ),
                    AdminAuditEvent(
                        actor_admin_id=operator_id,
                        action="session.revoke",
                        resource_type="admin_session",
                        resource_id="4",
                        request_id="audit-visibility-session",
                    ),
                ]
            )
            await session.commit()

        async def issue_cookie(admin: Admin) -> None:
            raw_token = token_urlsafe(32)
            now = datetime.now(UTC)
            async with case.session_maker() as session:
                session.add(
                    AdminSession(
                        admin_id=admin.id,
                        token_hash=sha256(raw_token.encode("ascii")).hexdigest(),
                        csrf_token=token_urlsafe(96),
                        auth_epoch=admin.auth_epoch,
                        idle_expires_at=now + timedelta(hours=12),
                        absolute_expires_at=now + timedelta(days=7),
                    )
                )
                await session.commit()
            case.client.cookies.set("__Host-kans-admin", raw_token, path="/")

        try:
            await issue_cookie(actors[AdminRole.SUPERADMIN])
            superadmin_response = await case.client.get("/api/v1/admin/audit")
            assert superadmin_response.status_code == 200
            assert superadmin_response.headers["cache-control"] == "private, no-store"
            assert {item["request_id"] for item in superadmin_response.json()["items"]} == {
                "audit-visibility-order",
                "audit-visibility-product",
                "audit-visibility-team",
                "audit-visibility-session",
                "audit-visibility-operator-order",
                "audit-visibility-customer",
            }
            product_filter_response = await case.client.get(
                "/api/v1/admin/audit?resource_type=product&limit=5"
            )
            assert product_filter_response.status_code == 200
            assert [
                item["request_id"] for item in product_filter_response.json()["items"]
            ] == ["audit-visibility-product"]
            assert product_filter_response.json()["total"] == 1

            await issue_cookie(actors[AdminRole.MANAGER])
            manager_response = await case.client.get("/api/v1/admin/audit")
            assert manager_response.status_code == 200
            assert {item["request_id"] for item in manager_response.json()["items"]} == {
                "audit-visibility-order",
                "audit-visibility-product",
                "audit-visibility-operator-order",
                "audit-visibility-customer",
            }

            await issue_cookie(actors[AdminRole.OPERATOR])
            operator_response = await case.client.get("/api/v1/admin/audit")
            assert operator_response.status_code == 200
            assert {item["request_id"] for item in operator_response.json()["items"]} == {
                "audit-visibility-operator-order",
            }
        finally:
            async with case.session_maker() as session:
                await session.execute(
                    delete(AdminAuditEvent).where(
                        AdminAuditEvent.request_id.in_(
                            [
                                "audit-visibility-order",
                                "audit-visibility-product",
                                "audit-visibility-team",
                                "audit-visibility-session",
                                "audit-visibility-operator-order",
                                "audit-visibility-customer",
                            ]
                        )
                    )
                )
                await session.execute(
                    delete(Admin).where(Admin.id.in_([superadmin_id, manager_id, operator_id]))
                )
                await session.commit()

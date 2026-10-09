from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.admin_security import ADMIN_COOKIE_NAME
from app.api.deps import get_db
from app.core.config import settings
from app.db.models.admin import Admin
from app.db.models.admin_audit_event import AdminAuditEvent
from app.db.models.admin_session import AdminSession
from app.db.models.enums import AdminRole
from app.db.models.notification_outbox import NotificationOutbox
from app.db.seed import seed_admins
from app.services import admin_team_service
from tests.api_helpers import ApiCase, make_api_case

_TEAM_TEST_ADMIN_IDS: dict[int, set[int]] = {}


@asynccontextmanager
async def _superadmin_cookie(
    case: ApiCase, *, role: AdminRole = AdminRole.SUPERADMIN
) -> AsyncIterator[tuple[Admin, str]]:
    raw_cookie = token_urlsafe(32)
    csrf_token = token_urlsafe(64)
    now = datetime.now(UTC)
    async with case.session_maker() as session:
        actor = Admin(
            telegram_id=9_300_000_000_000_000 + int(now.timestamp() * 1_000_000),
            full_name="Team Actor",
            role=role,
        )
        session.add(actor)
        await session.flush()
        session.add(
            AdminSession(
                admin_id=actor.id,
                token_hash=sha256(raw_cookie.encode("ascii")).hexdigest(),
                csrf_token=csrf_token,
                auth_epoch=actor.auth_epoch,
                idle_expires_at=now + timedelta(hours=12),
                absolute_expires_at=now + timedelta(days=7),
            )
        )
        await session.commit()
        await session.refresh(actor)
        _TEAM_TEST_ADMIN_IDS[id(case)] = {actor.id}
    case.client.cookies.set(ADMIN_COOKIE_NAME, raw_cookie, path="/")
    try:
        yield actor, csrf_token
    finally:
        async with case.session_maker() as session:
            admin_ids = _TEAM_TEST_ADMIN_IDS.pop(id(case), {actor.id})
            await session.execute(delete(Admin).where(Admin.id.in_(admin_ids)))
            await session.commit()


def _csrf_headers(csrf_token: str) -> dict[str, str]:
    return {"Origin": settings.webapp_origin, "X-CSRF-Token": csrf_token}


async def _create_admin(
    case: ApiCase, *, role: AdminRole = AdminRole.OPERATOR, is_active: bool = True
) -> Admin:
    async with case.session_maker() as session:
        admin = Admin(
            telegram_id=9_400_000_000_000_000 + int(datetime.now(UTC).timestamp() * 1_000_000),
            full_name="Team Target",
            role=role,
            is_active=is_active,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        _TEAM_TEST_ADMIN_IDS.setdefault(id(case), set()).add(admin.id)
        return admin


async def _attach_admin_cookie(case: ApiCase, client: httpx.AsyncClient, admin: Admin) -> str:
    raw_cookie = token_urlsafe(32)
    csrf_token = token_urlsafe(64)
    now = datetime.now(UTC)
    async with case.session_maker() as session:
        current = await session.get(Admin, admin.id)
        assert current is not None
        session.add(
            AdminSession(
                admin_id=current.id,
                token_hash=sha256(raw_cookie.encode("ascii")).hexdigest(),
                csrf_token=csrf_token,
                auth_epoch=current.auth_epoch,
                idle_expires_at=now + timedelta(hours=12),
                absolute_expires_at=now + timedelta(days=7),
            )
        )
        await session.commit()
    client.cookies.set(ADMIN_COOKIE_NAME, raw_cookie, path="/")
    return csrf_token


@pytest.mark.asyncio
async def test_team_roles_and_self_delete(test_engine: AsyncEngine) -> None:
    async with (
        make_api_case(test_engine, base_url="https://testserver") as case,
        _superadmin_cookie(case) as (actor, csrf_token),
    ):
        headers = _csrf_headers(csrf_token)
        listed = await case.client.get("/api/v1/admin/team")
        assert listed.status_code == 200
        assert listed.json()["items"]

        created = await case.client.post(
            "/api/v1/admin/team",
            headers=headers,
            json={
                "telegram_id": 9_500_000_000_000_123,
                "full_name": "New operator",
                "role": "operator",
            },
        )
        assert created.status_code == 201
        added = created.json()
        assert added["role"] == "operator"
        assert added["is_active"] is True
        assert added["notifications_enabled"] is True

        promoted = await case.client.patch(
            f"/api/v1/admin/team/{added['id']}",
            headers=headers,
            json={"role": "manager"},
        )
        assert promoted.status_code == 200
        assert promoted.json()["role"] == "manager"

        toggled = await case.client.patch(
            f"/api/v1/admin/team/{added['id']}",
            headers=headers,
            json={"is_active": False, "notifications_enabled": False},
        )
        assert toggled.status_code == 200
        assert toggled.json()["is_active"] is False
        assert toggled.json()["notifications_enabled"] is False

        self_delete = await case.client.delete(
            f"/api/v1/admin/team/{actor.id}", headers=headers
        )
        assert self_delete.status_code == 403
        assert self_delete.json()["error"]["code"] == "FORBIDDEN"

        peer = await _create_admin(case, role=AdminRole.MANAGER)
        removed = await case.client.delete(
            f"/api/v1/admin/team/{added['id']}", headers=headers
        )
        assert removed.status_code == 204

        async with case.session_maker() as session:
            deletion_event = await session.scalar(
                select(AdminAuditEvent).where(
                    AdminAuditEvent.action == "admin.team.remove",
                    AdminAuditEvent.resource_id == str(added["id"]),
                )
            )
            assert deletion_event is not None
            assert deletion_event.before_json is not None
            assert deletion_event.before_json["full_name"] == "New operator"
            assert deletion_event.after_json is not None
            assert "auth_epoch" not in deletion_event.after_json
            queued = list(
                (
                    await session.scalars(
                        select(NotificationOutbox).where(
                            NotificationOutbox.event_type == "admin.team.changed",
                            NotificationOutbox.payload_id == str(deletion_event.id),
                        )
                    )
                ).all()
            )
            assert [event.recipient_admin_id for event in queued] == [peer.id]
            current_admin_ids = set((await session.scalars(select(Admin.id))).all())
            assert all(event.recipient_admin_id in current_admin_ids for event in queued)


@pytest.mark.asyncio
async def test_last_superadmin_single_mutation(test_engine: AsyncEngine) -> None:
    async with (
        make_api_case(test_engine, base_url="https://testserver") as case,
        _superadmin_cookie(case) as (actor, csrf_token),
    ):
        headers = _csrf_headers(csrf_token)
        demote = await case.client.patch(
            f"/api/v1/admin/team/{actor.id}",
            headers=headers,
            json={"role": "manager"},
        )
        deactivate = await case.client.patch(
            f"/api/v1/admin/team/{actor.id}",
            headers=headers,
            json={"is_active": False},
        )
        assert demote.status_code == 409
        assert demote.json()["error"]["code"] == "LAST_SUPERADMIN_REQUIRED"
        assert deactivate.status_code == 409
        assert deactivate.json()["error"]["code"] == "LAST_SUPERADMIN_REQUIRED"

        async with case.session_maker() as session:
            active_count = await session.scalar(
                select(func.count())
                .select_from(Admin)
                .where(Admin.role == AdminRole.SUPERADMIN, Admin.is_active.is_(True))
            )
            assert active_count is not None and active_count >= 1


@pytest.mark.asyncio
async def test_concurrent_last_superadmin_changes_keep_one_active(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    async with (
        make_api_case(test_engine, base_url="https://testserver") as case,
        _superadmin_cookie(case) as (first, csrf_token),
    ):
        second = await _create_admin(case, role=AdminRole.SUPERADMIN)
        assert second.id != first.id
        async with case.session_maker() as session:
            initial_active_count = await session.scalar(
                select(func.count())
                .select_from(Admin)
                .where(Admin.role == AdminRole.SUPERADMIN, Admin.is_active.is_(True))
            )
            assert initial_active_count == 2
        second_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=case.app), base_url="https://testserver"
        )
        second_csrf_token = await _attach_admin_cookie(case, second_client, second)
        second_session = await second_client.get("/api/v1/auth/admin/session")
        assert second_session.status_code == 200
        original_acquire_lock = admin_team_service._acquire_team_lock
        arrival_barrier = asyncio.Barrier(2)

        async def wait_then_acquire_lock(session) -> None:
            # Both requests pass cookie/role authorization before either tries the lock.
            await asyncio.wait_for(arrival_barrier.wait(), timeout=5)
            await original_acquire_lock(session)

        monkeypatch.setattr(admin_team_service, "_acquire_team_lock", wait_then_acquire_lock)
        try:
            first_request = case.client.patch(
                f"/api/v1/admin/team/{first.id}",
                headers=_csrf_headers(csrf_token),
                json={"role": "manager"},
            )
            second_request = second_client.patch(
                f"/api/v1/admin/team/{second.id}",
                headers=_csrf_headers(second_csrf_token),
                json={"role": "manager"},
            )
            responses = await asyncio.gather(first_request, second_request)
        finally:
            await second_client.aclose()

        assert sorted(response.status_code for response in responses) == [200, 409]
        conflicts = [response for response in responses if response.status_code == 409]
        assert conflicts[0].json()["error"]["code"] == "LAST_SUPERADMIN_REQUIRED"
        async with case.session_maker() as session:
            active_count = await session.scalar(
                select(func.count())
                .select_from(Admin)
                .where(Admin.role == AdminRole.SUPERADMIN, Admin.is_active.is_(True))
            )
            assert active_count is not None and active_count >= 1


@pytest.mark.asyncio
async def test_role_change_revokes_sessions_and_epoch(test_engine: AsyncEngine) -> None:
    async with (
        make_api_case(test_engine, base_url="https://testserver") as case,
        _superadmin_cookie(case) as (_actor, csrf_token),
    ):
        target = await _create_admin(case)
        target_cookie = token_urlsafe(32)
        target_csrf = token_urlsafe(64)
        now = datetime.now(UTC)
        async with case.session_maker() as session:
            current = await session.get(Admin, target.id)
            assert current is not None
            session.add(
                AdminSession(
                    admin_id=current.id,
                    token_hash=sha256(target_cookie.encode("ascii")).hexdigest(),
                    csrf_token=target_csrf,
                    auth_epoch=current.auth_epoch,
                    idle_expires_at=now + timedelta(hours=12),
                    absolute_expires_at=now + timedelta(days=7),
                )
            )
            await session.commit()

        changed = await case.client.patch(
            f"/api/v1/admin/team/{target.id}",
            headers=_csrf_headers(csrf_token),
            json={"role": "manager"},
        )
        assert changed.status_code == 200

        async with case.session_maker() as session:
            current = await session.get(Admin, target.id)
            stored = await session.scalar(
                select(AdminSession).where(AdminSession.admin_id == target.id)
            )
            assert current is not None and current.auth_epoch == 1
            assert stored is not None and stored.revoked_at is not None

        rejected = await case.client.get(
            "/api/v1/auth/admin/session",
            headers={"Cookie": f"{ADMIN_COOKIE_NAME}={target_cookie}"},
        )
        assert rejected.status_code == 401

        second_cookie = token_urlsafe(32)
        second_csrf = token_urlsafe(64)
        async with case.session_maker() as session:
            current = await session.get(Admin, target.id)
            assert current is not None
            session.add(
                AdminSession(
                    admin_id=current.id,
                    token_hash=sha256(second_cookie.encode("ascii")).hexdigest(),
                    csrf_token=second_csrf,
                    auth_epoch=current.auth_epoch,
                    idle_expires_at=now + timedelta(hours=12),
                    absolute_expires_at=now + timedelta(days=7),
                )
            )
            await session.commit()

        revoked = await case.client.post(
            f"/api/v1/admin/team/{target.id}/sessions/revoke",
            headers=_csrf_headers(csrf_token),
        )
        assert revoked.status_code == 200
        assert revoked.json() == {"revoked_sessions": 1}
        revoked_cookie = await case.client.get(
            "/api/v1/auth/admin/session",
            headers={"Cookie": f"{ADMIN_COOKIE_NAME}={second_cookie}"},
        )
        assert revoked_cookie.status_code == 401

        third_cookie = token_urlsafe(32)
        third_csrf = token_urlsafe(64)
        async with case.session_maker() as session:
            current = await session.get(Admin, target.id)
            assert current is not None and current.auth_epoch == 2
            session.add(
                AdminSession(
                    admin_id=current.id,
                    token_hash=sha256(third_cookie.encode("ascii")).hexdigest(),
                    csrf_token=third_csrf,
                    auth_epoch=current.auth_epoch,
                    idle_expires_at=now + timedelta(hours=12),
                    absolute_expires_at=now + timedelta(days=7),
                )
            )
            await session.commit()

        deactivated = await case.client.patch(
            f"/api/v1/admin/team/{target.id}",
            headers=_csrf_headers(csrf_token),
            json={"is_active": False},
        )
        assert deactivated.status_code == 200
        async with case.session_maker() as session:
            current = await session.get(Admin, target.id)
            stored = await session.scalar(
                select(AdminSession).where(
                    AdminSession.token_hash == sha256(third_cookie.encode("ascii")).hexdigest()
                )
            )
            assert current is not None and current.auth_epoch == 3
            assert stored is not None and stored.revoked_at is not None
        deactivated_cookie = await case.client.get(
            "/api/v1/auth/admin/session",
            headers={"Cookie": f"{ADMIN_COOKIE_NAME}={third_cookie}"},
        )
        assert deactivated_cookie.status_code == 401

        reactivated = await case.client.patch(
            f"/api/v1/admin/team/{target.id}",
            headers=_csrf_headers(csrf_token),
            json={"is_active": True},
        )
        assert reactivated.status_code == 200
        removal_cookie = token_urlsafe(32)
        removal_csrf = token_urlsafe(64)
        async with case.session_maker() as session:
            current = await session.get(Admin, target.id)
            assert current is not None and current.auth_epoch == 4
            session.add(
                AdminSession(
                    admin_id=current.id,
                    token_hash=sha256(removal_cookie.encode("ascii")).hexdigest(),
                    csrf_token=removal_csrf,
                    auth_epoch=current.auth_epoch,
                    idle_expires_at=now + timedelta(hours=12),
                    absolute_expires_at=now + timedelta(days=7),
                )
            )
            await session.commit()
        removed = await case.client.delete(
            f"/api/v1/admin/team/{target.id}", headers=_csrf_headers(csrf_token)
        )
        assert removed.status_code == 204
        removed_cookie = await case.client.get(
            "/api/v1/auth/admin/session",
            headers={"Cookie": f"{ADMIN_COOKIE_NAME}={removal_cookie}"},
        )
        assert removed_cookie.status_code == 401


@pytest.mark.asyncio
async def test_self_deactivation_keeps_audit_and_revokes_session(
    test_engine: AsyncEngine,
) -> None:
    async with (
        make_api_case(test_engine, base_url="https://testserver") as case,
        _superadmin_cookie(case) as (actor, csrf_token),
    ):
        backup = await _create_admin(case, role=AdminRole.SUPERADMIN)
        response = await case.client.patch(
            f"/api/v1/admin/team/{actor.id}",
            headers=_csrf_headers(csrf_token),
            json={"is_active": False},
        )

        assert response.status_code == 200
        assert response.json()["is_active"] is False
        async with case.session_maker() as session:
            current = await session.get(Admin, actor.id)
            current_session = await session.scalar(
                select(AdminSession).where(AdminSession.admin_id == actor.id)
            )
            audit = await session.scalar(
                select(AdminAuditEvent).where(
                    AdminAuditEvent.action == "admin.team.update",
                    AdminAuditEvent.actor_admin_id == actor.id,
                    AdminAuditEvent.resource_id == str(actor.id),
                )
            )
            active_count = await session.scalar(
                select(func.count())
                .select_from(Admin)
                .where(Admin.role == AdminRole.SUPERADMIN, Admin.is_active.is_(True))
            )
            assert current is not None and current.is_active is False
            assert current.auth_epoch == 1
            assert current_session is not None and current_session.revoked_at is not None
            assert audit is not None
            assert audit.before_json == {
                "id": actor.id,
                "telegram_id": actor.telegram_id,
                "full_name": actor.full_name,
                "role": AdminRole.SUPERADMIN.value,
                "is_active": True,
                "notifications_enabled": True,
            }
            assert audit.after_json == {
                "id": actor.id,
                "telegram_id": actor.telegram_id,
                "full_name": actor.full_name,
                "role": AdminRole.SUPERADMIN.value,
                "is_active": False,
                "notifications_enabled": True,
            }
            assert active_count == 1
            assert backup.is_active is True

        expired = await case.client.get("/api/v1/auth/admin/session")
        assert expired.status_code == 401


@pytest.mark.asyncio
async def test_seed_does_not_reactivate_existing_admin(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = Admin(
        telegram_id=9_600_000_000_000_123,
        full_name="Existing manager",
        role=AdminRole.MANAGER,
        is_active=False,
        notifications_enabled=False,
    )
    db_session.add(existing)
    await db_session.flush()
    monkeypatch.setattr(
        "app.db.seed.settings", SimpleNamespace(admin_ids_list=[existing.telegram_id])
    )

    await seed_admins(db_session)
    await db_session.refresh(existing)

    assert existing.role == AdminRole.MANAGER
    assert existing.is_active is False
    assert existing.notifications_enabled is False


@pytest.mark.asyncio
async def test_team_routes_require_superadmin(test_engine: AsyncEngine) -> None:
    async with (
        make_api_case(test_engine, base_url="https://testserver") as case,
        _superadmin_cookie(case, role=AdminRole.MANAGER) as (_actor, _csrf_token),
    ):
        response = await case.client.get("/api/v1/admin/team")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ADMIN_ROLE_REQUIRED"


def test_admin_team_routes_use_function_scoped_sessions() -> None:
    from fastapi.routing import APIRoute

    from app.api.v1.admin import team as admin_team_routes

    for route in admin_team_routes.router.routes:
        if not isinstance(route, APIRoute):
            continue
        session_dependencies = [
            dependency
            for dependency in route.dependant.dependencies
            if dependency.call is get_db
        ]
        assert len(session_dependencies) == 1, route.path
        assert session_dependencies[0].scope == "function", route.path

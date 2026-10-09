from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.admin_security import ADMIN_COOKIE_NAME
from app.api.deps import get_db
from app.api.v1.admin import settings as admin_settings_routes
from app.api.v1.admin import users as admin_user_routes
from app.core.config import settings
from app.core.exceptions import ForbiddenError
from app.db.models.admin import Admin
from app.db.models.admin_session import AdminSession
from app.db.models.enums import AdminRole
from app.db.models.traffic_source import TrafficSource
from app.db.models.user import User
from app.services import customer_admin_service
from tests.api_helpers import ApiCase, make_api_case


@asynccontextmanager
async def _admin_cookie(case: ApiCase, *, role: AdminRole) -> AsyncIterator[tuple[int, str]]:
    raw_cookie = token_urlsafe(32)
    csrf_token = token_urlsafe(64)
    now = datetime.now(UTC)
    async with case.session_maker() as session:
        admin = Admin(
            telegram_id=9_200_000_000_000_000 + int(datetime.now(UTC).timestamp() * 1_000_000),
            full_name=f"Customer API {role.value}",
            role=role,
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
        yield admin_id, csrf_token
    finally:
        async with case.session_maker() as session:
            await session.execute(delete(Admin).where(Admin.id == admin_id))
            await session.commit()


async def _set_phone(case: ApiCase, user_id: int, phone: str) -> None:
    async with case.session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.phone = phone
        await session.commit()


@pytest.mark.asyncio
async def test_user_phone_masking_and_block_auth(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        full_phone = "+998901234567"
        await _set_phone(case, case.user_id, full_phone)

        async with _admin_cookie(case, role=AdminRole.MANAGER) as (_admin_id, csrf_token):
            listed = await case.client.get("/api/v1/admin/users")
            assert listed.status_code == 200
            listed_user = next(
                item for item in listed.json()["items"] if item["id"] == case.user_id
            )
            assert listed_user["phone"] != full_phone
            assert listed_user["phone"].endswith("4567")

            detail = await case.client.get(f"/api/v1/admin/users/{case.user_id}")
            assert detail.status_code == 200
            assert detail.json()["phone"] == full_phone
            assert detail.json()["orders_count"] == 0
            assert detail.json()["first_touch_source"] is None

            blocked = await case.client.patch(
                f"/api/v1/admin/users/{case.user_id}/block",
                headers={
                    "Origin": settings.webapp_origin,
                    "X-CSRF-Token": csrf_token,
                },
                json={"blocked": True},
            )
            assert blocked.status_code == 200
            assert blocked.json()["is_blocked"] is True

            buyer_after_block = await case.client.get(
                "/api/v1/cart", headers={"Authorization": f"Bearer {case.token}"}
            )
            assert buyer_after_block.status_code == 403
            assert buyer_after_block.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_customer_admin_roles_and_operator_order_only(
    test_engine: AsyncEngine,
) -> None:
    async with make_api_case(  # noqa: SIM117
        test_engine, base_url="https://testserver"
    ) as case:
        async with _admin_cookie(case, role=AdminRole.OPERATOR) as (admin_id, _csrf_token):
            users_response = await case.client.get("/api/v1/admin/users")
            orders_response = await case.client.get("/api/v1/admin/orders")
            detail_response = await case.client.get(f"/api/v1/admin/users/{case.user_id}")

            assert users_response.status_code == 403
            assert orders_response.status_code == 200
            assert detail_response.status_code == 403

            async with case.session_maker() as session:
                with pytest.raises(ForbiddenError):
                    await customer_admin_service.list_admin_users(
                        session,
                        admin_id=admin_id,
                        query=None,
                        page=1,
                        limit=20,
                    )


@pytest.mark.asyncio
async def test_customer_detail_includes_only_first_touch_source(
    db_session: AsyncSession, admin: Admin, user: User
) -> None:
    user.traffic_source_id = None
    source = TrafficSource(code="first-touch", name="Instagram")
    db_session.add(source)
    await db_session.flush()
    user.traffic_source_id = source.id
    user.phone = "+998901234567"
    await db_session.flush()

    detail = await customer_admin_service.get_admin_user(
        db_session, admin_id=admin.id, user_id=user.id
    )

    assert detail.phone == "+998901234567"
    assert detail.orders_count == 0
    assert detail.first_touch_source is not None
    assert detail.first_touch_source.model_dump() == {
        "id": source.id,
        "name": "Instagram",
        "code": "first-touch",
    }
    matching_users = await customer_admin_service.list_admin_users(
        db_session,
        admin_id=admin.id,
        query="Test",
        page=1,
        limit=1,
    )
    assert matching_users.total == 1
    assert [item.id for item in matching_users.items] == [user.id]


@pytest.mark.asyncio
async def test_customer_admin_reads_recheck_live_role(
    db_session: AsyncSession, admin: Admin
) -> None:
    admin.role = AdminRole.OPERATOR
    await db_session.flush()

    with pytest.raises(ForbiddenError):
        await customer_admin_service.list_admin_users(
            db_session, admin_id=admin.id, query=None, page=1, limit=20
        )


def test_customer_and_settings_routes_use_function_scoped_sessions() -> None:
    for router in (admin_user_routes.router, admin_settings_routes.router):
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            session_dependencies = [
                dependency
                for dependency in route.dependant.dependencies
                if dependency.call is get_db
            ]
            assert len(session_dependencies) == 1, route.path
            assert session_dependencies[0].scope == "function", route.path

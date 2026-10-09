import importlib
import secrets
from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack, asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings
from app.core.security import create_access_token
from app.db.models.admin import Admin
from app.db.models.admin_session import AdminSession
from app.db.models.enums import AdminRole
from app.db.models.user import User

from .api_helpers import ApiCase, make_api_case

ADMIN_COOKIE = "__Host-kans-admin"
WEBAPP_ORIGIN = (
    f"{urlsplit(settings.webapp_url).scheme}://{urlsplit(settings.webapp_url).netloc}"
)


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[Redis]:
    connection = Redis.from_url(settings.redis_url, decode_responses=True)
    existing_admin_codes = set(await connection.keys("admin_login:*"))
    yield connection
    created_admin_codes = set(await connection.keys("admin_login:*")) - existing_admin_codes
    if created_admin_codes:
        await connection.delete(*created_admin_codes)
    await connection.aclose()


@contextmanager
def _use_real_redis(redis: Redis) -> Iterator[None]:
    with ExitStack() as stack:
        for module_name in (
            "app.api.rate_limit",
            "app.api.v1.auth",
            "app.api.admin_security",
        ):
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError:
                continue
            if hasattr(module, "get_redis"):
                stack.enter_context(patch.object(module, "get_redis", return_value=redis))
        yield


async def _reset_api_limits(redis: Redis) -> None:
    await redis.delete(
        "ratelimit:general:127.0.0.1",
        "ratelimit:auth_code:127.0.0.1",
    )


@asynccontextmanager
async def _admin(case: ApiCase, *, telegram_id: int | None = None) -> AsyncIterator[Admin]:
    if telegram_id is None:
        telegram_id = 9_000_000_000_000_000 + secrets.randbelow(100_000_000)
    admin = Admin(
        telegram_id=telegram_id,
        full_name="Session Test Admin",
        role=AdminRole.SUPERADMIN,
    )
    async with case.session_maker() as session:
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
    try:
        yield admin
    finally:
        async with case.session_maker() as session:
            await session.execute(delete(Admin).where(Admin.id == admin.id))
            await session.commit()


async def _issue_code(redis: Redis, telegram_id: int) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    await redis.set(f"admin_login:{code}", str(telegram_id), ex=300)
    return code


async def _exchange(case: ApiCase, redis: Redis, telegram_id: int):
    code = await _issue_code(redis, telegram_id)
    response = await case.client.post(
        "/api/v1/auth/admin/code/exchange",
        headers={"Origin": WEBAPP_ORIGIN},
        json={"code": code},
    )
    return code, response


async def test_admin_cookie_session_lifecycle(test_engine: AsyncEngine, redis: Redis) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        await _reset_api_limits(redis)
        with _use_real_redis(redis):
            async with _admin(case) as admin:
                before_exchange = datetime.now(UTC)
                code, exchange = await _exchange(case, redis, admin.telegram_id)

                assert exchange.status_code == 200
                body = exchange.json()
                assert body == {
                    "admin_id": admin.id,
                    "full_name": "Session Test Admin",
                    "role": "superadmin",
                    "csrf_token": body["csrf_token"],
                }
                assert len(body["csrf_token"]) == 128
                assert exchange.headers["cache-control"] == "private, no-store"
                assert await redis.get(f"admin_login:{code}") is None

                set_cookie = exchange.headers["set-cookie"]
                attributes = {part.strip().lower() for part in set_cookie.split(";")[1:]}
                assert "secure" in attributes
                assert "httponly" in attributes
                assert "path=/" in attributes
                assert "samesite=lax" in attributes
                assert "max-age=604800" in attributes
                assert not any(part.startswith("domain=") for part in attributes)
                assert f"{ADMIN_COOKIE}=" in set_cookie

                raw_cookie = case.client.cookies.get(ADMIN_COOKIE)
                assert raw_cookie is not None
                assert len(raw_cookie) == 43
                async with case.session_maker() as session:
                    stored = await session.scalar(
                        select(AdminSession).where(AdminSession.admin_id == admin.id)
                    )
                    assert stored is not None
                    assert stored.token_hash == sha256(raw_cookie.encode("ascii")).hexdigest()
                    assert len(stored.token_hash) == 64
                    assert raw_cookie not in stored.token_hash
                    assert stored.csrf_token == body["csrf_token"]
                    assert before_exchange + timedelta(hours=11, minutes=59) < (
                        stored.idle_expires_at
                    )
                    assert stored.idle_expires_at < before_exchange + timedelta(
                        hours=12, minutes=1
                    )
                    assert before_exchange + timedelta(days=6, hours=23, minutes=59) < (
                        stored.absolute_expires_at
                    )
                    assert stored.absolute_expires_at < before_exchange + timedelta(
                        days=7, minutes=1
                    )

                session_response = await case.client.get("/api/v1/auth/admin/session")
                assert session_response.status_code == 200
                assert session_response.headers["cache-control"] == "private, no-store"
                assert session_response.json()["csrf_token"] == body["csrf_token"]

                logout = await case.client.post(
                    "/api/v1/auth/admin/logout",
                    headers={"Origin": WEBAPP_ORIGIN, "X-CSRF-Token": body["csrf_token"]},
                )
                assert logout.status_code == 200
                assert logout.headers["cache-control"] == "private, no-store"
                assert case.client.cookies.get(ADMIN_COOKIE) is None
                async with case.session_maker() as session:
                    revoked = await session.scalar(
                        select(AdminSession).where(AdminSession.admin_id == admin.id)
                    )
                    assert revoked is not None and revoked.revoked_at is not None


async def test_parallel_refresh_keeps_cookie_and_csrf_stable(
    test_engine: AsyncEngine, redis: Redis
) -> None:
    import asyncio

    async with make_api_case(test_engine, base_url="https://testserver") as case:
        await _reset_api_limits(redis)
        with _use_real_redis(redis):
            async with _admin(case) as admin:
                _code, exchange = await _exchange(case, redis, admin.telegram_id)
                assert exchange.status_code == 200
                csrf_token = exchange.json()["csrf_token"]
                original_cookie = case.client.cookies.get(ADMIN_COOKIE)
                assert original_cookie is not None

                refreshes = await asyncio.gather(
                    *(
                        case.client.post(
                            "/api/v1/auth/admin/session/refresh",
                            headers={
                                "Origin": WEBAPP_ORIGIN,
                                "X-CSRF-Token": csrf_token,
                            },
                        )
                        for _ in range(2)
                    )
                )

                assert [response.status_code for response in refreshes] == [200, 200]
                assert all(
                    response.headers["cache-control"] == "private, no-store"
                    for response in refreshes
                )
                assert all(
                    response.json()["csrf_token"] == csrf_token for response in refreshes
                )
                assert case.client.cookies.get(ADMIN_COOKIE) == original_cookie


async def test_admin_session_epoch_and_expiry_revoke(
    test_engine: AsyncEngine, redis: Redis
) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        await _reset_api_limits(redis)
        with _use_real_redis(redis):
            async with _admin(case) as admin:
                _code, first_exchange = await _exchange(case, redis, admin.telegram_id)
                assert first_exchange.status_code == 200
                first_cookie = case.client.cookies.get(ADMIN_COOKIE)
                assert first_cookie is not None
                async with case.session_maker() as session:
                    current_admin = await session.get(Admin, admin.id)
                    assert current_admin is not None
                    current_admin.auth_epoch += 1
                    await session.commit()

                epoch_rejected = await case.client.get(
                    "/api/v1/auth/admin/session",
                    headers={"Cookie": f"{ADMIN_COOKIE}={first_cookie}"},
                )
                assert epoch_rejected.status_code == 401
                assert epoch_rejected.json()["error"]["code"] == "ADMIN_SESSION_REQUIRED"
                async with case.session_maker() as session:
                    first_session = await session.scalar(
                        select(AdminSession).where(AdminSession.admin_id == admin.id)
                    )
                    assert first_session is not None and first_session.revoked_at is not None

                _second_code, second_exchange = await _exchange(case, redis, admin.telegram_id)
                assert second_exchange.status_code == 200
                second_cookie = case.client.cookies.get(ADMIN_COOKIE)
                assert second_cookie is not None
                async with case.session_maker() as session:
                    second_session = await session.scalar(
                        select(AdminSession)
                        .where(AdminSession.admin_id == admin.id)
                        .order_by(AdminSession.id.desc())
                    )
                    assert second_session is not None
                    second_session.idle_expires_at = datetime.now(UTC) - timedelta(seconds=1)
                    await session.commit()

                expired = await case.client.get(
                    "/api/v1/auth/admin/session",
                    headers={"Cookie": f"{ADMIN_COOKIE}={second_cookie}"},
                )
                assert expired.status_code == 401
                assert expired.json()["error"]["code"] == "ADMIN_SESSION_REQUIRED"
                async with case.session_maker() as session:
                    second_session = await session.scalar(
                        select(AdminSession)
                        .where(AdminSession.admin_id == admin.id)
                        .order_by(AdminSession.id.desc())
                    )
                    assert second_session is not None and second_session.revoked_at is not None

                _third_code, third_exchange = await _exchange(case, redis, admin.telegram_id)
                assert third_exchange.status_code == 200
                third_csrf = third_exchange.json()["csrf_token"]
                logout_all = await case.client.post(
                    "/api/v1/auth/admin/logout-all",
                    headers={"Origin": WEBAPP_ORIGIN, "X-CSRF-Token": third_csrf},
                )
                assert logout_all.status_code == 200
                assert logout_all.headers["cache-control"] == "private, no-store"
                async with case.session_maker() as session:
                    current_admin = await session.get(Admin, admin.id)
                    assert current_admin is not None and current_admin.auth_epoch == 2
                    sessions = list(
                        (
                            await session.scalars(
                                select(AdminSession).where(AdminSession.admin_id == admin.id)
                            )
                        ).all()
                    )
                    assert all(item.revoked_at is not None for item in sessions)


async def test_exact_origin_csrf_and_multipart_guards(
    test_engine: AsyncEngine, redis: Redis
) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        await _reset_api_limits(redis)
        with _use_real_redis(redis):
            async with _admin(case) as admin:
                bad_origin_code = await _issue_code(redis, admin.telegram_id)
                wrong_origin = await case.client.post(
                    "/api/v1/auth/admin/code/exchange",
                    headers={"Origin": f"{WEBAPP_ORIGIN}/attacker"},
                    json={"code": bad_origin_code},
                )
                assert wrong_origin.status_code == 403
                assert wrong_origin.json()["error"]["code"] == "CSRF_FAILED"
                assert await redis.get(f"admin_login:{bad_origin_code}") is not None

                wrong_media = await case.client.post(
                    "/api/v1/auth/admin/code/exchange",
                    headers={
                        "Origin": WEBAPP_ORIGIN,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    content=f"code={bad_origin_code}",
                )
                assert wrong_media.status_code == 415
                assert await redis.get(f"admin_login:{bad_origin_code}") is not None

                _code, exchange = await _exchange(case, redis, admin.telegram_id)
                assert exchange.status_code == 200
                csrf_token = exchange.json()["csrf_token"]

                for headers in (
                    {"Origin": f"{WEBAPP_ORIGIN}/attacker", "X-CSRF-Token": csrf_token},
                    {"Origin": WEBAPP_ORIGIN},
                    {"Origin": WEBAPP_ORIGIN, "X-CSRF-Token": "wrong-token"},
                ):
                    rejected = await case.client.post(
                        "/api/v1/auth/admin/session/refresh", headers=headers
                    )
                    assert rejected.status_code == 403
                    assert rejected.json()["error"]["code"] == "CSRF_FAILED"

                multipart = await case.client.post(
                    f"/api/v1/admin/products/{case.product_id}/images",
                    headers={"Origin": WEBAPP_ORIGIN},
                    files={"file": ("synthetic.png", b"synthetic image", "image/png")},
                )
                assert multipart.status_code == 403
                assert multipart.json()["error"]["code"] == "CSRF_FAILED"

                non_ascii_csrf = await case.client.post(
                    "/api/v1/auth/admin/session/refresh",
                    headers=[
                        (b"origin", WEBAPP_ORIGIN.encode("ascii")),
                        (b"x-csrf-token", b"\xff"),
                    ],
                )
                assert non_ascii_csrf.status_code == 403
                assert non_ascii_csrf.json()["error"]["code"] == "CSRF_FAILED"


async def test_admin_bearer_fallback_is_rejected(
    test_engine: AsyncEngine, redis: Redis
) -> None:
    async with make_api_case(test_engine) as case:
        await _reset_api_limits(redis)
        with _use_real_redis(redis):
            admin_token = create_access_token(
                user_id=case.user_id, telegram_id=8_100_000_001, is_admin=True
            )
            bearer_admin_response = await case.client.get(
                "/api/v1/admin/categories",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert bearer_admin_response.status_code == 401
            assert bearer_admin_response.json()["error"]["code"] == "ADMIN_SESSION_REQUIRED"

            malformed_cookie_response = await case.client.get(
                "/api/v1/admin/categories",
                headers={"Cookie": f"{ADMIN_COOKIE}=not-a-session-token"},
            )
            assert malformed_cookie_response.status_code == 401
            assert malformed_cookie_response.json()["error"]["code"] == (
                "ADMIN_SESSION_REQUIRED"
            )

            buyer_response = await case.client.get(
                "/api/v1/orders", headers={"Authorization": f"Bearer {case.token}"}
            )
            assert buyer_response.status_code == 200


async def test_legacy_admin_exchange_is_gone(test_engine: AsyncEngine, redis: Redis) -> None:
    async with make_api_case(test_engine) as case:
        await _reset_api_limits(redis)
        telegram_id = await _case_user_telegram_id(case)
        with _use_real_redis(redis):
            async with _admin(case, telegram_id=telegram_id):
                code = await _issue_code(redis, telegram_id)
                response = await case.client.post(
                    "/api/v1/auth/telegram/code", json={"code": code}
                )
                assert response.status_code == 410
                assert await redis.get(f"admin_login:{code}") == str(telegram_id)


async def test_admin_code_exchange_uses_shared_rate_limit(
    test_engine: AsyncEngine, redis: Redis
) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        await _reset_api_limits(redis)
        with _use_real_redis(redis):
            for _ in range(5):
                response = await case.client.post(
                    "/api/v1/auth/customer/code",
                    json={"code": "00000000"},
                )
                assert response.status_code == 401
            sixth_exchange = await case.client.post(
                "/api/v1/auth/admin/code/exchange",
                headers={"Origin": WEBAPP_ORIGIN},
                json={"code": "000000"},
            )

        assert sixth_exchange.status_code == 429


async def _case_user_telegram_id(case: ApiCase) -> int:
    async with case.session_maker() as session:
        user = await session.get(User, case.user_id)
        assert user is not None
        return user.telegram_id

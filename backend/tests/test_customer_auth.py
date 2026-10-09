import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import Request
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api import rate_limit
from app.bot.handlers.admin.auth import cmd_admin_login
from app.bot.handlers.user.start import on_language_selected
from app.bot.handlers.user.web_login import cmd_web_login
from app.bot.keyboards.callback_data import LanguageCallback
from app.core.config import Settings, settings
from app.core.exceptions import RateLimitedError, UnauthorizedError
from app.core.security import decode_token
from app.db.models.admin import Admin
from app.db.models.user import User
from app.services.customer_auth_service import (
    consume_customer_code,
    issue_customer_code,
)

from .api_helpers import ApiCase, make_api_case


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[Redis]:
    connection = Redis.from_url(settings.redis_url, decode_responses=True)
    yield connection
    await connection.aclose()


class FakeMessage:
    def __init__(self, chat_type: str = "private") -> None:
        self.chat = SimpleNamespace(type=chat_type)
        self.answers: list[str] = []
        self.edits: list[str] = []

    async def answer(self, text: str, **_kwargs: object) -> None:
        self.answers.append(text)

    async def edit_text(self, text: str, **_kwargs: object) -> None:
        self.edits.append(text)


class FakeState:
    def __init__(self, data: dict[str, str]) -> None:
        self.data = data

    async def get_data(self) -> dict[str, str]:
        return self.data

    async def clear(self) -> None:
        self.data = {}


class FakeCallback:
    def __init__(self, message: FakeMessage) -> None:
        self.message = message
        self.answered = False

    async def answer(self) -> None:
        self.answered = True


def _translator(key: str, **kwargs: object) -> str:
    return key.format(**kwargs)


def _request(peer: str, forwarded_for: str | None = None) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/customer/code",
            "headers": headers,
            "client": (peer, 43123),
            "server": ("testserver", 80),
        }
    )


def test_trusted_proxy_configuration_rejects_wildcard_networks() -> None:
    values = settings.model_dump(by_alias=True)
    values["TRUSTED_PROXY_CIDRS"] = "0.0.0.0/0,::/0"

    with pytest.raises(ValidationError):
        Settings.model_validate(values)


async def _user_telegram_id(case: ApiCase, user_id: int) -> int:
    async with case.session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        return user.telegram_id


@contextmanager
def _use_real_redis(redis: Redis) -> Iterator[None]:
    with (
        patch("app.api.rate_limit.get_redis", return_value=redis),
        patch("app.api.v1.auth.get_redis", return_value=redis),
    ):
        yield


async def _reset_api_rate_limits(redis: Redis) -> None:
    await redis.delete(
        "ratelimit:general:127.0.0.1",
        "ratelimit:auth_code:127.0.0.1",
    )


async def test_customer_code_contract(test_engine: AsyncEngine, redis: Redis) -> None:
    async with make_api_case(test_engine) as case:
        await _reset_api_rate_limits(redis)
        telegram_id = await _user_telegram_id(case, case.user_id)
        code = await issue_customer_code(redis, telegram_id)

        assert len(code) == 8 and code.isdecimal()
        assert 0 < await redis.ttl(f"customer_login:code:{code}") <= 300
        assert await redis.get(f"customer_login:code:{code}") == str(telegram_id)

        other_telegram_id = await _user_telegram_id(case, case.other_user_id)
        with _use_real_redis(redis):
            invalid = await case.client.post(
                "/api/v1/auth/customer/code", json={"code": "not-a-code"}
            )
            assert invalid.status_code == 401
            assert invalid.json()["error"]["code"] == "INVALID_OR_EXPIRED_CODE"
            expired_code = "87654321"
            await redis.set(f"customer_login:code:{expired_code}", str(telegram_id), ex=300)
            await redis.expire(f"customer_login:code:{expired_code}", 0)
            expired = await case.client.post(
                "/api/v1/auth/customer/code", json={"code": expired_code}
            )
            assert expired.status_code == 401
            assert expired.json()["error"]["code"] == "INVALID_OR_EXPIRED_CODE"
            orphan_code = await issue_customer_code(redis, 8_100_000_003)
            orphan = await case.client.post(
                "/api/v1/auth/customer/code", json={"code": orphan_code}
            )
            assert orphan.status_code == 401
            assert orphan.json()["error"]["code"] == "INVALID_OR_EXPIRED_CODE"
            response = await case.client.post(
                "/api/v1/auth/customer/code",
                json={"code": code, "telegram_id": other_telegram_id, "is_admin": True},
            )
            used = await case.client.post("/api/v1/auth/customer/code", json={"code": code})

        assert response.status_code == 200
        body = response.json()
        claims = decode_token(body["access_token"], expected_type="access")
        assert claims["telegram_id"] == telegram_id
        assert claims["sub"] == str(case.user_id)
        assert claims["is_admin"] is False
        assert body["is_admin"] is False
        assert body["refresh_token"]

        assert used.status_code == 401
        assert used.json()["error"]["code"] == "INVALID_OR_EXPIRED_CODE"


async def test_private_chat_required(redis: Redis) -> None:
    user = User(telegram_id=917_456_291, first_name="Test", is_blocked=False)
    group_message = FakeMessage("group")
    await cmd_web_login(group_message, user, redis, _translator)  # type: ignore[arg-type]

    assert group_message.answers
    assert await redis.get(f"customer_login:user:{user.telegram_id}") is None

    private_message = FakeMessage("private")
    await cmd_web_login(private_message, user, redis, _translator)  # type: ignore[arg-type]
    assert private_message.answers
    customer_code = await redis.get(f"customer_login:user:{user.telegram_id}")
    assert customer_code is not None and len(customer_code) == 8

    inactive_admin = Admin(
        telegram_id=917_456_292,
        full_name="Inactive admin",
        is_active=False,
    )
    group_admin_message = FakeMessage("supergroup")
    await cmd_admin_login(
        group_admin_message,
        inactive_admin,
        redis,
        _translator,
    )  # type: ignore[arg-type]

    assert group_admin_message.answers
    assert await redis.keys("admin_login:*") == []

    inactive_private_message = FakeMessage("private")
    await cmd_admin_login(
        inactive_private_message,
        inactive_admin,
        redis,
        _translator,
    )  # type: ignore[arg-type]
    assert inactive_private_message.answers
    assert await redis.keys("admin_login:*") == []


async def test_web_login_deeplink_after_language_selection(
    db_session: AsyncSession, user: User, redis: Redis
) -> None:
    message = FakeMessage()
    callback = FakeCallback(message)
    await on_language_selected(
        callback,
        LanguageCallback(code="ru"),
        db_session,
        user,
        FakeState({"deeplink": "web_login"}),
        None,
        redis,
    )  # type: ignore[arg-type]

    code = await redis.get(f"customer_login:user:{user.telegram_id}")
    assert code is not None and len(code) == 8 and code.isdecimal()
    assert await redis.get(f"customer_login:code:{code}") == str(user.telegram_id)
    assert user.language == "ru"
    assert callback.answered
    assert any(code in answer for answer in message.answers)


async def test_customer_code_one_winner(redis: Redis) -> None:
    telegram_id = 8_100_000_001
    code = await issue_customer_code(redis, telegram_id)

    results = await asyncio.gather(
        *(consume_customer_code(redis, code) for _ in range(12)),
        return_exceptions=True,
    )

    assert [result for result in results if isinstance(result, int)] == [telegram_id]
    assert sum(isinstance(result, UnauthorizedError) for result in results) == 11


async def test_customer_code_collision_and_reissue(
    redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.services.customer_auth_service as customer_auth_service

    clock = [1_000]
    draws = iter([1_111_111, 2_222_222, 3_333_333, 4_444_444])
    monkeypatch.setattr(customer_auth_service.time, "time", lambda: clock[0])
    monkeypatch.setattr(customer_auth_service.secrets, "randbelow", lambda _limit: next(draws))

    telegram_id = 8_100_000_002
    first_code = await issue_customer_code(redis, telegram_id)
    assert first_code == "01111111"
    with pytest.raises(RateLimitedError):
        await issue_customer_code(redis, telegram_id)

    await redis.set("customer_login:code:03333333", "8", ex=300)
    clock[0] += 60
    replacement = await issue_customer_code(redis, telegram_id)

    assert replacement == "04444444"
    assert await consume_customer_code(redis, replacement) == telegram_id
    with pytest.raises(UnauthorizedError):
        await consume_customer_code(redis, first_code)


async def test_customer_and_admin_codes_cannot_cross(
    test_engine: AsyncEngine, redis: Redis
) -> None:
    async with make_api_case(test_engine) as case:
        await _reset_api_rate_limits(redis)
        telegram_id = await _user_telegram_id(case, case.user_id)
        customer_code = await issue_customer_code(redis, telegram_id)
        admin_code = "012345"
        await redis.set(f"admin_login:{admin_code}", str(telegram_id), ex=300)

        with _use_real_redis(redis):
            admin_code_as_customer = await case.client.post(
                "/api/v1/auth/customer/code", json={"code": admin_code}
            )
            customer_code_as_admin = await case.client.post(
                "/api/v1/auth/telegram/code", json={"code": customer_code}
            )
            admin_races = await asyncio.gather(
                *(
                    case.client.post("/api/v1/auth/telegram/code", json={"code": admin_code})
                    for _ in range(2)
                )
            )

        assert admin_code_as_customer.status_code == 401
        assert customer_code_as_admin.status_code == 401
        assert sorted(response.status_code for response in admin_races) == [200, 401]
        assert await redis.get(f"admin_login:{admin_code}") is None
        assert await redis.get(f"customer_login:code:{customer_code}") == str(telegram_id)


async def test_code_rate_limits(
    test_engine: AsyncEngine, redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with make_api_case(test_engine) as case:
        await _reset_api_rate_limits(redis)
        with _use_real_redis(redis):
            responses = []
            for _ in range(5):
                responses.append(
                    await case.client.post(
                        "/api/v1/auth/customer/code",
                        headers={"X-Forwarded-For": "198.51.100.91"},
                        json={"code": "00000000"},
                    )
                )
            sixth_exchange = await case.client.post(
                "/api/v1/auth/telegram/code",
                headers={"X-Forwarded-For": "198.51.100.91"},
                json={"code": "999999"},
            )

        assert all(response.status_code == 401 for response in responses)
        assert sixth_exchange.status_code == 429
        assert await redis.get("ratelimit:auth_code:127.0.0.1") == "6"
        assert await redis.get("ratelimit:auth_code:198.51.100.91") is None

    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "")
    assert rate_limit.trusted_client_ip(_request("203.0.113.10", "198.51.100.8")) == (
        "203.0.113.10"
    )
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "10.0.0.0/8")
    assert (
        rate_limit.trusted_client_ip(_request("10.0.0.2", "198.51.100.8, 10.0.0.1"))
        == "198.51.100.8"
    )


async def test_blocked_customer_cannot_exchange_code(
    test_engine: AsyncEngine, redis: Redis
) -> None:
    async with make_api_case(test_engine) as case:
        await _reset_api_rate_limits(redis)
        telegram_id = await _user_telegram_id(case, case.user_id)
        code = await issue_customer_code(redis, telegram_id)
        async with case.session_maker() as session:
            user = await session.scalar(select(User).where(User.id == case.user_id))
            assert user is not None
            user.is_blocked = True
            await session.commit()

        with _use_real_redis(redis):
            response = await case.client.post(
                "/api/v1/auth/customer/code", json={"code": code}
            )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

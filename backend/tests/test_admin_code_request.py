"""The web login page asks the bot to send a five-minute admin code to Telegram."""

import secrets
from collections.abc import AsyncIterator

import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings
from app.db.models.user import User

from .api_helpers import make_api_case
from .test_admin_sessions import WEBAPP_ORIGIN, _admin, _use_real_redis

REQUEST_PATH = "/api/v1/auth/admin/code/request"


class RecordingBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_kwargs: object) -> None:
        self.sent.append((chat_id, text))


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[Redis]:
    connection = Redis.from_url(settings.redis_url, decode_responses=True)
    existing = set(await connection.keys("admin_login:*"))
    await connection.delete(
        "ratelimit:general:127.0.0.1",
        "ratelimit:auth_code:127.0.0.1",
        "ratelimit:admin_code_request:127.0.0.1",
    )
    yield connection
    created = set(await connection.keys("admin_login:*")) - existing
    if created:
        await connection.delete(*created)
    await connection.delete("ratelimit:admin_code_request:127.0.0.1")
    await connection.aclose()


async def _request(case, identifier: str, *, origin: str | None = WEBAPP_ORIGIN):
    headers = {"Origin": origin} if origin else {}
    return await case.client.post(
        REQUEST_PATH, headers=headers, json={"identifier": identifier}
    )


async def test_request_sends_a_five_minute_code_and_resend_replaces_it(
    test_engine: AsyncEngine, redis: Redis
) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        bot = RecordingBot()
        case.app.state.bot = bot
        with _use_real_redis(redis):
            async with _admin(case) as admin:
                response = await _request(case, str(admin.telegram_id))

                assert response.status_code == 200
                assert response.json() == {"expires_in": 300, "resend_after": 60}
                assert response.headers["cache-control"] == "private, no-store"
                code = await redis.get(f"admin_login:latest:{admin.telegram_id}")
                assert code is not None
                assert bot.sent == [(admin.telegram_id, bot.sent[0][1])]
                assert code in bot.sent[0][1]
                assert await redis.get(f"admin_login:{code}") == str(admin.telegram_id)
                assert 0 < await redis.ttl(f"admin_login:{code}") <= 300

                # Inside the cooldown nothing is sent, so the page cannot be used to spam an admin.
                again = await _request(case, str(admin.telegram_id))
                assert again.json() == {"expires_in": 300, "resend_after": 60}
                assert len(bot.sent) == 1

                # A resend after the cooldown revokes the previous code.
                await redis.delete(f"admin_login:cooldown:{admin.telegram_id}")
                await _request(case, str(admin.telegram_id))
                new_code = await redis.get(f"admin_login:latest:{admin.telegram_id}")
                assert len(bot.sent) == 2
                assert new_code is not None and new_code != code
                assert await redis.get(f"admin_login:{code}") is None

                exchange = await case.client.post(
                    "/api/v1/auth/admin/code/exchange",
                    headers={"Origin": WEBAPP_ORIGIN},
                    json={"code": new_code},
                )
                assert exchange.status_code == 200
                assert exchange.json()["admin_id"] == admin.id


async def test_username_identifies_the_admin(test_engine: AsyncEngine, redis: Redis) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        bot = RecordingBot()
        case.app.state.bot = bot
        username = f"Kans_Admin_{secrets.token_hex(4)}"
        with _use_real_redis(redis):
            async with _admin(case) as admin:
                async with case.session_maker() as session:
                    session.add(
                        User(
                            telegram_id=admin.telegram_id,
                            first_name="Admin user",
                            username=username,
                            language="ru",
                        )
                    )
                    await session.commit()
                try:
                    response = await _request(case, f"@{username.lower()}")
                    assert response.status_code == 200
                    assert [chat_id for chat_id, _text in bot.sent] == [admin.telegram_id]
                    # The code message follows the admin's own bot language.
                    assert "Действителен" in bot.sent[0][1]
                finally:
                    async with case.session_maker() as session:
                        await session.execute(
                            delete(User).where(User.telegram_id == admin.telegram_id)
                        )
                        await session.commit()


async def test_unknown_identifier_gets_the_same_answer_and_no_message(
    test_engine: AsyncEngine, redis: Redis
) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        bot = RecordingBot()
        case.app.state.bot = bot
        with _use_real_redis(redis):
            response = await _request(case, "@nobody_is_admin_here_123")
            numeric = await _request(case, "123456789012")

        assert response.status_code == numeric.status_code == 200
        assert response.json() == numeric.json() == {"expires_in": 300, "resend_after": 60}
        assert bot.sent == []


async def test_code_requests_are_rate_limited_per_ip(
    test_engine: AsyncEngine, redis: Redis
) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        case.app.state.bot = RecordingBot()
        with _use_real_redis(redis):
            statuses = [
                (await _request(case, f"@nobody_{attempt}")).status_code
                for attempt in range(6)
            ]

        assert statuses == [200, 200, 200, 200, 200, 429]


async def test_request_requires_the_admin_origin(
    test_engine: AsyncEngine, redis: Redis
) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        bot = RecordingBot()
        case.app.state.bot = bot
        with _use_real_redis(redis):
            async with _admin(case) as admin:
                response = await _request(
                    case, str(admin.telegram_id), origin="https://evil.example"
                )

        assert response.status_code == 403
        assert bot.sent == []

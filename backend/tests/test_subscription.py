"""The channel gate stands between every customer and the shop, so its failure modes matter
more than its happy path: a misconfigured channel must NOT lock the shop, while a genuine
"not a member" answer must.
"""

from types import SimpleNamespace

import pytest
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.bot.utils import subscription
from app.core.config import settings


class FakeBot:
    """Stands in for aiogram's Bot: records calls and replays a scripted result."""

    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0

    async def get_chat_member(self, *, chat_id: int, user_id: int) -> object:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


def _bad_request(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=SimpleNamespace(), message=message)


@pytest.fixture(autouse=True)
def _enable_gate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "required_channel_id", -1003642407474)
    yield


@pytest.mark.parametrize(
    "status",
    [
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    ],
)
async def test_member_statuses_pass_the_gate(status: ChatMemberStatus) -> None:
    bot = FakeBot(SimpleNamespace(status=status))
    assert await subscription.is_subscribed(bot, 42) is True


@pytest.mark.parametrize("status", [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED])
async def test_non_member_statuses_are_blocked(status: ChatMemberStatus) -> None:
    bot = FakeBot(SimpleNamespace(status=status))
    assert await subscription.is_subscribed(bot, 42) is False


async def test_restricted_member_is_judged_by_is_member_flag() -> None:
    still_in = FakeBot(SimpleNamespace(status=ChatMemberStatus.RESTRICTED, is_member=True))
    assert await subscription.is_subscribed(still_in, 42) is True

    thrown_out = FakeBot(SimpleNamespace(status=ChatMemberStatus.RESTRICTED, is_member=False))
    assert await subscription.is_subscribed(thrown_out, 42) is False


async def test_gate_is_open_when_no_channel_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "required_channel_id", None)
    bot = FakeBot(SimpleNamespace(status=ChatMemberStatus.LEFT))
    assert await subscription.is_subscribed(bot, 42) is True
    assert bot.calls == 0, "a disabled gate must not call Telegram at all"


async def test_unknown_user_is_treated_as_not_subscribed() -> None:
    """Telegram's answer for a user the channel has never seen — a real verdict, not a
    configuration problem, so the gate stays closed."""
    bot = FakeBot(_bad_request("Bad Request: user not found"))
    assert await subscription.is_subscribed(bot, 42) is False


@pytest.mark.parametrize(
    "error",
    [
        _bad_request("Bad Request: chat not found"),
        _bad_request("Bad Request: member list is inaccessible"),
        TelegramForbiddenError(method=SimpleNamespace(), message="Forbidden: bot was kicked"),
    ],
)
async def test_misconfiguration_fails_open(error: Exception) -> None:
    """The bot not being an admin of the channel must never lock customers out of the shop."""
    bot = FakeBot(error)
    assert await subscription.is_subscribed(bot, 42) is True


async def test_positive_verdict_is_cached_and_negative_is_not() -> None:
    redis = FakeRedis()
    subscribed = FakeBot(SimpleNamespace(status=ChatMemberStatus.MEMBER))

    assert await subscription.is_subscribed(subscribed, 42, redis) is True
    assert await subscription.is_subscribed(subscribed, 42, redis) is True
    assert subscribed.calls == 1, "second check should be served from cache"

    left = FakeBot(SimpleNamespace(status=ChatMemberStatus.LEFT))
    assert await subscription.is_subscribed(left, 99, redis) is False
    assert await subscription.is_subscribed(left, 99, redis) is False
    assert left.calls == 2, "a negative verdict must never be cached"


async def test_forget_subscription_forces_a_recheck() -> None:
    """What the "I subscribed" button relies on: the cached yes is dropped so a user who has
    since left is caught, and a user who has just joined is not stuck behind a stale no."""
    redis = FakeRedis()
    bot = FakeBot(SimpleNamespace(status=ChatMemberStatus.MEMBER))

    await subscription.is_subscribed(bot, 42, redis)
    await subscription.forget_subscription(redis, 42)
    await subscription.is_subscribed(bot, 42, redis)

    assert bot.calls == 2

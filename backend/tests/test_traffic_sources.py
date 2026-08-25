import pytest

from app.bot.handlers.admin.sources import source_link
from app.db.models.traffic_source import TrafficSource
from app.db.repositories.traffic_source_repository import CODE_PATTERN, normalize_code


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Instagram", "instagram"),
        ("Telegram kanal", "telegram-kanal"),
        ("  Bozor / Chorsu  ", "bozor-chorsu"),
        ("Reklama #1", "reklama-1"),
        ("Инстаграм", ""),
    ],
)
def test_normalize_code_produces_link_safe_slugs(raw: str, expected: str) -> None:
    assert normalize_code(raw) == expected


def test_normalize_code_is_capped_at_the_column_length() -> None:
    assert len(normalize_code("x" * 100)) == 32


@pytest.mark.parametrize("code", ["ig", "instagram", "kanal_1", "bozor-chorsu", "a" * 32])
def test_valid_codes_are_accepted(code: str) -> None:
    assert CODE_PATTERN.match(code)


@pytest.mark.parametrize(
    "code",
    [
        "",
        "a",  # too short to be meaningful
        "a" * 33,  # longer than the column
        "Instagram",  # uppercase would make the link case-sensitive to type
        "bozor chorsu",  # a space breaks the /start payload
        "reklama!",
        "инстаграм",
    ],
)
def test_invalid_codes_are_rejected(code: str) -> None:
    assert not CODE_PATTERN.match(code)


async def test_source_link_uses_the_real_bot_username_not_the_setting() -> None:
    """Production had BOT_USERNAME=kansshop_bot while the bot is really @kansshopbot — every
    campaign link would have pointed at the wrong bot. getMe is the source of truth."""
    from types import SimpleNamespace

    from app.bot.handlers.user import start as start_handler
    from app.bot.utils import identity

    identity._cached_username = None

    class FakeBot:
        async def get_me(self):
            return SimpleNamespace(username="kansshopbot")

    source = TrafficSource(code="instagram", name="Instagram")
    link = await source_link(FakeBot(), source)
    identity._cached_username = None

    assert link == "https://t.me/kansshopbot?start=src_instagram"

    payload = link.split("start=", 1)[1]
    assert any(payload.startswith(prefix) for prefix in start_handler._SOURCE_PREFIXES)
    assert payload.removeprefix("src_") == source.code


async def test_source_link_falls_back_to_the_setting_when_get_me_fails(
    monkeypatch,
) -> None:
    from aiogram.exceptions import TelegramAPIError

    from app.bot.utils import identity
    from app.core.config import settings

    identity._cached_username = None
    monkeypatch.setattr(settings, "bot_username", "configured_bot")

    class BrokenBot:
        async def get_me(self):
            raise TelegramAPIError(method=object(), message="boom")

    link = await source_link(BrokenBot(), TrafficSource(code="qr", name="QR"))
    identity._cached_username = None

    assert link == "https://t.me/configured_bot?start=src_qr"

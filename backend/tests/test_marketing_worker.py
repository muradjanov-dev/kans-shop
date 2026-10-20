"""Scheduling and publishing of the daily channel advert (real Postgres, fake Telegram)."""

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.models.category import Category
from app.db.models.enums import ProductUnit
from app.db.models.marketing_post import MarketingPost
from app.db.models.product import Product
from app.db.models.product_image import ProductImage
from app.services.marketing import worker
from app.services.marketing.video import RenderedVideo

TASHKENT = ZoneInfo("Asia/Tashkent")
CHANNEL = -1009000000001
ERRORS = -1009000000002


class FakeBot:
    def __init__(self, *, fail_upload: bool = False) -> None:
        self.videos: list[dict[str, Any]] = []
        self.messages: list[tuple[int, str]] = []
        self.fail_upload = fail_upload

    async def get_chat(self, chat_id: int) -> SimpleNamespace:
        assert chat_id == CHANNEL
        return SimpleNamespace(username="kansshop_test")

    async def send_video(self, **kwargs: Any) -> SimpleNamespace:
        if self.fail_upload:
            raise RuntimeError("Telegram is down")
        self.videos.append(kwargs)
        return SimpleNamespace(message_id=700 + len(self.videos))

    async def send_message(self, chat_id: int, text: str, **_kwargs: Any) -> None:
        self.messages.append((chat_id, text))


def at(local: str) -> datetime:
    return datetime.fromisoformat(local).replace(tzinfo=TASHKENT).astimezone(UTC)


@pytest_asyncio.fixture
async def session_maker(
    test_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Every session the worker opens shares one connection whose outer transaction is rolled
    back afterwards, so the worker's own commits never leak into other tests."""
    async with test_engine.connect() as conn:
        outer = await conn.begin()
        maker = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with maker() as session:
            category = Category(name_uz="Ofis", name_ru="Офис", slug="advert-test")
            session.add(category)
            await session.flush()
            for index in range(3):
                product = Product(
                    category_id=category.id,
                    # The first one carries a Russian 1C name, as most of the catalog does.
                    name_uz=(
                        "Ручка шариковая Spark Luxor чер."
                        if index == 0
                        else f"Advert daftar {index}"
                    ),
                    name_ru=f"Тетрадь {index}",
                    sku=f"ADV-TEST-{index}",
                    price=Decimal("9500"),
                    stock_qty=50,
                    unit=ProductUnit.DONA,
                )
                session.add(product)
                await session.flush()
                session.add(
                    ProductImage(
                        product_id=product.id,
                        url=f"https://cdn.example.test/advert/{index}.jpg",
                        is_main=True,
                        sort_order=0,
                    )
                )
            await session.commit()
        yield maker
        await outer.rollback()


@pytest.fixture(autouse=True)
def rendered(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """No network, no ffmpeg: photos and the video are stubbed; returns product counts."""
    monkeypatch.setattr(settings, "marketing_enabled", True)
    monkeypatch.setattr(settings, "marketing_channel_id", CHANNEL)
    monkeypatch.setattr(settings, "marketing_post_time", "11:00")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "bot_username", "kans_test_bot")
    monkeypatch.setattr(settings, "error_channel_id", ERRORS)
    calls: list[int] = []

    async def fake_image(_url: str, _client: object) -> Image.Image:
        return Image.new("RGB", (40, 40), (200, 120, 60))

    def fake_render(products: list[object], _brand: object) -> RenderedVideo:
        calls.append(len(products))
        return RenderedVideo(b"\x00\x00\x00\x18ftypmp42", 720, 900, 18.6)

    monkeypatch.setattr(worker, "load_image", fake_image)
    monkeypatch.setattr(worker, "render_advert", fake_render)
    return calls


async def _posts(maker: async_sessionmaker[AsyncSession]) -> list[MarketingPost]:
    async with maker() as session:
        rows = await session.scalars(select(MarketingPost).order_by(MarketingPost.post_date))
        return list(rows)


async def _set_updated_at(maker: async_sessionmaker[AsyncSession], value: datetime) -> None:
    async with maker() as session, session.begin():
        await session.execute(update(MarketingPost).values(updated_at=value))


async def test_first_advert_goes_out_immediately_then_one_a_day_at_post_time(
    session_maker: async_sessionmaker[AsyncSession], rendered: list[int]
) -> None:
    bot: Any = FakeBot()

    first = await worker.publish_due_advert(bot, session_maker, now=at("2031-03-10T07:30"))

    assert first is not None and first.status == "sent"
    assert first.message_id == 701 and first.channel_id == CHANNEL
    assert first.attempts == 1 and first.posted_at is not None
    assert len(first.product_ids) == 3 and rendered == [3]
    video = bot.videos[0]
    assert video["chat_id"] == CHANNEL and video["parse_mode"] == "HTML"
    assert video["duration"] == 19 and video["supports_streaming"] is True
    caption = video["caption"]
    assert caption == first.caption and len(caption) <= 1024
    assert "🤖 Buyurtma: @kans_test_bot" in caption
    assert caption.rstrip().endswith("📣 @kansshop_test")
    # The Russian catalog name is advertised in Uzbek: one language from start to end.
    assert "Luxor Spark sharikli ruchka, qora" in caption
    assert not re.search("[А-Яа-яЁё]", caption)

    # The same day never gets a second advert.
    assert (
        await worker.publish_due_advert(bot, session_maker, now=at("2031-03-10T12:00")) is None
    )
    # The next day waits for the post time.
    assert (
        await worker.publish_due_advert(bot, session_maker, now=at("2031-03-11T09:00")) is None
    )
    second = await worker.publish_due_advert(bot, session_maker, now=at("2031-03-11T11:05"))

    assert second is not None and second.status == "sent" and second.message_id == 702
    assert [post.status for post in await _posts(session_maker)] == ["sent", "sent"]
    assert len(bot.videos) == 2


async def test_a_failed_day_is_reported_and_retried_after_a_pause(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    now = at("2031-04-02T08:00")
    failing: Any = FakeBot(fail_upload=True)

    assert await worker.publish_due_advert(failing, session_maker, now=now) is None

    [post] = await _posts(session_maker)
    assert post.status == "failed" and post.attempts == 1
    assert post.error is not None and "Telegram is down" in post.error
    assert [chat for chat, _text in failing.messages] == [ERRORS]

    healthy: Any = FakeBot()
    await _set_updated_at(session_maker, now - timedelta(minutes=5))
    assert await worker.publish_due_advert(healthy, session_maker, now=now) is None
    assert healthy.videos == []

    await _set_updated_at(session_maker, now - timedelta(minutes=25))
    retried = await worker.publish_due_advert(healthy, session_maker, now=now)

    assert retried is not None and retried.status == "sent"
    assert retried.attempts == 2 and retried.error is None
    assert len(healthy.videos) == 1


async def test_a_day_is_given_up_after_three_attempts(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    now = at("2031-04-03T12:00")
    failing: Any = FakeBot(fail_upload=True)
    for _attempt in range(worker.MAX_ATTEMPTS_PER_DAY):
        assert await worker.publish_due_advert(failing, session_maker, now=now) is None
        await _set_updated_at(session_maker, now - timedelta(hours=1))

    healthy: Any = FakeBot()
    assert await worker.publish_due_advert(healthy, session_maker, now=now) is None
    [post] = await _posts(session_maker)
    assert post.status == "failed" and post.attempts == worker.MAX_ATTEMPTS_PER_DAY
    assert healthy.videos == []


async def test_a_disabled_or_unconfigured_worker_does_nothing(
    session_maker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    bot: Any = FakeBot()
    monkeypatch.setattr(settings, "marketing_enabled", False)
    assert (
        await worker.publish_due_advert(bot, session_maker, now=at("2031-05-01T12:00")) is None
    )

    monkeypatch.setattr(settings, "marketing_enabled", True)
    monkeypatch.setattr(settings, "marketing_channel_id", None)
    monkeypatch.setattr(settings, "required_channel_id", None)
    assert (
        await worker.publish_due_advert(bot, session_maker, now=at("2031-05-01T12:00")) is None
    )

    assert await _posts(session_maker) == []
    assert bot.videos == []

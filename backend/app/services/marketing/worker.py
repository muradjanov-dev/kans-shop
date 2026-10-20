"""Publishes one rendered video advert per day to the shop's Telegram channel.

The very first advert goes out as soon as the worker starts; afterwards one per Tashkent
day at MARKETING_POST_TIME. A day is claimed by inserting its `marketing_posts` row, so a
restart or a second API process cannot publish twice. Rendering, the caption and the
upload run outside any database transaction; a failed day is retried a few times and the
error channel hears about every failure.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import random
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.category import Category
from app.db.models.marketing_post import MarketingPost
from app.db.models.product import Product
from app.db.repositories import setting_repository
from app.db.repositories.product_repository import public_visibility_predicate
from app.services.inventory_policy import get_inventory_policy
from app.services.marketing.captions import CaptionContext, CaptionProduct, build_caption
from app.services.marketing.video import AdBrand, AdProduct, render_advert

log = get_logger(__name__)

STARTUP_DELAY_SECONDS = 45
CHECK_INTERVAL_SECONDS = 300
MAX_ATTEMPTS_PER_DAY = 3
RETRY_AFTER = timedelta(minutes=20)
STALE_RENDER_AFTER = timedelta(minutes=30)
RECENT_PRODUCT_DAYS = 14
PRODUCTS_PER_ADVERT = 3
MAX_IMAGE_BYTES = 12 * 1024 * 1024

_WEEKDAYS = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]
_MONTHS = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]  # fmt: skip
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U00002b00-\U00002bff\U0000fe0f\U0000200d]"
)


@dataclass(frozen=True)
class _PickedProduct:
    id: int
    name: str
    price: Decimal
    old_price: Decimal | None
    image_url: str
    category: str


def money(amount: Decimal) -> str:
    whole = int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{whole:,}".replace(",", " ")


def pretty_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("998"):
        return f"+998 {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:12]}"
    return raw.strip() or None


def video_hook(text: str, limit: int = 70) -> str:
    """First sentence without emoji (the video font has no emoji glyphs)."""
    clean = " ".join(_EMOJI.sub("", text).split())
    first = re.split(r"(?<=[.!?])\s", clean, maxsplit=1)[0]
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def uzbek_date(day: date) -> str:
    return f"{day.day}-{_MONTHS[day.month - 1]}, {_WEEKDAYS[day.weekday()]}"


def _post_time() -> time:
    try:
        hours, minutes = (int(part) for part in settings.marketing_post_time.split(":", 1))
        return time(hours, minutes)
    except ValueError:
        return time(11, 0)


def channel_id() -> int | None:
    return settings.marketing_channel_id or settings.required_channel_id


# --------------------------------------------------------------------------- claiming


async def claim_day(
    session: AsyncSession, *, today: date, local_now: datetime, now: datetime
) -> MarketingPost | None:
    """Claim today's advert if it is due. The first advert ever is due immediately."""
    ever_sent = await session.scalar(
        select(MarketingPost.id).where(MarketingPost.status == "sent").limit(1)
    )
    due = ever_sent is None or local_now.timetz().replace(tzinfo=None) >= _post_time()
    existing = await session.scalar(
        select(MarketingPost)
        .where(MarketingPost.post_date == today)
        .with_for_update(skip_locked=True)
    )
    if existing is None:
        if not due:
            return None
        inserted = await session.scalar(
            insert(MarketingPost)
            .values(post_date=today, status="rendering", attempts=1)
            .on_conflict_do_nothing(index_elements=["post_date"])
            .returning(MarketingPost.id)
        )
        if inserted is None:
            return None
        return await session.get(MarketingPost, inserted)

    if existing.status == "sent" or existing.attempts >= MAX_ATTEMPTS_PER_DAY:
        return None
    age = now - existing.updated_at
    if existing.status == "rendering" and age < STALE_RENDER_AFTER:
        return None
    if existing.status == "failed" and age < RETRY_AFTER:
        return None
    existing.status = "rendering"
    existing.attempts += 1
    existing.error = None
    return existing


async def _recent_product_ids(session: AsyncSession, today: date) -> set[int]:
    rows = await session.scalars(
        select(MarketingPost.product_ids).where(
            MarketingPost.post_date >= today - timedelta(days=RECENT_PRODUCT_DAYS),
            MarketingPost.status == "sent",
        )
    )
    return {int(product_id) for ids in rows for product_id in (ids or [])}


async def _recent_template_keys(session: AsyncSession) -> list[str]:
    rows = await session.scalars(
        select(MarketingPost.template_key)
        .where(MarketingPost.template_key.is_not(None))
        .order_by(MarketingPost.post_date.desc())
        .limit(7)
    )
    return [key for key in rows if key]


def _main_image_url(product: Product) -> str | None:
    images = sorted(product.images, key=lambda image: (not image.is_main, image.sort_order))
    return next(
        (image.url.strip() for image in images if image.url and image.url.strip()), None
    )


async def pick_products(
    session: AsyncSession, *, exclude: set[int], count: int = PRODUCTS_PER_ADVERT
) -> list[_PickedProduct]:
    """A hero product plus companions, preferring its category, skipping recent adverts."""
    policy = await get_inventory_policy(session)
    products = list(
        await session.scalars(
            select(Product)
            .options(selectinload(Product.images))
            .where(public_visibility_predicate(), Product.price > 0)
        )
    )
    candidates = [
        product
        for product in products
        if _main_image_url(product)
        and (
            not policy.stock_tracking_enabled
            or (product.stock_qty or 0) >= max(1, policy.minimum_quantity(product))
        )
    ]
    fresh = [product for product in candidates if product.id not in exclude] or candidates
    if not fresh:
        return []
    rng = random.Random()
    hero = rng.choice([product for product in fresh if product.is_featured] or fresh)
    same_category = [p for p in fresh if p.category_id == hero.category_id and p.id != hero.id]
    others = [p for p in fresh if p.category_id != hero.category_id]
    rng.shuffle(same_category)
    rng.shuffle(others)
    chosen = [hero, *(same_category[:1] + others + same_category[1:])[: count - 1]]

    category_names = {
        row.id: f"{row.name_uz} / {row.name_ru}"
        for row in await session.execute(
            select(Category.id, Category.name_uz, Category.name_ru).where(
                Category.id.in_({product.category_id for product in chosen})
            )
        )
    }
    return [
        _PickedProduct(
            id=product.id,
            name=product.name_uz,
            price=product.price,
            old_price=(
                product.old_price
                if product.old_price is not None and product.old_price > product.price
                else None
            ),
            image_url=_main_image_url(product) or "",
            category=category_names.get(product.category_id, ""),
        )
        for product in chosen
    ]


# --------------------------------------------------------------------------- images


def _local_media_path(url: str) -> Path | None:
    base = settings.media_base_url.rstrip("/") + "/"
    if not url.startswith(base):
        return None
    root = Path(settings.media_root).resolve()
    candidate = (root / url[len(base) :]).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    return candidate


async def load_image(url: str, client: httpx.AsyncClient) -> Image.Image:
    """The product photo, read from local media when it lives on this server."""
    local = _local_media_path(url)
    if local is not None:
        raw = await asyncio.to_thread(local.read_bytes)
    else:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        raw = response.content
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(f"Product image too large: {url}")
    image = Image.open(io.BytesIO(raw))
    image.load()
    image.thumbnail((1000, 1000))
    return image


# --------------------------------------------------------------------------- publishing


async def publish_due_advert(
    bot: Bot, session_maker: async_sessionmaker[AsyncSession], *, now: datetime
) -> MarketingPost | None:
    if not settings.marketing_enabled:
        return None
    target = channel_id()
    if target is None:
        return None
    local_now = now.astimezone(ZoneInfo(settings.timezone))
    today = local_now.date()

    async with session_maker() as session, session.begin():
        claim = await claim_day(session, today=today, local_now=local_now, now=now)
        if claim is None:
            return None
        post_id = claim.id
        picked = await pick_products(
            session, exclude=await _recent_product_ids(session, today)
        )
        recent_keys = await _recent_template_keys(session)
        store = await setting_repository.get_all(session)
        if not picked:
            claim.status = "failed"
            claim.error = "No active product with a photo to advertise"
            return None

    try:
        chat = await bot.get_chat(target)
        free_from = store.get("free_delivery_from")
        context = CaptionContext(
            products=[
                CaptionProduct(
                    name=product.name,
                    price=money(product.price),
                    old_price=money(product.old_price) if product.old_price else None,
                    category=product.category,
                )
                for product in picked
            ],
            bot_username=settings.bot_username.lstrip("@"),
            phone=pretty_phone(
                store.get("shop_phone") if isinstance(store.get("shop_phone"), str) else None
            ),
            channel_username=chat.username,
            free_delivery_from=(
                money(Decimal(str(free_from)))
                if free_from not in (None, "") and Decimal(str(free_from)) > 0
                else None
            ),
            weekday_date=uzbek_date(today),
        )
        caption = await build_caption(
            context,
            api_key=settings.anthropic_api_key,
            model=settings.marketing_llm_model,
            recent_keys=recent_keys,
        )
        async with httpx.AsyncClient(timeout=60) as client:
            photos = [await load_image(product.image_url, client) for product in picked]
        brand = AdBrand(
            hook=video_hook(caption.hook),
            bot_username=context.bot_username,
            phone=context.phone,
            channel_username=context.channel_username,
        )
        ad_products = [
            AdProduct(
                name=product.name,
                price=money(product.price),
                old_price=money(product.old_price) if product.old_price else None,
                image=photo,
            )
            for product, photo in zip(picked, photos, strict=True)
        ]
        rendered = await asyncio.to_thread(render_advert, ad_products, brand)
        message = await bot.send_video(
            chat_id=target,
            video=BufferedInputFile(rendered.data, filename="kans-shop.mp4"),
            caption=caption.text,
            parse_mode="HTML",
            width=rendered.width,
            height=rendered.height,
            duration=round(rendered.seconds),
            supports_streaming=True,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
        log.exception("marketing_advert_failed", post_id=post_id)
        async with session_maker() as session, session.begin():
            await session.execute(
                update(MarketingPost)
                .where(MarketingPost.id == post_id)
                .values(status="failed", error=error)
            )
        await _notify_failure(bot, error)
        return None

    async with session_maker() as session, session.begin():
        await session.execute(
            update(MarketingPost)
            .where(MarketingPost.id == post_id)
            .values(
                status="sent",
                product_ids=[product.id for product in picked],
                caption=caption.text,
                caption_source=caption.source,
                template_key=caption.key,
                channel_id=target,
                message_id=message.message_id,
                video_seconds=rendered.seconds,
                error=None,
                posted_at=datetime.now(UTC),
            )
        )
        post = await session.get(MarketingPost, post_id)
    log.info("marketing_advert_sent", post_id=post_id, message_id=message.message_id)
    return post


async def _notify_failure(bot: Bot, error: str) -> None:
    if settings.error_channel_id is None:
        return
    try:
        await bot.send_message(
            settings.error_channel_id,
            f"⚠️ Kanal reklamasi chiqmadi. Keyinroq yana urinib ko'riladi.\n{error}",
            parse_mode=None,
        )
    except Exception:
        log.warning("marketing_failure_notice_not_sent", exc_info=True)


async def run_marketing_worker(
    bot: Bot, session_maker: async_sessionmaker[AsyncSession], stop: asyncio.Event
) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=STARTUP_DELAY_SECONDS)
        return
    except TimeoutError:
        pass
    while not stop.is_set():
        try:
            await publish_due_advert(bot, session_maker, now=datetime.now(UTC))
        except Exception:
            log.exception("marketing_worker_cycle_failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=CHECK_INTERVAL_SECONDS)

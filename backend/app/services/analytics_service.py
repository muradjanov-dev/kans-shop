"""Collects storefront behaviour batches and keeps the analytics tables trimmed.

The browser is not trusted: every field is bounded, unknown event types are dropped,
timestamps are corrected for the client's clock and clamped, product ids that do not
exist are cleared, and a session id only accepts events from the visitor that made it.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.schemas.analytics import AnalyticsBatchIn, AnalyticsEventIn
from app.core.logging import get_logger
from app.db.models.admin import Admin
from app.db.models.analytics import ANALYTICS_EVENT_TYPES, AnalyticsEvent, AnalyticsSession
from app.db.models.product import Product
from app.db.models.user import User

log = get_logger(__name__)

KNOWN_TYPES = frozenset(ANALYTICS_EVENT_TYPES)
# An event may be queued offline for a while, but never dated into the future or long ago.
MAX_EVENT_AGE = timedelta(hours=12)
# One timing event covers one flush interval of the storefront (about 20 seconds).
MAX_TIMING_MS = 120_000
# Guest sessions of the same browser are attributed to the customer who later signs in.
BACKFILL_WINDOW = timedelta(days=30)
EVENT_RETENTION = timedelta(days=180)
SESSION_RETENTION = timedelta(days=400)
MAINTENANCE_INTERVAL_SECONDS = 6 * 60 * 60
MAINTENANCE_STARTUP_DELAY_SECONDS = 120

_NUMERIC_SEGMENT = re.compile(r"/\d+(?=/|$)")
_SAFE_SECTION = re.compile(r"[^a-z0-9_:-]")
_SAFE_SOURCE = re.compile(r"[^A-Za-z0-9_.-]")
_BOT_AGENT = re.compile(r"bot\b|crawl|spider|slurp|facebookexternalhit|preview", re.IGNORECASE)
_TIMING_TYPES = frozenset({"page_time", "section_time"})


def looks_like_bot(user_agent: str) -> bool:
    return bool(_BOT_AGENT.search(user_agent or ""))


def normalize_path(raw: str | None) -> str | None:
    """`/product/42?x=1` becomes `/product/:id`; anything that is not a path is dropped."""
    if not raw:
        return None
    path = raw.split("#", 1)[0].split("?", 1)[0].strip()
    if not path.startswith("/") or path.startswith("//"):
        return None
    path = _NUMERIC_SEGMENT.sub("/:id", path)
    if len(path) > 1:
        path = path.rstrip("/")
    return path[:160]


def _clean_text(raw: str | None, limit: int) -> str | None:
    if raw is None:
        return None
    text = " ".join(raw.split())
    return text[:limit] or None


def _clean_section(raw: str | None) -> str | None:
    if not raw:
        return None
    section = _SAFE_SECTION.sub("", raw.strip().lower())
    return section[:48] or None


def _clean_source(raw: str | None) -> str | None:
    if not raw:
        return None
    source = _SAFE_SOURCE.sub("", raw.strip())
    return source[:64] or None


def _referrer_host(raw: str | None) -> str | None:
    if not raw:
        return None
    with contextlib.suppress(ValueError):
        host = urlsplit(raw).hostname
        if host:
            return host.lower()[:160]
    return None


def _event_time(event: AnalyticsEventIn, *, offset: timedelta, now: datetime) -> datetime:
    if event.at is None:
        return now
    try:
        occurred = datetime.fromtimestamp(event.at / 1000, UTC) + offset
    except (OverflowError, OSError, ValueError):
        return now
    return min(max(occurred, now - MAX_EVENT_AGE), now)


def _clock_offset(sent_at: int | None, now: datetime) -> timedelta:
    """How far the browser clock is behind the server; applied to every event time."""
    if sent_at is None:
        return timedelta(0)
    try:
        client_now = datetime.fromtimestamp(sent_at / 1000, UTC)
    except (OverflowError, OSError, ValueError):
        return timedelta(0)
    return now - client_now


async def is_staff(session: AsyncSession, user: User) -> bool:
    if user.is_admin:
        return True
    admin_id = await session.scalar(
        select(Admin.id).where(
            Admin.telegram_id == user.telegram_id, Admin.is_active.is_(True)
        )
    )
    return admin_id is not None


async def _existing_product_ids(session: AsyncSession, ids: Iterable[int]) -> set[int]:
    wanted = {product_id for product_id in ids if product_id}
    if not wanted:
        return set()
    rows = await session.scalars(select(Product.id).where(Product.id.in_(wanted)))
    return set(rows)


async def _claim_session(
    session: AsyncSession, batch: AnalyticsBatchIn, *, started_at: datetime
) -> AnalyticsSession | None:
    inserted = await session.scalar(
        pg_insert(AnalyticsSession)
        .values(
            session_key=batch.session_id,
            visitor_key=batch.visitor_id,
            platform=batch.platform,
            device=batch.device,
            language=_clean_text(batch.language, 8),
            entry_path=normalize_path(batch.entry_path),
            referrer=_referrer_host(batch.referrer),
            source=_clean_source(batch.source),
            started_at=started_at,
            last_seen_at=started_at,
        )
        .on_conflict_do_nothing(index_elements=["session_key"])
        .returning(AnalyticsSession.id)
    )
    row = await session.scalar(
        select(AnalyticsSession)
        .where(AnalyticsSession.session_key == batch.session_id)
        .with_for_update()
    )
    if row is None:
        return None
    if inserted is None and row.visitor_key != batch.visitor_id:
        # Someone replayed another browser's session id: ignore rather than mix visitors.
        return None
    return row


async def _attribute_visitor(
    session: AsyncSession,
    *,
    visitor_key: uuid.UUID,
    user_id: int,
    staff: bool,
    now: datetime,
) -> None:
    """Earlier guest sessions of this browser belong to the customer who just signed in."""
    values: dict[str, object] = {"user_id": user_id}
    if staff:
        values["is_staff"] = True
    await session.execute(
        update(AnalyticsSession)
        .where(
            AnalyticsSession.visitor_key == visitor_key,
            AnalyticsSession.user_id.is_(None),
            AnalyticsSession.last_seen_at >= now - BACKFILL_WINDOW,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )


async def ingest_batch(
    session: AsyncSession,
    batch: AnalyticsBatchIn,
    *,
    user: User | None,
    now: datetime,
) -> int:
    """Store one storefront batch; returns how many events were kept."""
    offset = _clock_offset(batch.sent_at, now)
    known = [
        (event, _event_time(event, offset=offset, now=now))
        for event in batch.events
        if event.type in KNOWN_TYPES
    ]
    started_at = min((occurred for _event, occurred in known), default=now)
    row = await _claim_session(session, batch, started_at=started_at)
    if row is None:
        return 0
    # The bulk UPDATE below expires the ORM row; read what is needed from it now.
    row_id, visitor_key, had_user = row.id, row.visitor_key, row.user_id is not None
    products = await _existing_product_ids(
        session, (event.product_id or 0 for event, _occurred in known)
    )

    rows: list[dict[str, object]] = []
    engaged_ms = 0
    page_views = 0
    latest = row.last_seen_at
    for event, occurred in known:
        latest = max(latest, occurred)
        value = event.value
        if event.type in _TIMING_TYPES:
            value = min(value or 0, MAX_TIMING_MS)
            if value <= 0:
                continue
            if event.type == "page_time":
                engaged_ms += value
        if event.type == "page_view":
            page_views += 1
        rows.append(
            {
                "session_id": row_id,
                "type": event.type,
                "path": normalize_path(event.path),
                "section": _clean_section(event.section),
                "target": _clean_text(event.target, 96),
                "label": _clean_text(event.label, 160),
                "product_id": event.product_id if event.product_id in products else None,
                "value": value,
                "occurred_at": occurred,
            }
        )

    if rows:
        await session.execute(insert(AnalyticsEvent), rows)

    values: dict[str, object] = {
        "last_seen_at": latest,
        "page_views": AnalyticsSession.page_views + page_views,
        "events_count": AnalyticsSession.events_count + len(rows),
        "engaged_ms": AnalyticsSession.engaged_ms + engaged_ms,
    }
    staff = False
    if user is not None:
        staff = await is_staff(session, user)
        values["user_id"] = func.coalesce(AnalyticsSession.user_id, user.id)
        if staff:
            values["is_staff"] = True
    await session.execute(
        update(AnalyticsSession)
        .where(AnalyticsSession.id == row_id)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if user is not None and not had_user:
        await _attribute_visitor(
            session, visitor_key=visitor_key, user_id=user.id, staff=staff, now=now
        )
    return len(rows)


# --------------------------------------------------------------------------- retention


async def prune_analytics(session: AsyncSession, *, now: datetime) -> tuple[int, int]:
    """Drop events after 180 days and whole sessions after 400 days of silence."""
    events = await session.execute(
        delete(AnalyticsEvent).where(AnalyticsEvent.occurred_at < now - EVENT_RETENTION)
    )
    sessions = await session.execute(
        delete(AnalyticsSession).where(
            or_(
                AnalyticsSession.last_seen_at < now - SESSION_RETENTION,
                AnalyticsSession.started_at < now - SESSION_RETENTION,
            )
        )
    )
    return int(getattr(events, "rowcount", 0) or 0), int(getattr(sessions, "rowcount", 0) or 0)


async def run_analytics_maintenance(
    session_maker: async_sessionmaker[AsyncSession], stop: asyncio.Event
) -> None:
    # Let the API finish starting (and short-lived test apps finish) before the first sweep.
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=MAINTENANCE_STARTUP_DELAY_SECONDS)
    while not stop.is_set():
        try:
            async with session_maker() as session, session.begin():
                events, sessions = await prune_analytics(session, now=datetime.now(UTC))
            if events or sessions:
                log.info("analytics_pruned", events=events, sessions=sessions)
        except Exception:
            log.exception("analytics_maintenance_failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=MAINTENANCE_INTERVAL_SECONDS)

from __future__ import annotations

import asyncio
import contextlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup
from redis.asyncio import Redis
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.keyboards.inline.admin_broadcast import broadcast_content_button
from app.core.logging import get_logger
from app.db.models.admin import Admin
from app.db.models.broadcast import Broadcast
from app.db.models.broadcast_recipient import BroadcastRecipient
from app.db.models.enums import (
    AdminRole,
    BroadcastRecipientStatus,
    BroadcastStatus,
)
from app.db.models.user import User
from app.db.repositories import user_repository
from app.services.admin_broadcast_service import (
    fingerprint_broadcast_content,
    fingerprint_broadcast_preview,
)
from app.services.broadcast_media_service import read_broadcast_photo
from app.services.telegram_pacing_service import acquire_telegram_slot

log = get_logger(__name__)

LEASE_SECONDS = 90
BATCH_SIZE = 20
POLL_SECONDS = 0.5
_LIVE_BROADCAST_ROLES = frozenset({AdminRole.MANAGER, AdminRole.SUPERADMIN})


@dataclass(frozen=True)
class BroadcastClaim:
    recipient_id: int
    broadcast_id: int
    user_id: int
    lease_token: UUID
    attempts: int


@dataclass(frozen=True)
class _Delivery:
    chat_id: int
    text: str
    photo: str | BufferedInputFile | None
    reply_markup: InlineKeyboardMarkup | None


async def _stop_uncheckpointed_legacy_rows(session: AsyncSession) -> None:
    legacy_ids = list(
        (
            await session.scalars(
                select(Broadcast.id).where(
                    Broadcast.status == BroadcastStatus.SENDING,
                    or_(
                        Broadcast.launch_idempotency_key.is_(None),
                        Broadcast.preview_content_fingerprint.is_(None),
                        Broadcast.launch_fingerprint.is_(None),
                        Broadcast.launch_count.is_(None),
                        Broadcast.launcher_auth_epoch.is_(None),
                        Broadcast.launched_at.is_(None),
                    ),
                )
            )
        ).all()
    )
    if not legacy_ids:
        return
    await session.execute(
        update(BroadcastRecipient)
        .where(
            BroadcastRecipient.broadcast_id.in_(legacy_ids),
            BroadcastRecipient.status.in_(
                (BroadcastRecipientStatus.PENDING, BroadcastRecipientStatus.SENDING)
            ),
        )
        .values(
            status=BroadcastRecipientStatus.CANCELLED,
            lease_token=None,
            lease_expires_at=None,
            last_error="missing_launch_checkpoint",
        )
    )
    await session.execute(
        update(Broadcast)
        .where(Broadcast.id.in_(legacy_ids))
        .values(status=BroadcastStatus.FAILED)
    )


async def _stop_incomplete_checkpoint_rows(session: AsyncSession) -> None:
    incomplete_ids = list(
        (
            await session.scalars(
                select(Broadcast.id)
                .outerjoin(
                    BroadcastRecipient,
                    BroadcastRecipient.broadcast_id == Broadcast.id,
                )
                .where(
                    Broadcast.status == BroadcastStatus.SENDING,
                    Broadcast.preview_content_fingerprint.is_not(None),
                    Broadcast.launch_idempotency_key.is_not(None),
                    Broadcast.launch_fingerprint.is_not(None),
                    Broadcast.launch_count > 0,
                    Broadcast.launcher_auth_epoch.is_not(None),
                    Broadcast.launched_at.is_not(None),
                )
                .group_by(Broadcast.id, Broadcast.launch_count)
                .having(func.count(BroadcastRecipient.id) != Broadcast.launch_count)
            )
        ).all()
    )
    if not incomplete_ids:
        return
    await session.execute(
        update(BroadcastRecipient)
        .where(
            BroadcastRecipient.broadcast_id.in_(incomplete_ids),
            BroadcastRecipient.status == BroadcastRecipientStatus.PENDING,
        )
        .values(
            status=BroadcastRecipientStatus.CANCELLED,
            last_error="recipient_checkpoint_changed",
        )
    )
    await session.execute(
        update(Broadcast)
        .where(Broadcast.id.in_(incomplete_ids))
        .values(status=BroadcastStatus.FAILED)
    )


async def _settle_stopped_expired_claims(session: AsyncSession, *, now: datetime) -> None:
    stopped_broadcasts = select(Broadcast.id).where(
        Broadcast.status.in_((BroadcastStatus.CANCELLED, BroadcastStatus.FAILED))
    )
    await session.execute(
        update(BroadcastRecipient)
        .where(
            BroadcastRecipient.broadcast_id.in_(stopped_broadcasts),
            BroadcastRecipient.status == BroadcastRecipientStatus.SENDING,
            BroadcastRecipient.lease_expires_at <= now,
        )
        .values(
            status=BroadcastRecipientStatus.CANCELLED,
            last_error="broadcast_stopped",
            lease_token=None,
            lease_expires_at=None,
        )
    )


async def claim_broadcast_batch(
    session: AsyncSession,
    *,
    worker_id: str,
    now: datetime,
    limit: int,
    lease_seconds: int,
) -> list[BroadcastClaim]:
    """Lease due recipient checkpoints in a short transaction; never rebuild an audience."""
    if not worker_id.strip():
        raise ValueError("worker_id must not be blank")
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if limit < 1 or lease_seconds < 1:
        raise ValueError("limit and lease_seconds must be positive")

    await _stop_uncheckpointed_legacy_rows(session)
    await _stop_incomplete_checkpoint_rows(session)
    await _settle_stopped_expired_claims(session, now=now)
    eligible = or_(
        (BroadcastRecipient.status == BroadcastRecipientStatus.PENDING)
        & (BroadcastRecipient.next_available_at <= now),
        (BroadcastRecipient.status == BroadcastRecipientStatus.SENDING)
        & (BroadcastRecipient.lease_expires_at <= now),
    )
    rows = list(
        (
            await session.scalars(
                select(BroadcastRecipient)
                .join(Broadcast, Broadcast.id == BroadcastRecipient.broadcast_id)
                .where(
                    eligible,
                    Broadcast.status == BroadcastStatus.SENDING,
                    Broadcast.launch_idempotency_key.is_not(None),
                    Broadcast.preview_content_fingerprint.is_not(None),
                    Broadcast.launch_fingerprint.is_not(None),
                    Broadcast.launch_count.is_not(None),
                    Broadcast.launcher_auth_epoch.is_not(None),
                    Broadcast.launched_at.is_not(None),
                )
                .order_by(BroadcastRecipient.next_available_at, BroadcastRecipient.id)
                .limit(limit)
                .with_for_update(of=BroadcastRecipient, skip_locked=True)
            )
        ).all()
    )
    claims: list[BroadcastClaim] = []
    for recipient in rows:
        token = uuid4()
        recipient.status = BroadcastRecipientStatus.SENDING
        recipient.attempts += 1
        recipient.lease_token = str(token)
        recipient.lease_expires_at = now + timedelta(seconds=lease_seconds)
        claims.append(
            BroadcastClaim(
                recipient_id=recipient.id,
                broadcast_id=recipient.broadcast_id,
                user_id=recipient.user_id,
                lease_token=token,
                attempts=recipient.attempts,
            )
        )
    await session.flush()
    return claims


async def _mark_claim(
    session: AsyncSession,
    *,
    claim: BroadcastClaim,
    status: BroadcastRecipientStatus,
    last_error: str | None,
    sent_at: datetime | None = None,
    available_at: datetime | None = None,
) -> bool:
    values: dict[str, object] = {
        "status": status,
        "last_error": last_error,
        "lease_token": None,
        "lease_expires_at": None,
    }
    if sent_at is not None:
        values["sent_at"] = sent_at
    if available_at is not None:
        values["next_available_at"] = available_at
    result = await session.execute(
        update(BroadcastRecipient)
        .where(
            BroadcastRecipient.id == claim.recipient_id,
            BroadcastRecipient.broadcast_id == claim.broadcast_id,
            BroadcastRecipient.user_id == claim.user_id,
            BroadcastRecipient.status == BroadcastRecipientStatus.SENDING,
            BroadcastRecipient.lease_token == str(claim.lease_token),
        )
        .values(**values)
        .returning(BroadcastRecipient.id)
    )
    return result.scalar_one_or_none() is not None


async def _refresh_progress(session: AsyncSession, broadcast_id: int) -> None:
    broadcast = await session.get(Broadcast, broadcast_id, populate_existing=True)
    if broadcast is None:
        return
    rows = (
        await session.execute(
            select(BroadcastRecipient.status, func.count())
            .where(BroadcastRecipient.broadcast_id == broadcast_id)
            .group_by(BroadcastRecipient.status)
        )
    ).all()
    counts: dict[BroadcastRecipientStatus, int] = {status: count for status, count in rows}
    broadcast.sent_count = counts.get(BroadcastRecipientStatus.SENT, 0)
    broadcast.failed_count = counts.get(BroadcastRecipientStatus.FAILED, 0)
    total = sum(counts.values())
    remaining = counts.get(BroadcastRecipientStatus.PENDING, 0) + counts.get(
        BroadcastRecipientStatus.SENDING, 0
    )
    if broadcast.status == BroadcastStatus.SENDING and remaining == 0 and total > 0:
        broadcast.status = (
            BroadcastStatus.FAILED
            if broadcast.sent_count == 0 and broadcast.failed_count > 0
            else BroadcastStatus.COMPLETED
        )


async def _cancel_job(
    session: AsyncSession,
    *,
    broadcast: Broadcast,
    claim: BroadcastClaim,
    reason: str,
) -> None:
    await _mark_claim(
        session,
        claim=claim,
        status=BroadcastRecipientStatus.CANCELLED,
        last_error=reason,
    )
    await session.execute(
        update(BroadcastRecipient)
        .where(
            BroadcastRecipient.broadcast_id == broadcast.id,
            BroadcastRecipient.status == BroadcastRecipientStatus.PENDING,
        )
        .values(
            status=BroadcastRecipientStatus.CANCELLED,
            last_error=reason,
        )
    )
    broadcast.status = BroadcastStatus.CANCELLED
    await session.flush()


async def _check_live_delivery(
    session: AsyncSession, claim: BroadcastClaim
) -> _Delivery | None:
    recipient = await session.scalar(
        select(BroadcastRecipient).where(
            BroadcastRecipient.id == claim.recipient_id,
            BroadcastRecipient.broadcast_id == claim.broadcast_id,
            BroadcastRecipient.user_id == claim.user_id,
            BroadcastRecipient.status == BroadcastRecipientStatus.SENDING,
            BroadcastRecipient.lease_token == str(claim.lease_token),
        )
    )
    if recipient is None:
        return None
    broadcast = await session.get(Broadcast, claim.broadcast_id, populate_existing=True)
    if broadcast is None:
        await _mark_claim(
            session,
            claim=claim,
            status=BroadcastRecipientStatus.CANCELLED,
            last_error="broadcast_missing",
        )
        return None
    if broadcast.status != BroadcastStatus.SENDING:
        await _mark_claim(
            session,
            claim=claim,
            status=BroadcastRecipientStatus.CANCELLED,
            last_error="cancelled_by_admin",
        )
        return None

    if (
        broadcast.launch_idempotency_key is None
        or broadcast.preview_content_fingerprint is None
        or broadcast.launch_fingerprint is None
        or broadcast.launch_count is None
        or broadcast.launcher_auth_epoch is None
        or broadcast.launched_at is None
        or broadcast.admin_id is None
    ):
        await _cancel_job(
            session, broadcast=broadcast, claim=claim, reason="missing_launch_checkpoint"
        )
        return None

    actor = await session.get(Admin, broadcast.admin_id, populate_existing=True)
    if (
        actor is None
        or not actor.is_active
        or actor.role not in _LIVE_BROADCAST_ROLES
        or actor.auth_epoch != broadcast.launcher_auth_epoch
    ):
        await _cancel_job(session, broadcast=broadcast, claim=claim, reason="launcher_revoked")
        return None

    snapshot_ids = list(
        (
            await session.scalars(
                select(BroadcastRecipient.user_id)
                .where(BroadcastRecipient.broadcast_id == broadcast.id)
                .order_by(BroadcastRecipient.user_id)
            )
        ).all()
    )
    if len(snapshot_ids) != broadcast.launch_count:
        await _cancel_job(
            session, broadcast=broadcast, claim=claim, reason="recipient_checkpoint_changed"
        )
        return None
    current_content_fingerprint = fingerprint_broadcast_content(
        target=broadcast.target,
        text=broadcast.text,
        photo_storage_key=broadcast.photo_storage_key,
        photo_file_id=broadcast.photo_file_id,
        button_text=broadcast.button_text,
        button_url=broadcast.button_url,
    )
    if current_content_fingerprint != broadcast.preview_content_fingerprint:
        await _cancel_job(session, broadcast=broadcast, claim=claim, reason="preview_changed")
        return None
    current_fingerprint = fingerprint_broadcast_preview(
        snapshot_ids,
        target=broadcast.target,
        text=broadcast.text,
        photo_storage_key=broadcast.photo_storage_key,
        photo_file_id=broadcast.photo_file_id,
        button_text=broadcast.button_text,
        button_url=broadcast.button_url,
    )
    if current_fingerprint != broadcast.launch_fingerprint:
        await _cancel_job(session, broadcast=broadcast, claim=claim, reason="preview_changed")
        return None

    snapshot_users = list(
        (
            await session.scalars(
                select(User).where(User.id.in_(snapshot_ids)).order_by(User.id)
            )
        ).all()
    )
    expected_live_ids = {user.id for user in snapshot_users if not user.is_blocked}
    from app.services.admin_broadcast_service import _audience_ids

    live_ids = set(await _audience_ids(session, broadcast.target))
    if live_ids != expected_live_ids:
        await _cancel_job(session, broadcast=broadcast, claim=claim, reason="audience_changed")
        return None

    user = await user_repository.get_by_id(session, claim.user_id)
    if user is None or user.is_blocked:
        await _mark_claim(
            session,
            claim=claim,
            status=BroadcastRecipientStatus.FAILED,
            last_error="recipient_blocked" if user is not None else "recipient_missing",
        )
        await _refresh_progress(session, broadcast.id)
        return None

    photo: str | BufferedInputFile | None = broadcast.photo_file_id
    if broadcast.photo_storage_key is not None:
        try:
            content, filename = read_broadcast_photo(broadcast.photo_storage_key)
        except (FileNotFoundError, OSError, ValueError):
            await _mark_claim(
                session,
                claim=claim,
                status=BroadcastRecipientStatus.FAILED,
                last_error="media_unavailable",
            )
            await _refresh_progress(session, broadcast.id)
            return None
        photo = BufferedInputFile(content, filename=filename)

    return _Delivery(
        chat_id=user.telegram_id,
        text=broadcast.text,
        photo=photo,
        reply_markup=broadcast_content_button(broadcast.button_text, broadcast.button_url),
    )


async def _retry_claim(
    session_maker: async_sessionmaker[AsyncSession],
    claim: BroadcastClaim,
    *,
    available_at: datetime,
    safe_error: str,
) -> None:
    async with session_maker() as session, session.begin():
        updated = await _mark_claim(
            session,
            claim=claim,
            status=BroadcastRecipientStatus.PENDING,
            last_error=safe_error,
            available_at=available_at,
        )
        if updated:
            await _refresh_progress(session, claim.broadcast_id)


async def _fail_claim(
    session_maker: async_sessionmaker[AsyncSession],
    claim: BroadcastClaim,
    *,
    safe_error: str,
    block_user: bool = False,
) -> None:
    async with session_maker() as session, session.begin():
        if block_user:
            await session.execute(
                update(User).where(User.id == claim.user_id).values(is_blocked=True)
            )
        updated = await _mark_claim(
            session,
            claim=claim,
            status=BroadcastRecipientStatus.FAILED,
            last_error=safe_error,
        )
        if updated:
            await _refresh_progress(session, claim.broadcast_id)


async def process_broadcast_claim(
    bot: Bot,
    session_maker: async_sessionmaker[AsyncSession],
    redis: Redis,
    claim: BroadcastClaim,
) -> None:
    try:
        await acquire_telegram_slot(redis, bot_id=bot.id, now=datetime.now(UTC))
        # The fresh authorization, cancellation, preview and recipient checks happen after pacing
        # so they are as close as possible to the external send call.
        async with session_maker() as session, session.begin():
            delivery = await _check_live_delivery(session, claim)
        if delivery is None:
            return
        if delivery.photo is not None:
            await bot.send_photo(
                delivery.chat_id,
                photo=delivery.photo,
                caption=delivery.text,
                reply_markup=delivery.reply_markup,
                parse_mode=None,
            )
        else:
            await bot.send_message(
                delivery.chat_id,
                delivery.text,
                reply_markup=delivery.reply_markup,
                parse_mode=None,
            )
    except TelegramRetryAfter as exc:
        await _retry_claim(
            session_maker,
            claim,
            available_at=datetime.now(UTC) + timedelta(seconds=float(exc.retry_after)),
            safe_error="telegram_retry_after",
        )
        log.warning(
            "broadcast_delivery_retry",
            broadcast_id=claim.broadcast_id,
            recipient_id=claim.recipient_id,
            error_code="telegram_retry_after",
        )
        return
    except TelegramForbiddenError:
        await _fail_claim(
            session_maker,
            claim,
            safe_error="telegram_forbidden",
            block_user=True,
        )
        log.warning(
            "broadcast_delivery_failed",
            broadcast_id=claim.broadcast_id,
            recipient_id=claim.recipient_id,
            error_code="telegram_forbidden",
        )
        return
    except TelegramBadRequest:
        await _fail_claim(session_maker, claim, safe_error="telegram_bad_request")
        log.warning(
            "broadcast_delivery_failed",
            broadcast_id=claim.broadcast_id,
            recipient_id=claim.recipient_id,
            error_code="telegram_bad_request",
        )
        return
    except asyncio.CancelledError:
        raise
    except Exception:
        await _retry_claim(
            session_maker,
            claim,
            available_at=datetime.now(UTC)
            + timedelta(seconds=min(300, 2 ** min(claim.attempts, 8))),
            safe_error="delivery_error",
        )
        log.warning(
            "broadcast_delivery_retry",
            broadcast_id=claim.broadcast_id,
            recipient_id=claim.recipient_id,
            error_code="delivery_error",
        )
        return

    async with session_maker() as session, session.begin():
        sent = await _mark_claim(
            session,
            claim=claim,
            status=BroadcastRecipientStatus.SENT,
            last_error=None,
            sent_at=datetime.now(UTC),
        )
        if sent:
            await _refresh_progress(session, claim.broadcast_id)
    if sent:
        log.info(
            "broadcast_recipient_sent",
            broadcast_id=claim.broadcast_id,
            recipient_id=claim.recipient_id,
        )


async def _wait_or_stop(stop: asyncio.Event) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)


async def run_broadcast_worker(
    bot: Bot,
    session_maker: async_sessionmaker[AsyncSession],
    redis: Redis,
    stop: asyncio.Event,
) -> None:
    worker_id = f"broadcast-{os.getpid()}-{uuid4().hex}"
    while not stop.is_set():
        try:
            now = datetime.now(UTC)
            async with session_maker() as session, session.begin():
                claims = await claim_broadcast_batch(
                    session,
                    worker_id=worker_id,
                    now=now,
                    limit=BATCH_SIZE,
                    lease_seconds=LEASE_SECONDS,
                )
            if not claims:
                await _wait_or_stop(stop)
                continue
            for claim in claims:
                if stop.is_set():
                    break
                await process_broadcast_claim(bot, session_maker, redis, claim)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.error("broadcast_worker_iteration_failed", error_code="delivery_error")
            await _wait_or_stop(stop)

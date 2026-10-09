"""Durable Telegram notification delivery.

The worker contract for Task 10 is deliberately small: claims contain only row IDs, event type,
recipient IDs and a lease token; renderers reload their related rows and authorization state just
before sending. Add new ID-only event renderers in :func:`_render_event`. Broadcast workers share
the bot-wide Redis rate gate through ``telegram_pacing_service.acquire_telegram_slot``.

Supported producer contracts:

* ``order.created``: aggregate is the order ID; one row per admin recipient.
* ``order.status.changed``: aggregate is order ID, payload is OrderStatusHistory ID; recipient is
  the customer. ``order.admin_card.status_updated`` targets an admin with an existing card.
* ``order.gateway_payment.confirmed``: payload is PaymentTransaction ID. The paired
  ``order.admin_card.gateway_payment_updated`` refreshes an admin card.
* ``order.manual_payment.accepted``: payload is AdminAuditEvent ID. The paired
  ``order.admin_card.manual_payment_updated`` refreshes an admin card.
* ``admin.order_message.queued``: aggregate is order ID, payload is AdminOrderMessage ID, and the
  recipient is the actual order owner. The protected message is always sent with ``parse_mode=None``.
* ``admin.team.changed`` and ``store.settings.updated`` use AdminAuditEvent payload IDs;
  ``traffic_source.created``/``traffic_source.updated`` use a traffic-source aggregate ID and an
  audit payload ID. ``system.deploy`` has no payload.

Every claim must be made in a short caller-owned transaction. Telegram requests happen after that
transaction closes. A process crash after Telegram accepts a message but before token-guarded ack
can deliver a duplicate after lease expiry; this is at-least-once delivery, not exactly-once.
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup
from redis.asyncio import Redis
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.services.order_notifications import translator_for_admin
from app.bot.utils.admin_order_card import build_admin_order_keyboard, build_admin_order_text
from app.bot.utils.i18n import translate
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.admin import Admin
from app.db.models.admin_audit_event import AdminAuditEvent
from app.db.models.admin_order_message import AdminOrderMessage
from app.db.models.enums import (
    NotificationOutboxStatus,
    OrderStatus,
)
from app.db.models.notification_outbox import NotificationOutbox
from app.db.models.order_status_history import OrderStatusHistory
from app.db.models.payment_transaction import PaymentTransaction
from app.db.models.traffic_source import TrafficSource
from app.db.models.user import User
from app.db.repositories import order_repository, user_repository
from app.services.telegram_pacing_service import acquire_telegram_slot

log = get_logger(__name__)

LEASE_SECONDS = 90
BATCH_SIZE = 20
POLL_SECONDS = 0.5
_SAFE_ERROR_CODES = {
    "actor_inactive",
    "admin_inactive",
    "admin_notifications_disabled",
    "event_data_missing",
    "event_superseded",
    "recipient_blocked",
    "recipient_missing",
    "telegram_bad_request",
    "telegram_forbidden",
    "telegram_retry_after",
    "delivery_error",
    "unknown_event_type",
}
_STATUS_ACTION_KEYS = {
    OrderStatus.CONFIRMED: "admin.confirmed_by",
    OrderStatus.PREPARING: "admin.preparing_by",
    OrderStatus.DELIVERING: "admin.delivering_by",
    OrderStatus.COMPLETED: "admin.completed_by",
    OrderStatus.CANCELLED: "admin.cancelled_by",
}


@dataclass(frozen=True)
class OutboxClaim:
    event_id: int
    event_type: str
    aggregate_id: str
    payload_id: str | None
    recipient_user_id: int | None
    recipient_admin_id: int | None
    lease_token: UUID
    attempts: int


@dataclass(frozen=True)
class _Delivery:
    operation: Literal["send_message", "send_order", "edit_order"]
    chat_id: int
    text: str
    reply_markup: InlineKeyboardMarkup | None = None
    message_id: int | None = None
    order_id: int | None = None
    receipt_file_id: str | None = None
    receipt_is_pdf: bool = False
    parse_mode: str | None = "HTML"


@dataclass(frozen=True)
class _Skip:
    error_code: str


async def claim_outbox_batch(
    session: AsyncSession,
    *,
    worker_id: str,
    now: datetime,
    limit: int,
    lease_seconds: int,
) -> list[OutboxClaim]:
    """Lock and lease due rows. The caller commits this short claim transaction before sending."""
    if not worker_id.strip():
        raise ValueError("worker_id must not be blank")
    if limit < 1 or lease_seconds < 1:
        raise ValueError("limit and lease_seconds must be positive")

    eligible = or_(
        (
            (NotificationOutbox.status == NotificationOutboxStatus.PENDING)
            & (NotificationOutbox.next_available_at <= now)
        ),
        (
            (NotificationOutbox.status == NotificationOutboxStatus.SENDING)
            & (NotificationOutbox.lease_expires_at <= now)
        ),
    )
    rows = list(
        (
            await session.scalars(
                select(NotificationOutbox)
                .where(eligible)
                .order_by(NotificationOutbox.next_available_at, NotificationOutbox.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    claims: list[OutboxClaim] = []
    for row in rows:
        token = uuid4()
        row.status = NotificationOutboxStatus.SENDING
        row.attempts += 1
        row.lease_token = str(token)
        row.lease_expires_at = now + timedelta(seconds=lease_seconds)
        claims.append(
            OutboxClaim(
                event_id=row.id,
                event_type=row.event_type,
                aggregate_id=row.aggregate_id,
                payload_id=row.payload_id,
                recipient_user_id=row.recipient_user_id,
                recipient_admin_id=row.recipient_admin_id,
                lease_token=token,
                attempts=row.attempts,
            )
        )
    await session.flush()
    return claims


async def ack_outbox(
    session: AsyncSession,
    *,
    event_id: int,
    lease_token: UUID,
    sent_at: datetime,
) -> bool:
    result = await session.execute(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.id == event_id,
            NotificationOutbox.status == NotificationOutboxStatus.SENDING,
            NotificationOutbox.lease_token == str(lease_token),
        )
        .values(
            status=NotificationOutboxStatus.SENT,
            sent_at=sent_at,
            lease_token=None,
            lease_expires_at=None,
            last_error=None,
        )
        .returning(NotificationOutbox.id)
    )
    return result.scalar_one_or_none() is not None


async def retry_outbox(
    session: AsyncSession,
    *,
    event_id: int,
    lease_token: UUID,
    available_at: datetime,
    safe_error: str,
) -> bool:
    error_code = safe_error if safe_error in _SAFE_ERROR_CODES else "delivery_error"
    result = await session.execute(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.id == event_id,
            NotificationOutbox.status == NotificationOutboxStatus.SENDING,
            NotificationOutbox.lease_token == str(lease_token),
        )
        .values(
            status=NotificationOutboxStatus.PENDING,
            next_available_at=available_at,
            lease_token=None,
            lease_expires_at=None,
            last_error=error_code,
        )
        .returning(NotificationOutbox.id)
    )
    return result.scalar_one_or_none() is not None


async def _fail_outbox(
    session: AsyncSession, *, event_id: int, lease_token: UUID, safe_error: str
) -> bool:
    error_code = safe_error if safe_error in _SAFE_ERROR_CODES else "delivery_error"
    result = await session.execute(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.id == event_id,
            NotificationOutbox.status == NotificationOutboxStatus.SENDING,
            NotificationOutbox.lease_token == str(lease_token),
        )
        .values(
            status=NotificationOutboxStatus.FAILED,
            lease_token=None,
            lease_expires_at=None,
            last_error=error_code,
        )
        .returning(NotificationOutbox.id)
    )
    return result.scalar_one_or_none() is not None


async def _fresh_admin(
    session: AsyncSession, admin_id: int
) -> tuple[Admin | None, str | None]:
    admin = await session.scalar(
        select(Admin).where(Admin.id == admin_id).execution_options(populate_existing=True)
    )
    if admin is None or not admin.is_active:
        return None, "admin_inactive"
    if not admin.notifications_enabled:
        return None, "admin_notifications_disabled"
    return admin, None


async def _actor_is_live(session: AsyncSession, actor_id: int | None) -> bool:
    if actor_id is None:
        return True
    actor = await session.get(Admin, actor_id, populate_existing=True)
    return actor is not None and actor.is_active


async def _render_order_status(session: AsyncSession, claim: OutboxClaim) -> _Delivery | _Skip:
    if claim.payload_id is None:
        return _Skip("event_data_missing")
    history = await session.get(
        OrderStatusHistory, int(claim.payload_id), populate_existing=True
    )
    order = await order_repository.get_by_id(session, int(claim.aggregate_id))
    if history is None or order is None or history.order_id != order.id:
        return _Skip("event_data_missing")
    if history.changed_by_admin_id is None or not await _actor_is_live(
        session, history.changed_by_admin_id
    ):
        return _Skip("actor_inactive")
    if claim.recipient_user_id is None or claim.recipient_user_id != order.user_id:
        return _Skip("recipient_missing")
    customer = await user_repository.get_by_id(session, claim.recipient_user_id)
    if customer is None:
        return _Skip("recipient_missing")
    if customer.is_blocked:
        return _Skip("recipient_blocked")

    def translator(key: str, **kwargs: str) -> str:
        return translate(customer.language, key, **kwargs)

    if history.to_status == OrderStatus.CANCELLED:
        key = "orders.cancelled_notification"
        kwargs = {"reason": html.escape(history.comment or "-")}
    elif history.to_status == OrderStatus.CONFIRMED:
        key, kwargs = "orders.confirmed_notification", {}
    else:
        key = "orders.status_changed_notification"
        kwargs = {
            "status": translator(f"orders.status_{history.to_status.value}"),
        }
    text = translator(key, order_number=order.order_number, **kwargs)
    return _Delivery("send_message", customer.telegram_id, text)


async def _render_admin_order_card(
    session: AsyncSession,
    claim: OutboxClaim,
    *,
    actor_id: int | None,
    payment_review: bool = False,
    status_history: OrderStatusHistory | None = None,
) -> _Delivery | _Skip:
    if claim.recipient_admin_id is None:
        return _Skip("recipient_missing")
    admin, error = await _fresh_admin(session, claim.recipient_admin_id)
    if admin is None:
        return _Skip(error or "admin_inactive")
    if not await _actor_is_live(session, actor_id):
        return _Skip("actor_inactive")
    order = await order_repository.get_by_id(session, int(claim.aggregate_id))
    if order is None:
        return _Skip("event_data_missing")
    message_id = order.admin_message_ids.get(str(admin.telegram_id))
    if message_id is None:
        # The order.created event may still be waiting to send this admin's first card.
        return _Skip("event_data_missing")
    customer = await user_repository.get_by_id(session, order.user_id)
    if customer is None:
        return _Skip("event_data_missing")
    translator = await translator_for_admin(session, admin.telegram_id)
    processed_line = None
    if status_history is not None:
        if status_history.changed_by_admin_id is None:
            return _Skip("actor_inactive")
        if status_history.to_status != order.status:
            return _Skip("event_superseded")
        action_key = _STATUS_ACTION_KEYS.get(status_history.to_status)
        if action_key is not None and status_history.changed_by_admin_id is not None:
            actor = await session.get(
                Admin, status_history.changed_by_admin_id, populate_existing=True
            )
            if actor is None or not actor.is_active:
                return _Skip("actor_inactive")
            action_kwargs = {
                "admin": html.escape(actor.full_name),
                "time": datetime.now(UTC)
                .astimezone(ZoneInfo(settings.timezone))
                .strftime("%H:%M"),
            }
            if status_history.to_status == OrderStatus.CANCELLED:
                action_kwargs["reason"] = html.escape(status_history.comment or "-")
            processed_line = translator(action_key, **action_kwargs)
    elif payment_review:
        audit = await session.get(AdminAuditEvent, int(claim.payload_id or 0))
        if audit is None or audit.actor_admin_id is None:
            return _Skip("event_data_missing")
        actor = await session.get(Admin, audit.actor_admin_id, populate_existing=True)
        if actor is None or not actor.is_active:
            return _Skip("actor_inactive")
        processed_line = translator(
            "admin.payment_accepted_by",
            admin=html.escape(actor.full_name),
            time=datetime.now(UTC).astimezone(ZoneInfo(settings.timezone)).strftime("%H:%M"),
        )
    text = build_admin_order_text(
        order, customer, translator=translator, processed_line=processed_line
    )
    keyboard = build_admin_order_keyboard(order, translator=translator)
    return _Delivery(
        "edit_order",
        admin.telegram_id,
        text,
        reply_markup=keyboard,
        message_id=int(message_id),
    )


async def _render_event(session: AsyncSession, claim: OutboxClaim) -> _Delivery | _Skip:
    if claim.event_type == "admin.order_message.queued":
        if claim.payload_id is None or claim.recipient_user_id is None:
            return _Skip("event_data_missing")
        order = await order_repository.get_by_id(session, int(claim.aggregate_id))
        message = await session.get(AdminOrderMessage, int(claim.payload_id))
        customer = await user_repository.get_by_id(session, claim.recipient_user_id)
        if (
            order is None
            or message is None
            or customer is None
            or order.user_id != claim.recipient_user_id
            or message.order_id != order.id
        ):
            return _Skip("recipient_missing")
        if customer.is_blocked:
            return _Skip("recipient_blocked")
        if message.admin_id is None or not await _actor_is_live(session, message.admin_id):
            return _Skip("actor_inactive")
        return _Delivery("send_message", customer.telegram_id, message.text, parse_mode=None)

    if claim.event_type == "order.created":
        if claim.recipient_admin_id is None:
            return _Skip("recipient_missing")
        admin, error = await _fresh_admin(session, claim.recipient_admin_id)
        if admin is None:
            return _Skip(error or "admin_inactive")
        order = await order_repository.get_by_id(session, int(claim.aggregate_id))
        if order is None:
            return _Skip("event_data_missing")
        customer = await user_repository.get_by_id(session, order.user_id)
        if customer is None:
            return _Skip("event_data_missing")
        translator = await translator_for_admin(session, admin.telegram_id)
        text = build_admin_order_text(order, customer, translator=translator)
        keyboard = build_admin_order_keyboard(order, translator=translator)
        return _Delivery(
            "send_order",
            admin.telegram_id,
            text,
            reply_markup=keyboard,
            order_id=order.id,
            receipt_file_id=order.receipt_file_id,
            receipt_is_pdf=bool(
                order.receipt_url and order.receipt_url.lower().endswith(".pdf")
            ),
        )

    if claim.event_type == "order.status.changed":
        return await _render_order_status(session, claim)

    if claim.event_type == "order.admin_card.status_updated":
        if claim.payload_id is None:
            return _Skip("event_data_missing")
        history = await session.get(
            OrderStatusHistory, int(claim.payload_id), populate_existing=True
        )
        if history is None:
            return _Skip("event_data_missing")
        return await _render_admin_order_card(
            session,
            claim,
            actor_id=history.changed_by_admin_id,
            status_history=history,
        )

    if claim.event_type in {
        "order.gateway_payment.confirmed",
        "order.manual_payment.accepted",
    }:
        if claim.payload_id is None or claim.recipient_user_id is None:
            return _Skip("event_data_missing")
        order = await order_repository.get_by_id(session, int(claim.aggregate_id))
        user = await user_repository.get_by_id(session, claim.recipient_user_id)
        if order is None or user is None or order.user_id != user.id:
            return _Skip("recipient_missing")
        if user.is_blocked:
            return _Skip("recipient_blocked")
        if claim.event_type == "order.manual_payment.accepted":
            audit = await session.get(AdminAuditEvent, int(claim.payload_id))
            if (
                audit is None
                or audit.actor_admin_id is None
                or not await _actor_is_live(session, audit.actor_admin_id)
            ):
                return _Skip("actor_inactive")
        else:
            payment = await session.get(PaymentTransaction, int(claim.payload_id))
            if payment is None or payment.order_id != order.id:
                return _Skip("event_data_missing")
        text = translate(
            user.language,
            "orders.payment_confirmed_notification",
            order_number=order.order_number,
        )
        return _Delivery("send_message", user.telegram_id, text)

    if claim.event_type in {
        "order.admin_card.gateway_payment_updated",
        "order.admin_card.manual_payment_updated",
    }:
        if claim.event_type == "order.admin_card.manual_payment_updated":
            audit = await session.get(AdminAuditEvent, int(claim.payload_id or 0))
            if audit is None:
                return _Skip("event_data_missing")
            actor_id = audit.actor_admin_id
        else:
            payment = await session.get(PaymentTransaction, int(claim.payload_id or 0))
            if payment is None or payment.order_id != int(claim.aggregate_id):
                return _Skip("event_data_missing")
            actor_id = None
        return await _render_admin_order_card(
            session,
            claim,
            actor_id=actor_id,
            payment_review=claim.event_type == "order.admin_card.manual_payment_updated",
        )

    if claim.event_type in {"admin.team.changed", "store.settings.updated"}:
        if claim.payload_id is None or claim.recipient_admin_id is None:
            return _Skip("event_data_missing")
        admin, error = await _fresh_admin(session, claim.recipient_admin_id)
        if admin is None:
            return _Skip(error or "admin_inactive")
        audit = await session.get(AdminAuditEvent, int(claim.payload_id))
        if (
            audit is None
            or audit.actor_admin_id is None
            or not await _actor_is_live(session, audit.actor_admin_id)
        ):
            return _Skip("actor_inactive")
        translator = await translator_for_admin(session, admin.telegram_id)
        key = (
            "admin.outbox_team_changed"
            if claim.event_type == "admin.team.changed"
            else "admin.outbox_settings_updated"
        )
        return _Delivery("send_message", admin.telegram_id, translator(key))

    if claim.event_type in {"traffic_source.created", "traffic_source.updated"}:
        if claim.payload_id is None or claim.recipient_admin_id is None:
            return _Skip("event_data_missing")
        admin, error = await _fresh_admin(session, claim.recipient_admin_id)
        if admin is None:
            return _Skip(error or "admin_inactive")
        source = await session.get(TrafficSource, int(claim.aggregate_id))
        audit = await session.get(AdminAuditEvent, int(claim.payload_id))
        if (
            source is None
            or audit is None
            or audit.actor_admin_id is None
            or not await _actor_is_live(session, audit.actor_admin_id)
        ):
            return _Skip("actor_inactive")
        translator = await translator_for_admin(session, admin.telegram_id)
        key = (
            "admin.outbox_source_created"
            if claim.event_type == "traffic_source.created"
            else "admin.outbox_source_updated"
        )
        text = translator(key, source_id=source.id)
        return _Delivery("send_message", admin.telegram_id, text)

    if claim.event_type == "system.deploy":
        if claim.recipient_admin_id is None:
            return _Skip("recipient_missing")
        admin, error = await _fresh_admin(session, claim.recipient_admin_id)
        if admin is None:
            return _Skip(error or "admin_inactive")
        translator = await translator_for_admin(session, admin.telegram_id)
        return _Delivery(
            "send_message", admin.telegram_id, translator("admin.deploy_notification")
        )

    return _Skip("unknown_event_type")


async def _save_admin_message_id(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    order_id: int,
    telegram_id: int,
    message_id: int,
) -> None:
    async with session_maker() as session, session.begin():
        order = await order_repository.get_by_id_for_update(session, order_id)
        if order is None:
            return
        await order_repository.set_admin_message_id(session, order, telegram_id, message_id)


async def _send_delivery(
    bot: Bot,
    session_maker: async_sessionmaker[AsyncSession],
    redis: Redis,
    delivery: _Delivery,
) -> None:
    async def pace() -> None:
        await acquire_telegram_slot(redis, bot_id=bot.id, now=datetime.now(UTC))

    if delivery.operation == "edit_order":
        await pace()
        await bot.edit_message_text(
            text=delivery.text,
            chat_id=delivery.chat_id,
            message_id=delivery.message_id,
            reply_markup=delivery.reply_markup,
        )
        return

    await pace()
    sent = await bot.send_message(
        delivery.chat_id,
        delivery.text,
        reply_markup=delivery.reply_markup,
        parse_mode=delivery.parse_mode,
    )
    if delivery.operation != "send_order":
        return
    assert delivery.order_id is not None
    await _save_admin_message_id(
        session_maker,
        order_id=delivery.order_id,
        telegram_id=delivery.chat_id,
        message_id=sent.message_id,
    )
    if delivery.receipt_file_id:
        await pace()
        if delivery.receipt_is_pdf:
            await bot.send_document(
                delivery.chat_id,
                delivery.receipt_file_id,
                reply_to_message_id=sent.message_id,
            )
        else:
            await bot.send_photo(
                delivery.chat_id,
                delivery.receipt_file_id,
                reply_to_message_id=sent.message_id,
            )


async def _process_claim(
    bot: Bot,
    session_maker: async_sessionmaker[AsyncSession],
    redis: Redis,
    claim: OutboxClaim,
) -> None:
    try:
        async with session_maker() as session, session.begin():
            delivery = await _render_event(session, claim)
        if isinstance(delivery, _Skip):
            async with session_maker() as session, session.begin():
                await _fail_outbox(
                    session,
                    event_id=claim.event_id,
                    lease_token=claim.lease_token,
                    safe_error=delivery.error_code,
                )
            log.info(
                "outbox_event_skipped", event_id=claim.event_id, error_code=delivery.error_code
            )
            return
        await _send_delivery(bot, session_maker, redis, delivery)
    except TelegramRetryAfter as exc:
        async with session_maker() as session, session.begin():
            await retry_outbox(
                session,
                event_id=claim.event_id,
                lease_token=claim.lease_token,
                available_at=datetime.now(UTC) + timedelta(seconds=float(exc.retry_after)),
                safe_error="telegram_retry_after",
            )
        log.warning(
            "outbox_delivery_retry", event_id=claim.event_id, error_code="telegram_retry_after"
        )
        return
    except TelegramForbiddenError:
        async with session_maker() as session, session.begin():
            if claim.recipient_user_id is not None:
                await session.execute(
                    update(User)
                    .where(User.id == claim.recipient_user_id)
                    .values(is_blocked=True)
                )
            await _fail_outbox(
                session,
                event_id=claim.event_id,
                lease_token=claim.lease_token,
                safe_error="telegram_forbidden",
            )
        log.warning(
            "outbox_delivery_failed", event_id=claim.event_id, error_code="telegram_forbidden"
        )
        return
    except TelegramBadRequest:
        async with session_maker() as session, session.begin():
            await _fail_outbox(
                session,
                event_id=claim.event_id,
                lease_token=claim.lease_token,
                safe_error="telegram_bad_request",
            )
        log.warning(
            "outbox_delivery_failed",
            event_id=claim.event_id,
            error_code="telegram_bad_request",
        )
        return
    except Exception:
        async with session_maker() as session, session.begin():
            await retry_outbox(
                session,
                event_id=claim.event_id,
                lease_token=claim.lease_token,
                available_at=datetime.now(UTC)
                + timedelta(seconds=min(300, 2 ** min(claim.attempts, 8))),
                safe_error="delivery_error",
            )
        log.warning(
            "outbox_delivery_retry", event_id=claim.event_id, error_code="delivery_error"
        )
        return

    async with session_maker() as session, session.begin():
        acknowledged = await ack_outbox(
            session,
            event_id=claim.event_id,
            lease_token=claim.lease_token,
            sent_at=datetime.now(UTC),
        )
    if acknowledged:
        log.info("outbox_event_sent", event_id=claim.event_id)


async def _wait_or_stop(stop: asyncio.Event) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)


async def run_outbox_worker(
    bot: Bot,
    session_maker: async_sessionmaker[AsyncSession],
    redis: Redis,
    stop: asyncio.Event,
) -> None:
    """Claim durable rows until stopped; network sends never hold database locks."""
    worker_id = f"outbox-{os.getpid()}-{uuid4().hex}"
    while not stop.is_set():
        try:
            now = datetime.now(UTC)
            async with session_maker() as session, session.begin():
                claims = await claim_outbox_batch(
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
                await _process_claim(bot, session_maker, redis, claim)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Do not leak SQL or Redis exception details, which may contain connection data.
            log.error("outbox_worker_iteration_failed", error_code="delivery_error")
            await _wait_or_stop(stop)

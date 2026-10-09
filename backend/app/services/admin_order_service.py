from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import ClassVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AdminOrderMessageValidationError,
    IdempotencyConflictError,
    OrderNotFoundError,
)
from app.db.models.admin import Admin
from app.db.models.admin_audit_event import AdminAuditEvent
from app.db.models.admin_order_message import AdminOrderMessage
from app.db.models.enums import AdminRole, OrderStatus
from app.db.models.order import Order
from app.db.models.order_status_history import OrderStatusHistory
from app.db.models.payment_transaction import PaymentTransaction
from app.db.repositories import order_repository
from app.services.admin_actor_service import load_live_admin
from app.services.admin_audit_service import write_audit_event
from app.services.common import Page
from app.services.notification_outbox_service import enqueue_outbox_event

ORDER_ADMIN_ROLES = frozenset({AdminRole.SUPERADMIN, AdminRole.MANAGER, AdminRole.OPERATOR})
ADMIN_ORDER_MESSAGE_QUEUED_EVENT = "admin.order_message.queued"


def validate_admin_order_message_text(text: str) -> None:
    if not isinstance(text, str) or not 1 <= len(text) <= 4096 or not text.strip():
        raise AdminOrderMessageValidationError(
            "Order messages must contain 1 to 4096 non-blank characters."
        )


@dataclass(frozen=True)
class AdminOrderMessageQueuedEvent:
    """ID-only outbox DTO consumed by Task 9's Telegram dispatcher."""

    event_type: ClassVar[str] = ADMIN_ORDER_MESSAGE_QUEUED_EVENT
    order_id: int
    recipient_user_id: int
    message_id: int


async def load_order_admin(
    session: AsyncSession, *, admin_id: int, lock: bool = False
) -> Admin:
    return await load_live_admin(
        session,
        admin_id=admin_id,
        allowed_roles=ORDER_ADMIN_ROLES,
        lock=lock,
    )


@dataclass(frozen=True)
class AdminOrderDetail:
    order: Order
    status_history: Sequence[OrderStatusHistory]
    payment_history: Sequence[PaymentTransaction]
    payment_review_history: Sequence[AdminAuditEvent]


async def list_admin_orders(
    session: AsyncSession,
    *,
    admin_id: int,
    status: OrderStatus | None,
    query: str | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    limit: int,
) -> Page[Order]:
    await load_live_admin(session, admin_id=admin_id, allowed_roles=ORDER_ADMIN_ROLES)
    items, total = await order_repository.list_for_admin(
        session,
        status=status,
        query=query,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )
    return Page(items=items, total=total, page=page, limit=limit)


async def get_admin_order(
    session: AsyncSession, *, admin_id: int, order_id: int
) -> AdminOrderDetail:
    await load_live_admin(session, admin_id=admin_id, allowed_roles=ORDER_ADMIN_ROLES)
    order = await order_repository.get_by_id(session, order_id)
    if order is None:
        raise OrderNotFoundError(f"Order {order_id} not found")

    status_history = sorted(
        order.status_history,
        key=lambda event: (event.created_at, event.id),
    )
    payment_history = list(
        (
            await session.scalars(
                select(PaymentTransaction)
                .where(PaymentTransaction.order_id == order.id)
                .order_by(PaymentTransaction.created_at, PaymentTransaction.id)
            )
        ).all()
    )
    payment_review_history = list(
        (
            await session.scalars(
                select(AdminAuditEvent)
                .where(
                    AdminAuditEvent.resource_type == "payment",
                    AdminAuditEvent.resource_id == str(order.id),
                    AdminAuditEvent.action == "manual_card_transfer_payment_accepted",
                )
                .order_by(AdminAuditEvent.created_at, AdminAuditEvent.id)
            )
        ).all()
    )
    return AdminOrderDetail(
        order=order,
        status_history=status_history,
        payment_history=payment_history,
        payment_review_history=payment_review_history,
    )


async def queue_order_message(
    session: AsyncSession,
    *,
    admin_id: int,
    order_id: int,
    text: str,
    idempotency_key: UUID,
) -> AdminOrderMessage:
    actor = await load_live_admin(
        session,
        admin_id=admin_id,
        allowed_roles=ORDER_ADMIN_ROLES,
        lock=True,
    )
    validate_admin_order_message_text(text)

    order = await order_repository.get_by_id_for_update(session, order_id)
    if order is None:
        raise OrderNotFoundError(f"Order {order_id} not found")

    message_id = await session.scalar(
        insert(AdminOrderMessage)
        .values(
            order_id=order.id,
            admin_id=actor.id,
            text=text,
            idempotency_key=idempotency_key,
        )
        .on_conflict_do_nothing(
            index_elements=[
                AdminOrderMessage.admin_id,
                AdminOrderMessage.order_id,
                AdminOrderMessage.idempotency_key,
            ]
        )
        .returning(AdminOrderMessage.id)
    )
    if message_id is None:
        existing = await session.scalar(
            select(AdminOrderMessage).where(
                AdminOrderMessage.admin_id == actor.id,
                AdminOrderMessage.order_id == order.id,
                AdminOrderMessage.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise RuntimeError("Idempotent order message could not be reloaded")
        if existing.text != text:
            raise IdempotencyConflictError(
                "This idempotency key was already used for a different order message."
            )
        return existing

    message = await session.get(AdminOrderMessage, message_id)
    if message is None:
        raise RuntimeError("Queued order message could not be reloaded")

    event = AdminOrderMessageQueuedEvent(
        order_id=order.id,
        recipient_user_id=order.user_id,
        message_id=message.id,
    )
    await enqueue_outbox_event(
        session,
        event_type=event.event_type,
        aggregate_id=event.order_id,
        dedupe_key=f"admin-order-message:{message.id}",
        recipient_user_id=event.recipient_user_id,
        payload_id=event.message_id,
    )
    await write_audit_event(
        session,
        admin_id=actor.id,
        action="order_message_queued",
        entity="admin_order_message",
        entity_id=message.id,
        request_id=f"order-msg:{message.id}",
        before=None,
        after={
            "message_id": message.id,
            "text_length": len(text),
            "text_sha256": sha256(text.encode("utf-8")).hexdigest(),
        },
    )
    return message

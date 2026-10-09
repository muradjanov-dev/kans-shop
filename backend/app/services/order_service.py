from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    OrderAlreadyProcessedError,
    OrderNotFoundError,
)
from app.db.models.admin import Admin
from app.db.models.enums import (
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentStatus,
    PaymentTxState,
)
from app.db.models.order import Order
from app.db.models.payment_transaction import PaymentTransaction
from app.db.models.product import Product
from app.db.repositories import (
    order_repository,
    product_repository,
    setting_repository,
)
from app.services.notification_outbox_service import enqueue_outbox_event
from app.services.purchase_service import CheckoutCommand, submit_checkout

# Statuses an admin/operator may move an order into from its current status. `cancelled` is
# reachable from any non-terminal status via cancel_order(), not through this map.
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW: {OrderStatus.CONFIRMED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING},
    OrderStatus.PREPARING: {OrderStatus.DELIVERING, OrderStatus.COMPLETED},
    OrderStatus.DELIVERING: {OrderStatus.COMPLETED},
}


async def calculate_delivery_fee(
    session: AsyncSession, order_type: OrderType, subtotal: Decimal
) -> Decimal:
    if order_type != OrderType.DELIVERY:
        return Decimal("0")
    free_from = Decimal(
        str(await setting_repository.get_value(session, "free_delivery_from", 0))
    )
    if free_from and subtotal >= free_from:
        return Decimal("0")
    fee = await setting_repository.get_value(session, "delivery_fee", 0)
    return Decimal(str(fee))


async def checkout(
    session: AsyncSession,
    *,
    user_id: int,
    order_type: OrderType,
    customer_name: str,
    customer_phone: str,
    payment_method: PaymentMethod = PaymentMethod.CASH,
    address: str | None = None,
    address_comment: str | None = None,
    latitude: Decimal | None = None,
    longitude: Decimal | None = None,
    comment: str | None = None,
    source: str = "bot",
    lang: str = "uz",
) -> Order:
    result = await submit_checkout(
        session,
        user_id=user_id,
        command=CheckoutCommand(
            order_type=order_type,
            customer_name=customer_name,
            customer_phone=customer_phone,
            payment_method=payment_method,
            address=address,
            address_comment=address_comment,
            latitude=latitude,
            longitude=longitude,
            comment=comment,
        ),
        checkout_key=None,
        expected_quote=None,
        expected_total=None,
        source=source,
        lang=lang,
    )
    return result.order


async def attach_receipt(
    session: AsyncSession, order: Order, *, file_id: str | None, url: str | None
) -> Order:
    order.receipt_file_id = file_id
    order.receipt_url = url
    order.payment_status = PaymentStatus.RECEIPT_UPLOADED
    await session.flush()
    return order


async def mark_paid(session: AsyncSession, order: Order) -> Order:
    """Called once a gateway (Click/Payme/Paynet) confirms payment. Unlike card_transfer, this
    is a server-verified confirmation, so the order is auto-advanced past manual admin review.
    """
    if order.payment_status == PaymentStatus.PAID:
        return order

    order.payment_status = PaymentStatus.PAID
    if order.status == OrderStatus.NEW:
        order = await advance_status(session, order, OrderStatus.CONFIRMED)
    await session.flush()
    payment_id = await session.scalar(
        select(PaymentTransaction.id)
        .where(
            PaymentTransaction.order_id == order.id,
            PaymentTransaction.state == PaymentTxState.PAID,
        )
        .order_by(PaymentTransaction.id.desc())
        .limit(1)
    )
    if payment_id is not None:
        await _enqueue_payment_notifications(
            session,
            order,
            event_type="order.gateway_payment.confirmed",
            admin_event_type="order.admin_card.gateway_payment_updated",
            payload_id=payment_id,
            dedupe_key=f"order-gateway-payment:{payment_id}",
        )
    return order


async def _enqueue_order_card_updates(
    session: AsyncSession,
    order: Order,
    *,
    event_type: str,
    payload_id: int,
    dedupe_key: str,
) -> None:
    try:
        telegram_ids = [int(value) for value in order.admin_message_ids]
    except (TypeError, ValueError):
        telegram_ids = []
    if not telegram_ids:
        return
    recipients = await session.execute(
        select(Admin.id, Admin.telegram_id)
        .where(
            Admin.telegram_id.in_(telegram_ids),
            Admin.is_active.is_(True),
            Admin.notifications_enabled.is_(True),
        )
        .order_by(Admin.id)
    )
    for admin_id, _telegram_id in recipients:
        await enqueue_outbox_event(
            session,
            event_type=event_type,
            aggregate_id=order.id,
            payload_id=payload_id,
            recipient_admin_id=admin_id,
            dedupe_key=f"{dedupe_key}:admin:{admin_id}",
        )


async def _enqueue_payment_notifications(
    session: AsyncSession,
    order: Order,
    *,
    event_type: str,
    admin_event_type: str,
    payload_id: int,
    dedupe_key: str,
) -> None:
    await enqueue_outbox_event(
        session,
        event_type=event_type,
        aggregate_id=order.id,
        payload_id=payload_id,
        recipient_user_id=order.user_id,
        dedupe_key=f"{dedupe_key}:user:{order.user_id}",
    )
    await _enqueue_order_card_updates(
        session,
        order,
        event_type=admin_event_type,
        payload_id=payload_id,
        dedupe_key=dedupe_key,
    )


async def enqueue_manual_payment_notification(
    session: AsyncSession, order: Order, *, audit_event_id: int
) -> None:
    """Queue the manual-review customer message and existing admin-card refreshes atomically."""
    await _enqueue_payment_notifications(
        session,
        order,
        event_type="order.manual_payment.accepted",
        admin_event_type="order.admin_card.manual_payment_updated",
        payload_id=audit_event_id,
        dedupe_key=f"order-manual-payment:{audit_event_id}",
    )


@dataclass(frozen=True)
class LotLink:
    product_name: str
    url: str


async def lot_links(session: AsyncSession, order: Order) -> tuple[list[LotLink], list[str]]:
    """Tender checkout: the lot page for each ordered product. Returns (links, missing) —
    `missing` names the items whose product has no `lot_url` set (or whose product row is
    gone), so the customer is told which ones an admin still has to send a link for."""
    product_ids = [item.product_id for item in order.items if item.product_id is not None]
    products = {}
    if product_ids:
        rows = await session.scalars(select(Product).where(Product.id.in_(product_ids)))
        products = {product.id: product for product in rows}

    links: list[LotLink] = []
    missing: list[str] = []
    for item in order.items:
        product = products.get(item.product_id) if item.product_id is not None else None
        if product is not None and product.lot_url:
            links.append(LotLink(item.product_name_snapshot, product.lot_url))
        else:
            missing.append(item.product_name_snapshot)
    return links, missing


async def get_order(session: AsyncSession, order_id: int) -> Order:
    order = await order_repository.get_by_id(session, order_id)
    if order is None:
        raise OrderNotFoundError(f"Order {order_id} not found")
    return order


async def confirm_order(session: AsyncSession, order: Order, *, admin_id: int) -> Order:
    return await advance_status(
        session, order, OrderStatus.CONFIRMED, admin_id=admin_id, _set_confirmed_at=True
    )


async def advance_status(
    session: AsyncSession,
    order: Order,
    new_status: OrderStatus,
    *,
    admin_id: int | None = None,
    comment: str | None = None,
    _set_confirmed_at: bool = False,
) -> Order:
    locked_order = await order_repository.get_by_id_for_update(session, order.id)
    if locked_order is None:
        raise OrderNotFoundError(f"Order {order.id} not found")
    order = locked_order
    allowed = ALLOWED_TRANSITIONS.get(order.status, set())
    if new_status not in allowed:
        raise OrderAlreadyProcessedError(
            f"Cannot move order {order.order_number} from {order.status} to {new_status}"
        )

    old_status = order.status
    order.status = new_status
    order.processed_by_admin_id = (
        admin_id if admin_id is not None else order.processed_by_admin_id
    )
    if _set_confirmed_at or new_status == OrderStatus.CONFIRMED:
        order.confirmed_at = datetime.now(UTC)
    if new_status == OrderStatus.COMPLETED:
        order.completed_at = datetime.now(UTC)
    history = await order_repository.add_status_history(
        session,
        order,
        from_status=old_status,
        to_status=new_status,
        changed_by_admin_id=admin_id,
        comment=comment,
    )
    await session.flush()
    if admin_id is not None:
        await enqueue_outbox_event(
            session,
            event_type="order.status.changed",
            aggregate_id=order.id,
            payload_id=history.id,
            recipient_user_id=order.user_id,
            dedupe_key=f"order-status:{history.id}:user:{order.user_id}",
        )
        await _enqueue_order_card_updates(
            session,
            order,
            event_type="order.admin_card.status_updated",
            payload_id=history.id,
            dedupe_key=f"order-status:{history.id}",
        )
    return order


async def cancel_order(
    session: AsyncSession, order: Order, *, admin_id: int | None, reason: str
) -> Order:
    locked_order = await order_repository.get_by_id_for_update(session, order.id)
    if locked_order is None:
        raise OrderNotFoundError(f"Order {order.id} not found")
    order = locked_order
    if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
        raise OrderAlreadyProcessedError(
            f"Order {order.order_number} is already {order.status}"
        )

    old_status = order.status
    order.status = OrderStatus.CANCELLED
    order.cancel_reason = reason
    order.cancelled_at = datetime.now(UTC)
    order.processed_by_admin_id = (
        admin_id if admin_id is not None else order.processed_by_admin_id
    )

    for item in sorted(order.items, key=lambda current: current.product_id or 0):
        if item.product_id is not None:
            product = await product_repository.get_by_id(
                session, item.product_id, for_update=True
            )
            if product is not None:
                await product_repository.adjust_stock(session, product, item.quantity)
                await product_repository.increment_sold(session, product, -item.quantity)

    history = await order_repository.add_status_history(
        session,
        order,
        from_status=old_status,
        to_status=OrderStatus.CANCELLED,
        changed_by_admin_id=admin_id,
        comment=reason,
    )
    await session.flush()
    await enqueue_outbox_event(
        session,
        event_type="order.status.changed",
        aggregate_id=order.id,
        payload_id=history.id,
        recipient_user_id=order.user_id,
        dedupe_key=f"order-status:{history.id}:user:{order.user_id}",
    )
    await _enqueue_order_card_updates(
        session,
        order,
        event_type="order.admin_card.status_updated",
        payload_id=history.id,
        dedupe_key=f"order-status:{history.id}",
    )
    return order


async def set_admin_message_id(
    session: AsyncSession, order: Order, admin_telegram_id: int, message_id: int
) -> None:
    await order_repository.set_admin_message_id(session, order, admin_telegram_id, message_id)

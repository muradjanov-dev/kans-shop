from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    OrderNotFoundError,
    PaymentAcceptanceUnavailableError,
    ReceiptVersionConflictError,
)
from app.db.models.enums import AdminRole, OrderStatus, PaymentMethod, PaymentStatus
from app.db.models.order import Order
from app.db.repositories import order_repository
from app.services.admin_actor_service import load_live_admin
from app.services.admin_audit_service import write_audit_event

_ORDER_ADMIN_ROLES = frozenset({AdminRole.SUPERADMIN, AdminRole.MANAGER, AdminRole.OPERATOR})
_NEW_ACCEPTANCE_IDS_KEY = "app.services.manual_payment.new_acceptance_order_ids"


def consume_new_acceptance_event(session: AsyncSession, order_id: int) -> bool:
    """Return and clear whether this transaction made the payment transition."""
    order_ids: set[int] = session.info.get(_NEW_ACCEPTANCE_IDS_KEY, set())
    if order_id not in order_ids:
        return False
    order_ids.discard(order_id)
    return True


async def accept_card_transfer_payment(
    session: AsyncSession,
    *,
    order_id: int,
    admin_id: int,
    expected_receipt_version: int,
) -> Order:
    admin = await load_live_admin(
        session,
        admin_id=admin_id,
        allowed_roles=_ORDER_ADMIN_ROLES,
        lock=True,
    )
    order = await order_repository.get_by_id_for_update(session, order_id)
    if order is None:
        raise OrderNotFoundError(f"Order {order_id} not found")

    current_version = order.receipt_version or 0
    if expected_receipt_version != current_version:
        raise ReceiptVersionConflictError(
            "The receipt was replaced. Review the current receipt before accepting payment.",
            details={
                "expected_receipt_version": expected_receipt_version,
                "current_receipt_version": current_version,
            },
        )

    has_evidence = bool(order.receipt_storage_key or order.receipt_file_id)
    if (
        order.payment_method == PaymentMethod.CARD_TRANSFER
        and order.payment_status == PaymentStatus.PAID
        and order.payment_reviewed_by_admin_id is not None
        and order.payment_reviewed_at is not None
        and has_evidence
    ):
        return order

    if (
        order.payment_method != PaymentMethod.CARD_TRANSFER
        or order.payment_status != PaymentStatus.RECEIPT_UPLOADED
        or not has_evidence
        or order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED)
    ):
        raise PaymentAcceptanceUnavailableError(
            "This order does not have an eligible card-transfer receipt."
        )

    before: dict[str, object] = {
        "order_status": order.status,
        "payment_status": order.payment_status,
        "receipt_version": current_version,
    }
    reviewed_at = datetime.now(UTC)
    order.payment_status = PaymentStatus.PAID
    order.payment_reviewed_by_admin_id = admin.id
    order.payment_reviewed_at = reviewed_at
    await session.flush()

    after: dict[str, object] = {
        "order_status": order.status,
        "payment_status": order.payment_status,
        "receipt_version": current_version,
        "payment_reviewed_by_admin_id": admin.id,
        "payment_reviewed_at": reviewed_at,
    }
    await write_audit_event(
        session,
        admin_id=admin.id,
        action="manual_card_transfer_payment_accepted",
        entity="payment",
        entity_id=order.id,
        request_id=f"payment-accept:{order.id}:{current_version}",
        before=before,
        after=after,
    )
    session.info.setdefault(_NEW_ACCEPTANCE_IDS_KEY, set()).add(order.id)
    return order

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ForbiddenError,
    InvalidFileError,
    OrderAlreadyProcessedError,
    OrderNotFoundError,
)
from app.core.uploads import validate_receipt_content
from app.db.models.enums import AdminRole, OrderStatus, PaymentMethod, PaymentStatus
from app.db.models.order import Order
from app.db.repositories import order_repository
from app.services.admin_actor_service import load_live_admin
from app.services.receipt_storage import PrivateReceiptStorage


@dataclass(frozen=True)
class ReceiptRead:
    path: Path
    content_type: str


def has_private_receipt_evidence(order: Order) -> bool:
    """Whether this order has an admin-reviewable receipt object or Telegram file."""
    return bool(order.receipt_storage_key or order.receipt_file_id)


_ORDER_ADMIN_ROLES = frozenset({AdminRole.SUPERADMIN, AdminRole.MANAGER, AdminRole.OPERATOR})


async def attach_card_transfer_receipt(
    session: AsyncSession,
    storage: PrivateReceiptStorage,
    *,
    order_id: int,
    owner_user_id: int,
    content: bytes,
    declared_content_type: str,
    telegram_file_id: str | None = None,
) -> Order:
    order = await order_repository.get_by_id_for_update(session, order_id)
    if order is None:
        raise OrderNotFoundError(f"Order {order_id} not found")
    _validate_receipt_upload_order(order, owner_user_id=owner_user_id)

    validate_receipt_content(content, declared_content_type)
    stored = storage.store(content, declared_content_type)

    # New objects are immutable. The previous object remains available until a later cleanup
    # process can prove that no committed order references it.
    order.receipt_storage_key = stored.storage_key
    order.receipt_content_type = stored.content_type
    order.receipt_file_id = telegram_file_id
    order.receipt_url = None
    order.receipt_version = (order.receipt_version or 0) + 1
    order.payment_status = PaymentStatus.RECEIPT_UPLOADED
    await session.flush()
    return order


def _validate_receipt_upload_order(order: Order, *, owner_user_id: int) -> None:
    if order.user_id != owner_user_id:
        raise ForbiddenError("Not your order")
    if order.payment_method != PaymentMethod.CARD_TRANSFER:
        raise ForbiddenError("Receipts are only accepted for card-transfer orders")
    if order.status in (
        OrderStatus.COMPLETED,
        OrderStatus.CANCELLED,
    ) or order.payment_status not in (PaymentStatus.PENDING, PaymentStatus.RECEIPT_UPLOADED):
        raise OrderAlreadyProcessedError("This order can no longer accept a receipt")


async def get_receipt_upload_order(
    session: AsyncSession, *, order_id: int, owner_user_id: int
) -> Order:
    """Read and validate a receipt redirect target; the upload repeats this check while locked."""
    order = await order_repository.get_by_id(session, order_id)
    if order is None:
        raise OrderNotFoundError(f"Order {order_id} not found")
    _validate_receipt_upload_order(order, owner_user_id=owner_user_id)
    return order


async def open_order_receipt(
    session: AsyncSession,
    storage: PrivateReceiptStorage,
    *,
    order_id: int,
    user_id: int,
    admin_id: int | None = None,
) -> ReceiptRead:
    order = await order_repository.get_by_id(session, order_id)
    if order is None:
        raise OrderNotFoundError(f"Order {order_id} not found")

    if admin_id is not None:
        await load_live_admin(
            session,
            admin_id=admin_id,
            allowed_roles=_ORDER_ADMIN_ROLES,
        )
    elif order.user_id != user_id:
        raise ForbiddenError("Not your order")

    if not order.receipt_storage_key or not order.receipt_content_type:
        raise OrderNotFoundError(f"Receipt for order {order_id} not found")
    try:
        path = storage.resolve(order.receipt_storage_key)
    except (ValueError, FileNotFoundError) as exc:
        raise InvalidFileError("Receipt object is unavailable") from exc
    return ReceiptRead(path=path, content_type=order.receipt_content_type)

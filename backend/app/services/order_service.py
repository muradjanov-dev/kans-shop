from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    CartEmptyError,
    MinOrderAmountError,
    OrderAlreadyProcessedError,
    OrderNotFoundError,
    OutOfStockError,
)
from app.db.models.cart import Cart
from app.db.models.enums import OrderStatus, OrderType, PaymentMethod, PaymentStatus
from app.db.models.order import Order
from app.db.models.product import Product
from app.db.repositories import (
    cart_repository,
    order_repository,
    product_repository,
    setting_repository,
)

# Statuses an admin/operator may move an order into from its current status. `cancelled` is
# reachable from any non-terminal status via cancel_order(), not through this map.
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW: {OrderStatus.CONFIRMED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING},
    OrderStatus.PREPARING: {OrderStatus.DELIVERING, OrderStatus.COMPLETED},
    OrderStatus.DELIVERING: {OrderStatus.COMPLETED},
}


async def _lock_and_validate_stock(
    session: AsyncSession, cart: Cart
) -> list[tuple[Product, int]]:
    """Row-locks every product in the cart (ordered by id to avoid deadlocks with concurrent
    checkouts) and re-validates stock against the live row, inside the caller's transaction."""
    locked: list[tuple[Product, int]] = []
    for item in sorted(cart.items, key=lambda i: i.product_id):
        product = await product_repository.get_by_id(session, item.product_id, for_update=True)
        if product is None or not product.is_active or product.stock_qty < item.quantity:
            available = product.stock_qty if product else 0
            raise OutOfStockError(
                f"Not enough stock for product {item.product_id}",
                details={"product_id": item.product_id, "available": available},
            )
        locked.append((product, item.quantity))
    return locked


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
    cart = await cart_repository.get_active_cart(session, user_id)
    if cart is None or not cart.items:
        raise CartEmptyError("Cart is empty")

    locked_products = await _lock_and_validate_stock(session, cart)
    subtotal = sum((p.price * qty for p, qty in locked_products), Decimal("0"))

    # Preorder is a manual "a manager will call you back" flow; the minimum-order-amount gate
    # is a self-checkout guard and doesn't apply to it (see docs/ASSUMPTIONS.md).
    if order_type != OrderType.PREORDER:
        min_amount = Decimal(
            str(await setting_repository.get_value(session, "min_order_amount", 0))
        )
        if subtotal < min_amount:
            raise MinOrderAmountError(
                f"Subtotal {subtotal} below minimum {min_amount}",
                details={"subtotal": str(subtotal), "min_amount": str(min_amount)},
            )

    delivery_fee = await calculate_delivery_fee(session, order_type, subtotal)
    discount = Decimal("0")
    total = subtotal + delivery_fee - discount

    order_number = await order_repository.next_order_number(session)
    order = await order_repository.create(
        session,
        order_number=order_number,
        user_id=user_id,
        order_type=order_type,
        customer_name=customer_name,
        customer_phone=customer_phone,
        address=address if order_type == OrderType.DELIVERY else None,
        address_comment=address_comment if order_type == OrderType.DELIVERY else None,
        latitude=latitude if order_type == OrderType.DELIVERY else None,
        longitude=longitude if order_type == OrderType.DELIVERY else None,
        comment=comment,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        discount=discount,
        total=total,
        payment_method=payment_method,
        source=source,
    )

    for product, quantity in locked_products:
        name_snapshot = product.name_uz if lang == "uz" else product.name_ru
        await order_repository.add_item(
            session,
            order,
            product_id=product.id,
            product_name_snapshot=name_snapshot,
            product_sku_snapshot=product.sku,
            price=product.price,
            quantity=quantity,
        )
        await product_repository.adjust_stock(session, product, -quantity)
        await product_repository.increment_sold(session, product, quantity)

    await order_repository.add_status_history(
        session, order, from_status=None, to_status=OrderStatus.NEW
    )
    await cart_repository.clear(session, cart)

    refreshed = await order_repository.get_by_id(session, order.id)
    assert refreshed is not None
    return refreshed


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
    return order


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
    await order_repository.add_status_history(
        session,
        order,
        from_status=old_status,
        to_status=new_status,
        changed_by_admin_id=admin_id,
        comment=comment,
    )
    await session.flush()
    return order


async def cancel_order(
    session: AsyncSession, order: Order, *, admin_id: int | None, reason: str
) -> Order:
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

    for item in order.items:
        if item.product_id is not None:
            product = await product_repository.get_by_id(
                session, item.product_id, for_update=True
            )
            if product is not None:
                await product_repository.adjust_stock(session, product, item.quantity)
                await product_repository.increment_sold(session, product, -item.quantity)

    await order_repository.add_status_history(
        session,
        order,
        from_status=old_status,
        to_status=OrderStatus.CANCELLED,
        changed_by_admin_id=admin_id,
        comment=reason,
    )
    await session.flush()
    return order


async def set_admin_message_id(
    session: AsyncSession, order: Order, admin_telegram_id: int, message_id: int
) -> None:
    await order_repository.set_admin_message_id(session, order, admin_telegram_id, message_id)

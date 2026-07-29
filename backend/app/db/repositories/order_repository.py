from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.enums import OrderStatus, OrderType, PaymentMethod, PaymentStatus
from app.db.models.order import Order
from app.db.models.order_item import OrderItem
from app.db.models.order_status_history import OrderStatusHistory


async def next_order_number(session: AsyncSession) -> str:
    seq_value = await session.scalar(select(func.nextval("kans_order_seq")))
    return f"KANS-{seq_value:06d}"


def _with_items(stmt):
    return stmt.options(selectinload(Order.items), selectinload(Order.status_history))


async def create(
    session: AsyncSession,
    *,
    order_number: str,
    user_id: int,
    order_type: OrderType,
    customer_name: str,
    customer_phone: str,
    address: str | None,
    address_comment: str | None,
    latitude: Decimal | None,
    longitude: Decimal | None,
    comment: str | None,
    subtotal: Decimal,
    delivery_fee: Decimal,
    discount: Decimal,
    total: Decimal,
    payment_method: PaymentMethod,
    source: str = "bot",
) -> Order:
    order = Order(
        order_number=order_number,
        user_id=user_id,
        order_type=order_type,
        status=OrderStatus.NEW,
        customer_name=customer_name,
        customer_phone=customer_phone,
        address=address,
        address_comment=address_comment,
        latitude=latitude,
        longitude=longitude,
        comment=comment,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        discount=discount,
        total=total,
        payment_method=payment_method,
        payment_status=PaymentStatus.PENDING,
        source=source,
    )
    session.add(order)
    await session.flush()
    return order


async def add_item(
    session: AsyncSession,
    order: Order,
    *,
    product_id: int | None,
    product_name_snapshot: str,
    product_sku_snapshot: str,
    price: Decimal,
    quantity: int,
) -> OrderItem:
    item = OrderItem(
        order_id=order.id,
        product_id=product_id,
        product_name_snapshot=product_name_snapshot,
        product_sku_snapshot=product_sku_snapshot,
        price=price,
        quantity=quantity,
        total=price * quantity,
    )
    session.add(item)
    await session.flush()
    return item


async def get_by_id(session: AsyncSession, order_id: int) -> Order | None:
    stmt = _with_items(select(Order).where(Order.id == order_id))
    return await session.scalar(stmt)


async def get_by_number(session: AsyncSession, order_number: str) -> Order | None:
    stmt = _with_items(select(Order).where(Order.order_number == order_number))
    return await session.scalar(stmt)


async def list_by_user(
    session: AsyncSession, user_id: int, *, page: int = 1, limit: int = 10
) -> tuple[Sequence[Order], int]:
    base = select(Order).where(Order.user_id == user_id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    stmt = _with_items(base).order_by(Order.created_at.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    items = (await session.scalars(stmt)).all()
    return items, total or 0


async def list_for_admin(
    session: AsyncSession,
    *,
    status: OrderStatus | None = None,
    query: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[Sequence[Order], int]:
    base = select(Order)
    if status is not None:
        base = base.where(Order.status == status)
    if query:
        like = f"%{query}%"
        base = base.where(
            (Order.order_number.ilike(like)) | (Order.customer_phone.ilike(like))
        )
    if date_from is not None:
        base = base.where(Order.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        base = base.where(Order.created_at <= datetime.combine(date_to, datetime.max.time()))

    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    stmt = _with_items(base).order_by(Order.created_at.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    items = (await session.scalars(stmt)).all()
    return items, total or 0


async def add_status_history(
    session: AsyncSession,
    order: Order,
    *,
    from_status: OrderStatus | None,
    to_status: OrderStatus,
    changed_by_admin_id: int | None = None,
    comment: str | None = None,
) -> OrderStatusHistory:
    entry = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=to_status,
        changed_by_admin_id=changed_by_admin_id,
        comment=comment,
    )
    session.add(entry)
    await session.flush()
    return entry


async def set_admin_message_id(
    session: AsyncSession, order: Order, admin_telegram_id: int, message_id: int
) -> None:
    order.admin_message_ids = {
        **order.admin_message_ids,
        str(admin_telegram_id): message_id,
    }
    await session.flush()


async def count_since(session: AsyncSession, since: datetime) -> int:
    stmt = select(func.count()).where(Order.created_at >= since)
    return (await session.scalar(stmt)) or 0

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.customer_orders import OrderTimelineEventOut
from app.core.exceptions import OrderNotFoundError
from app.db.models.enums import OrderStatus
from app.db.models.order import Order
from app.db.repositories import order_repository
from app.services.common import Page


async def list_customer_orders(
    session: AsyncSession, user_id: int, page: int = 1, limit: int = 24
) -> Page[Order]:
    orders, total = await order_repository.list_for_customer_history(
        session, user_id, page=page, limit=limit
    )
    return Page(items=orders, total=total, page=page, limit=limit)


async def customer_timeline(
    session: AsyncSession, user_id: int, order_id: int
) -> list[OrderTimelineEventOut]:
    rows = await order_repository.list_customer_timeline_rows(
        session, user_id=user_id, order_id=order_id
    )
    if not rows:
        raise OrderNotFoundError("Order not found")

    now = datetime.now(UTC)
    events: list[OrderTimelineEventOut] = []
    current_status = rows[0][0]
    for _order_status, status, occurred_at, _history_id in rows:
        if status is None or occurred_at is None or occurred_at > now:
            continue
        if status == OrderStatus.CANCELLED:
            events.append(OrderTimelineEventOut(status=status, occurred_at=occurred_at))
            break
        if current_status == OrderStatus.CANCELLED and status == OrderStatus.COMPLETED:
            continue
        events.append(OrderTimelineEventOut(status=status, occurred_at=occurred_at))
    return events

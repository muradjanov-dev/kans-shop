from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import OrderStatus
from app.db.models.order import Order
from app.db.models.order_item import OrderItem
from app.db.models.user import User

PERIOD_DELTAS = {
    "today": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
}


@dataclass(frozen=True)
class TopProduct:
    name: str
    sold: int


@dataclass(frozen=True)
class StatsResult:
    period: str
    since: datetime
    orders_count: int
    revenue: Decimal
    avg_check: Decimal
    new_users: int
    top_products: list[TopProduct]


def period_start(period: str) -> datetime:
    now = datetime.now(UTC)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    return now - PERIOD_DELTAS.get(period, timedelta(days=1))


async def get_stats(session: AsyncSession, period: str) -> StatsResult:
    since = period_start(period)
    non_cancelled = Order.status != OrderStatus.CANCELLED

    orders_count = (
        await session.scalar(
            select(func.count()).select_from(Order).where(Order.created_at >= since)
        )
        or 0
    )

    revenue = await session.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.created_at >= since, non_cancelled
        )
    ) or Decimal("0")

    valid_orders_count = (
        await session.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.created_at >= since, non_cancelled)
        )
        or 0
    )
    avg_check = (Decimal(revenue) / valid_orders_count) if valid_orders_count else Decimal("0")

    new_users = (
        await session.scalar(
            select(func.count()).select_from(User).where(User.created_at >= since)
        )
        or 0
    )

    top_stmt = (
        select(OrderItem.product_name_snapshot, func.sum(OrderItem.quantity).label("qty"))
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.created_at >= since, non_cancelled)
        .group_by(OrderItem.product_name_snapshot)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(10)
    )
    rows = (await session.execute(top_stmt)).all()
    top_products = [TopProduct(name=name, sold=int(qty)) for name, qty in rows]

    return StatsResult(
        period=period,
        since=since,
        orders_count=orders_count,
        revenue=Decimal(revenue),
        avg_check=avg_check,
        new_users=new_users,
        top_products=top_products,
    )

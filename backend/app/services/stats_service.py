from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import AdminRole, OrderStatus, PaymentStatus
from app.db.models.order import Order
from app.db.models.order_item import OrderItem
from app.db.models.user import User
from app.services.admin_actor_service import load_live_admin

StatsPeriod = Literal["today", "week", "month"]
STAT_PERIODS: tuple[StatsPeriod, ...] = ("today", "week", "month")
_TASHKENT = ZoneInfo("Asia/Tashkent")
_STATS_ROLES = frozenset({AdminRole.SUPERADMIN, AdminRole.MANAGER, AdminRole.OPERATOR})


@dataclass(frozen=True)
class TopProduct:
    name: str
    sold: int


@dataclass(frozen=True)
class AdminStats:
    period: str
    since: datetime
    until: datetime
    orders_count: int
    order_value: Decimal
    paid_amount: Decimal
    avg_check: Decimal
    new_users: int
    top_products: list[TopProduct]

    @property
    def revenue(self) -> Decimal:
        """Legacy API name. This is order value, not collected cash."""
        return self.order_value


# Keep bot plugins and callers that imported this name source compatible.
StatsResult = AdminStats


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _validated_period(period: str) -> StatsPeriod:
    if period not in STAT_PERIODS:
        raise ValueError("period must be today, week, or month")
    return period


def period_bounds(period: StatsPeriod, *, now: datetime) -> tuple[datetime, datetime]:
    """Return [start, end] UTC bounds for a reporting window.

    `today` follows the store's local calendar in Tashkent. Week and month are rolling
    windows of exactly seven and thirty 24-hour days.
    """
    end = _utc(now)
    if period == "today":
        local_now = end.astimezone(_TASHKENT)
        start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    elif period == "week":
        start = end - timedelta(days=7)
    elif period == "month":
        start = end - timedelta(days=30)
    else:
        raise ValueError("period must be today, week, or month")
    return start, end


async def _calculate_stats(
    session: AsyncSession, *, period: StatsPeriod, now: datetime
) -> AdminStats:
    since, until = period_bounds(period, now=now)
    within_period = (Order.created_at >= since, Order.created_at <= until)
    non_cancelled = Order.status != OrderStatus.CANCELLED

    orders_count = (
        await session.scalar(select(func.count()).select_from(Order).where(*within_period))
        or 0
    )
    order_value = await session.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(
            *within_period,
            non_cancelled,
        )
    ) or Decimal("0")
    paid_amount = await session.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(
            *within_period,
            non_cancelled,
            Order.payment_status == PaymentStatus.PAID,
        )
    ) or Decimal("0")
    non_cancelled_count = (
        await session.scalar(
            select(func.count()).select_from(Order).where(*within_period, non_cancelled)
        )
        or 0
    )
    order_value = Decimal(order_value)
    paid_amount = Decimal(paid_amount)
    avg_check = order_value / non_cancelled_count if non_cancelled_count else Decimal("0")

    new_users = (
        await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.created_at >= since, User.created_at <= until)
        )
        or 0
    )
    top_stmt = (
        select(OrderItem.product_name_snapshot, func.sum(OrderItem.quantity).label("qty"))
        .join(Order, Order.id == OrderItem.order_id)
        .where(*within_period, non_cancelled)
        .group_by(OrderItem.product_name_snapshot)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(10)
    )
    rows = (await session.execute(top_stmt)).all()
    top_products = [TopProduct(name=name, sold=int(quantity)) for name, quantity in rows]

    return AdminStats(
        period=period,
        since=since,
        until=until,
        orders_count=orders_count,
        order_value=order_value,
        paid_amount=paid_amount,
        avg_check=avg_check,
        new_users=new_users,
        top_products=top_products,
    )


async def get_admin_stats(
    session: AsyncSession,
    *,
    admin_id: int,
    period: str,
    now: datetime,
) -> AdminStats:
    typed_period = _validated_period(period)
    await load_live_admin(session, admin_id=admin_id, allowed_roles=_STATS_ROLES)
    return await _calculate_stats(session, period=typed_period, now=now)


async def export_admin_stats_xlsx(
    session: AsyncSession,
    *,
    admin_id: int,
    period: str,
    now: datetime,
) -> bytes:
    stats = await get_admin_stats(session, admin_id=admin_id, period=period, now=now)
    from app.bot.utils.stats_export import build_stats_workbook

    return build_stats_workbook(stats).getvalue()


def period_start(period: str) -> datetime:
    """Compatibility helper for older internal callers."""
    if period not in STAT_PERIODS:
        period = "today"
    return period_bounds(_validated_period(period), now=datetime.now(UTC))[0]


async def get_stats(session: AsyncSession, period: str) -> StatsResult:
    """Compatibility wrapper for existing service consumers and phase-one tests.

    Admin-facing routes and handlers use `get_admin_stats`, which validates the current
    actor. This wrapper remains only for older internal callers that have no actor context.
    """
    if period not in STAT_PERIODS:
        period = "today"
    return await _calculate_stats(
        session, period=_validated_period(period), now=datetime.now(UTC)
    )

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import OrderStatus
from app.db.models.order import Order
from app.db.models.traffic_source import TrafficSource
from app.db.models.user import User

# Telegram allows A-Z a-z 0-9 _ - in a /start payload; the `src_` prefix eats 4 of its 64
# characters, and codes are lowercased so links stay case-insensitive to type by hand.
CODE_PATTERN = re.compile(r"^[a-z0-9_-]{2,32}$")


@dataclass(frozen=True)
class SourceStats:
    source: TrafficSource
    users_count: int
    orders_count: int
    revenue: Decimal


def normalize_code(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", raw.strip().lower()).strip("-_")
    return slug[:32]


async def get_by_code(session: AsyncSession, code: str) -> TrafficSource | None:
    return await session.scalar(
        select(TrafficSource).where(TrafficSource.code == code.lower())
    )


async def get_by_id(session: AsyncSession, source_id: int) -> TrafficSource | None:
    return await session.get(TrafficSource, source_id)


async def list_all(session: AsyncSession) -> Sequence[TrafficSource]:
    return (
        await session.scalars(select(TrafficSource).order_by(TrafficSource.created_at.desc()))
    ).all()


async def create(session: AsyncSession, *, code: str, name: str) -> TrafficSource:
    source = TrafficSource(code=code.lower(), name=name)
    session.add(source)
    await session.flush()
    return source


async def delete(session: AsyncSession, source: TrafficSource) -> None:
    await session.delete(source)
    await session.flush()


async def increment_clicks(session: AsyncSession, source_id: int) -> None:
    """UPDATE-in-place rather than read-modify-write: two people opening the same link at
    once must not lose a click."""
    await session.execute(
        update(TrafficSource)
        .where(TrafficSource.id == source_id)
        .values(clicks_count=TrafficSource.clicks_count + 1)
    )


async def get_stats(session: AsyncSession, source: TrafficSource) -> SourceStats:
    users_count = (
        await session.scalar(
            select(func.count()).select_from(User).where(User.traffic_source_id == source.id)
        )
        or 0
    )
    orders_count = (
        await session.scalar(
            select(func.count())
            .select_from(Order)
            .join(User, User.id == Order.user_id)
            .where(User.traffic_source_id == source.id)
        )
        or 0
    )
    revenue = await session.scalar(
        select(func.coalesce(func.sum(Order.total), 0))
        .select_from(Order)
        .join(User, User.id == Order.user_id)
        .where(
            User.traffic_source_id == source.id,
            Order.status != OrderStatus.CANCELLED,
        )
    ) or Decimal("0")
    return SourceStats(
        source=source,
        users_count=users_count,
        orders_count=orders_count,
        revenue=Decimal(revenue),
    )

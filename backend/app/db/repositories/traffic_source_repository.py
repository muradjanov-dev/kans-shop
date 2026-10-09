import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TrafficSourceCodeConflictError, TrafficSourceInUseError
from app.db.models.enums import OrderStatus
from app.db.models.order import Order
from app.db.models.traffic_source import TrafficSource
from app.db.models.user import User
from app.services.common import Page

# Telegram allows A-Z a-z 0-9 _ - in a /start payload; the `src_` prefix eats 4 of its 64
# characters, and codes are lowercased so links stay case-insensitive to type by hand.
CODE_PATTERN = re.compile(r"^[a-z0-9_-]{2,32}$")


@dataclass(frozen=True)
class SourceStats:
    source: TrafficSource
    clicks: int
    first_touch_users: int
    orders_count: int
    order_value: Decimal

    @property
    def users_count(self) -> int:
        return self.first_touch_users

    @property
    def revenue(self) -> Decimal:
        """Compatibility alias for the historical, uncancelled order value."""
        return self.order_value


def normalize_code(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", raw.strip().lower()).strip("-_")
    return slug[:32]


async def get_by_code(session: AsyncSession, code: str) -> TrafficSource | None:
    return await session.scalar(
        select(TrafficSource).where(TrafficSource.code == code.lower())
    )


async def get_by_id(
    session: AsyncSession, source_id: int, *, lock: bool = False
) -> TrafficSource | None:
    statement = (
        select(TrafficSource)
        .where(TrafficSource.id == source_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def list_all(session: AsyncSession) -> Sequence[TrafficSource]:
    return (
        await session.scalars(select(TrafficSource).order_by(TrafficSource.created_at.desc()))
    ).all()


async def list_page(session: AsyncSession, *, page: int, limit: int) -> Page[TrafficSource]:
    total = await session.scalar(select(func.count()).select_from(TrafficSource)) or 0
    sources = (
        await session.scalars(
            select(TrafficSource)
            .order_by(TrafficSource.created_at.desc(), TrafficSource.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()
    return Page(items=sources, total=total, page=page, limit=limit)


async def create(session: AsyncSession, *, code: str, name: str) -> TrafficSource:
    source = TrafficSource(code=code.lower(), name=name)
    session.add(source)
    await session.flush()
    return source


async def create_unique(session: AsyncSession, *, code: str, name: str) -> TrafficSource:
    """Create a source while mapping a concurrent code collision to the domain error."""
    source_id = await session.scalar(
        insert(TrafficSource)
        .values(code=code.lower(), name=name)
        .on_conflict_do_nothing(index_elements=[TrafficSource.code])
        .returning(TrafficSource.id)
    )
    if source_id is None:
        raise TrafficSourceCodeConflictError("Traffic source code already exists")
    source = await session.get(TrafficSource, source_id)
    if source is None:
        raise RuntimeError("Created traffic source could not be reloaded")
    return source


async def delete(session: AsyncSession, source: TrafficSource) -> None:
    attributed_users = await session.scalar(
        select(func.count()).select_from(User).where(User.traffic_source_id == source.id)
    )
    if attributed_users:
        raise TrafficSourceInUseError("Attributed sources must be deactivated, not deleted")
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
    first_touch_users = (
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
    order_value = await session.scalar(
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
        clicks=source.clicks_count,
        first_touch_users=first_touch_users,
        orders_count=orders_count,
        order_value=Decimal(order_value),
    )

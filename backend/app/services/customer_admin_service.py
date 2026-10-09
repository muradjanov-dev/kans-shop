"""Shared, role-checked customer administration for the bot and web admin."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.admin import AdminUserDetail, AdminUserSourceSummary, UserOut
from app.core.exceptions import UserNotFoundError
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole
from app.db.models.order import Order
from app.db.models.traffic_source import TrafficSource
from app.db.models.user import User
from app.db.repositories import user_repository
from app.services.admin_actor_service import load_live_admin
from app.services.admin_audit_service import write_audit_event
from app.services.common import Page

MANAGEMENT_ROLES = frozenset({AdminRole.SUPERADMIN, AdminRole.MANAGER})


async def _load_manager(session: AsyncSession, admin_id: int, *, lock: bool = False) -> Admin:
    return await load_live_admin(
        session,
        admin_id=admin_id,
        allowed_roles=MANAGEMENT_ROLES,
        lock=lock,
    )


def mask_phone(phone: str | None) -> str | None:
    """Keep a country prefix and final four digits while hiding the subscriber number."""
    if phone is None:
        return None
    digits = "".join(character for character in phone if character.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits) if digits else None
    prefix_length = min(3, len(digits) - 4)
    return (
        ("+" if phone.strip().startswith("+") else "")
        + digits[:prefix_length]
        + "*" * (len(digits) - prefix_length - 4)
        + digits[-4:]
    )


async def list_admin_users(
    session: AsyncSession,
    *,
    admin_id: int,
    query: str | None,
    page: int,
    limit: int,
) -> Page[User]:
    await _load_manager(session, admin_id)
    if page < 1 or not 1 <= limit <= 100:
        raise ValueError("page must be positive and limit must be between 1 and 100")

    statement = select(User)
    normalized_query = (query or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(
            or_(
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.username.ilike(pattern),
                User.phone.ilike(pattern),
                cast(User.telegram_id, String).ilike(pattern),
                cast(User.id, String).ilike(pattern),
            )
        )

    total = await session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    items = (
        await session.scalars(
            statement.order_by(User.created_at.desc(), User.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()
    return Page(items=items, total=total or 0, page=page, limit=limit)


async def get_admin_user(
    session: AsyncSession,
    *,
    admin_id: int,
    user_id: int,
) -> AdminUserDetail:
    await _load_manager(session, admin_id)
    user = await user_repository.get_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError(f"User {user_id} not found")

    orders_count = await session.scalar(
        select(func.count()).select_from(Order).where(Order.user_id == user.id)
    )
    source = None
    if user.traffic_source_id is not None:
        source = await session.scalar(
            select(TrafficSource).where(TrafficSource.id == user.traffic_source_id)
        )

    base_user = UserOut.model_validate(user)
    return AdminUserDetail.model_validate(
        {
            **base_user.model_dump(),
            "orders_count": orders_count or 0,
            "first_touch_source": (
                AdminUserSourceSummary.model_validate(source) if source is not None else None
            ),
        }
    )


async def set_user_blocked(
    session: AsyncSession,
    *,
    admin_id: int,
    user_id: int,
    blocked: bool,
) -> User:
    actor = await _load_manager(session, admin_id, lock=True)
    if not isinstance(blocked, bool):
        raise ValueError("blocked must be a boolean")

    user = await user_repository.get_by_id(session, user_id, for_update=True)
    if user is None:
        raise UserNotFoundError(f"User {user_id} not found")
    previous = user.is_blocked
    if previous == blocked:
        return user

    await user_repository.set_blocked(session, user, blocked)
    await write_audit_event(
        session,
        admin_id=actor.id,
        action="user.block" if blocked else "user.unblock",
        entity="user",
        entity_id=user.id,
        request_id=uuid4().hex,
        before={"is_blocked": previous},
        after={"is_blocked": blocked},
    )
    return user

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AddressLimitExceededError, NotFoundError
from app.db.models.address import Address
from app.db.models.user import User

MAX_ADDRESSES_PER_USER = 20


async def _lock_owner(session: AsyncSession, user: User) -> User:
    owner = await session.scalar(select(User).where(User.id == user.id).with_for_update())
    if owner is None:
        raise NotFoundError("User not found")
    return owner


async def get_address(session: AsyncSession, user: User, address_id: int) -> Address | None:
    return await session.scalar(
        select(Address).where(Address.id == address_id, Address.user_id == user.id)
    )


async def list_addresses(session: AsyncSession, user: User) -> Sequence[Address]:
    result = await session.scalars(
        select(Address)
        .where(Address.user_id == user.id)
        .order_by(Address.is_default.desc(), Address.id.asc())
    )
    return result.all()


async def create_address(
    session: AsyncSession, user: User, payload: Mapping[str, Any]
) -> Address:
    owner = await _lock_owner(session, user)
    count = await session.scalar(
        select(func.count(Address.id)).where(Address.user_id == owner.id)
    )
    if (count or 0) >= MAX_ADDRESSES_PER_USER:
        raise AddressLimitExceededError("A customer can save at most 20 addresses")

    address = Address(
        user_id=owner.id,
        is_default=count == 0,
        **payload,
    )
    session.add(address)
    await session.flush()
    return address


async def update_address(
    session: AsyncSession,
    user: User,
    address_id: int,
    patch: Mapping[str, Any],
) -> Address | None:
    owner = await _lock_owner(session, user)
    address = await session.scalar(
        select(Address)
        .where(Address.id == address_id, Address.user_id == owner.id)
        .with_for_update()
    )
    if address is None:
        return None

    for field, value in patch.items():
        setattr(address, field, value)
    await session.flush()
    return address


async def set_default_address(session: AsyncSession, user: User, address_id: int) -> Address:
    owner = await _lock_owner(session, user)
    address = await session.scalar(
        select(Address)
        .where(Address.id == address_id, Address.user_id == owner.id)
        .with_for_update()
    )
    if address is None:
        raise NotFoundError("Address not found")

    defaults = await session.scalars(
        select(Address)
        .where(Address.user_id == owner.id, Address.is_default.is_(True))
        .with_for_update()
    )
    for current_default in defaults:
        current_default.is_default = False
    await session.flush()

    address.is_default = True
    await session.flush()
    return address


async def delete_address(session: AsyncSession, user: User, address_id: int) -> bool:
    owner = await _lock_owner(session, user)
    address = await session.scalar(
        select(Address)
        .where(Address.id == address_id, Address.user_id == owner.id)
        .with_for_update()
    )
    if address is None:
        return False

    await session.delete(address)
    await session.flush()
    return True

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import UserSource
from app.db.models.user import User


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def create(
    session: AsyncSession,
    *,
    telegram_id: int,
    first_name: str,
    last_name: str | None = None,
    username: str | None = None,
    language: str = "uz",
    source: UserSource = UserSource.BOT,
) -> User:
    user = User(
        telegram_id=telegram_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        language=language,
        source=source,
        last_active_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    return user


async def get_or_create(
    session: AsyncSession,
    *,
    telegram_id: int,
    first_name: str,
    last_name: str | None = None,
    username: str | None = None,
    source: UserSource = UserSource.BOT,
) -> tuple[User, bool]:
    user = await get_by_telegram_id(session, telegram_id)
    if user is not None:
        return user, False
    user = await create(
        session,
        telegram_id=telegram_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        source=source,
    )
    return user, True


async def touch_last_active(session: AsyncSession, user: User) -> None:
    user.last_active_at = datetime.now(UTC)
    await session.flush()


async def set_language(session: AsyncSession, user: User, language: str) -> None:
    user.language = language
    await session.flush()


async def set_phone(session: AsyncSession, user: User, phone: str) -> None:
    user.phone = phone
    await session.flush()


async def set_blocked(session: AsyncSession, user: User, blocked: bool) -> None:
    user.is_blocked = blocked
    await session.flush()

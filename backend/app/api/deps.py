from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence

from aiogram import Bot
from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole
from app.db.models.user import User
from app.db.repositories import admin_repository, user_repository
from app.db.session import async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token, expected_type="access")
    user = await user_repository.get_by_id(session, int(payload["sub"]))
    if user is None:
        raise UnauthorizedError("User not found")
    if user.is_blocked:
        raise ForbiddenError("User is blocked")
    return user


async def get_current_admin(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Admin:
    admin = await admin_repository.get_by_telegram_id(session, user.telegram_id)
    if admin is None or not admin.is_active:
        raise ForbiddenError("Admin access required")
    return admin


def require_admin_roles(*roles: AdminRole) -> Callable[[Admin], Awaitable[Admin]]:
    """Usage: `admin: Admin = Depends(require_admin_roles(AdminRole.MANAGER, ...))`."""

    async def _dependency(admin: Admin = Depends(get_current_admin)) -> Admin:
        if roles and admin.role not in roles:
            raise ForbiddenError("Insufficient role for this action")
        return admin

    return _dependency


MANAGEMENT_ROLES: Sequence[AdminRole] = (AdminRole.SUPERADMIN, AdminRole.MANAGER)


def get_bot(request: Request) -> Bot:
    return request.app.state.bot

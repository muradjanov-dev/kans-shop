import hmac
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from datetime import UTC, datetime

from aiogram import Bot
from fastapi import Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AdminSessionInvalidError,
    AdminSessionRequiredError,
    CsrfFailedError,
    ForbiddenError,
    UnauthorizedError,
)
from app.core.security import decode_token
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole
from app.db.models.user import User
from app.db.repositories import user_repository
from app.db.session import async_session_maker
from app.services.admin_session_service import (
    AdminSessionPrincipal,
    resolve_admin_session,
)
from app.services.after_commit import commit_with_after_commit


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await commit_with_after_commit(session)
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db, scope="function"),
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


async def get_admin_session_principal(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db, scope="function"),
) -> AdminSessionPrincipal:
    try:
        raw_cookie = request.cookies.get("__Host-kans-admin")
    except Exception:
        raise AdminSessionRequiredError("Admin session required") from None
    if raw_cookie is None:
        raise AdminSessionRequiredError("Admin session required")

    try:
        principal = await resolve_admin_session(
            session, raw_token=raw_cookie, now=datetime.now(UTC)
        )
    except AdminSessionInvalidError:
        # Persist revocation even though the authorization error aborts this request's unit of work.
        await session.commit()
        raise

    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf_token = request.headers.get("x-csrf-token")
        if (
            request.headers.get("origin") != settings.webapp_origin
            or csrf_token is None
            or not csrf_token.isascii()
            or not hmac.compare_digest(csrf_token, principal.csrf_token)
        ):
            raise CsrfFailedError("Request origin or CSRF token check failed")

    response.headers["Cache-Control"] = "private, no-store"
    return principal


async def get_current_admin(
    principal: AdminSessionPrincipal = Depends(get_admin_session_principal),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> Admin:
    admin = await session.get(Admin, principal.admin_id)
    if admin is None or not admin.is_active:
        raise AdminSessionRequiredError("Admin session required")
    return admin


def require_admin_roles(*roles: AdminRole) -> Callable[..., Awaitable[Admin]]:
    """Usage: `admin: Admin = Depends(require_admin_roles(AdminRole.MANAGER, ...))`."""

    async def _dependency(admin: Admin = Depends(get_current_admin)) -> Admin:
        if roles and admin.role not in roles:
            raise ForbiddenError("Insufficient role for this action")
        return admin

    return _dependency


MANAGEMENT_ROLES: Sequence[AdminRole] = (AdminRole.SUPERADMIN, AdminRole.MANAGER)


def get_bot(request: Request) -> Bot:
    return request.app.state.bot

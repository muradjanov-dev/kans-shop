import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AdminSessionInvalidError, AdminSessionRequiredError
from app.db.models.admin import Admin
from app.db.models.admin_session import AdminSession
from app.db.models.enums import AdminRole

IDLE_TTL = timedelta(hours=12)
ABSOLUTE_TTL = timedelta(days=7)
_RAW_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


@dataclass(frozen=True)
class AdminSessionPrincipal:
    admin_id: int
    session_id: int
    role: AdminRole
    csrf_token: str


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _digest_cookie(raw_token: str) -> str:
    if not _RAW_TOKEN_PATTERN.fullmatch(raw_token):
        raise AdminSessionRequiredError("Admin session required")
    return hashlib.sha256(raw_token.encode("ascii")).hexdigest()


async def create_admin_session(
    session: AsyncSession, *, admin_id: int, now: datetime
) -> tuple[AdminSessionPrincipal, str]:
    now = _as_utc(now)
    admin = await session.get(Admin, admin_id)
    if admin is None or not admin.is_active:
        raise AdminSessionRequiredError("Admin session required")

    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(96)
    admin_session = AdminSession(
        admin_id=admin.id,
        token_hash=hashlib.sha256(raw_token.encode("ascii")).hexdigest(),
        csrf_token=csrf_token,
        auth_epoch=admin.auth_epoch,
        idle_expires_at=now + IDLE_TTL,
        absolute_expires_at=now + ABSOLUTE_TTL,
    )
    session.add(admin_session)
    await session.flush()

    return (
        AdminSessionPrincipal(
            admin_id=admin.id,
            session_id=admin_session.id,
            role=admin.role,
            csrf_token=csrf_token,
        ),
        raw_token,
    )


async def _require_live_session(
    session: AsyncSession, admin_session: AdminSession, *, now: datetime
) -> Admin:
    admin = await session.get(Admin, admin_session.admin_id)
    if admin_session.revoked_at is not None:
        raise AdminSessionRequiredError("Admin session required")

    if (
        admin is None
        or not admin.is_active
        or admin_session.auth_epoch != admin.auth_epoch
        or _as_utc(now) >= _as_utc(admin_session.idle_expires_at)
        or _as_utc(now) >= _as_utc(admin_session.absolute_expires_at)
    ):
        admin_session.revoked_at = _as_utc(now)
        await session.flush()
        raise AdminSessionInvalidError("Admin session required")

    return admin


async def _extend_idle_expiry(
    session: AsyncSession, admin_session: AdminSession, *, now: datetime
) -> None:
    deadline = _as_utc(now) + IDLE_TTL
    await session.execute(
        update(AdminSession)
        .where(AdminSession.id == admin_session.id, AdminSession.revoked_at.is_(None))
        .values(
            idle_expires_at=func.least(
                AdminSession.absolute_expires_at,
                func.greatest(AdminSession.idle_expires_at, deadline),
            )
        )
        .execution_options(synchronize_session=False)
    )


async def resolve_admin_session(
    session: AsyncSession, *, raw_token: str, now: datetime
) -> AdminSessionPrincipal:
    now = _as_utc(now)
    try:
        token_hash = _digest_cookie(raw_token)
    except (AttributeError, TypeError, UnicodeEncodeError):
        raise AdminSessionRequiredError("Admin session required") from None

    admin_session = await session.scalar(
        select(AdminSession).where(AdminSession.token_hash == token_hash)
    )
    if admin_session is None:
        raise AdminSessionRequiredError("Admin session required")

    admin = await _require_live_session(session, admin_session, now=now)
    await _extend_idle_expiry(session, admin_session, now=now)
    return AdminSessionPrincipal(
        admin_id=admin.id,
        session_id=admin_session.id,
        role=admin.role,
        csrf_token=admin_session.csrf_token,
    )


async def refresh_admin_session(
    session: AsyncSession, *, principal: AdminSessionPrincipal, now: datetime
) -> None:
    now = _as_utc(now)
    admin_session = await session.get(AdminSession, principal.session_id)
    if (
        admin_session is None
        or admin_session.admin_id != principal.admin_id
        or not hmac.compare_digest(admin_session.csrf_token, principal.csrf_token)
    ):
        raise AdminSessionRequiredError("Admin session required")

    await _require_live_session(session, admin_session, now=now)
    await _extend_idle_expiry(session, admin_session, now=now)


async def revoke_admin_session(
    session: AsyncSession, *, principal: AdminSessionPrincipal, now: datetime
) -> None:
    admin_session = await session.get(AdminSession, principal.session_id)
    if (
        admin_session is not None
        and admin_session.admin_id == principal.admin_id
        and admin_session.revoked_at is None
    ):
        admin_session.revoked_at = _as_utc(now)
        await session.flush()


async def revoke_all_admin_sessions(
    session: AsyncSession, *, admin: Admin, now: datetime
) -> None:
    now = _as_utc(now)
    admin.auth_epoch += 1
    await session.execute(
        update(AdminSession)
        .where(AdminSession.admin_id == admin.id, AdminSession.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    await session.flush()

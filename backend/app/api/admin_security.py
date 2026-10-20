import json
from datetime import UTC, datetime

from aiogram import Bot
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_admin_session_principal, get_bot, get_current_admin, get_db
from app.api.schemas.auth import (
    AdminCodeAuthIn,
    AdminCodeRequestIn,
    AdminCodeRequestOut,
    AdminSessionOut,
)
from app.bot.utils.i18n import SUPPORTED_LANGUAGES, translate
from app.core.config import settings
from app.core.exceptions import (
    AdminSessionInvalidError,
    CsrfFailedError,
    InvalidOrExpiredAdminCodeError,
    UnsupportedMediaTypeError,
)
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.db.models.admin import Admin
from app.db.models.user import User
from app.db.repositories import admin_repository
from app.services.admin_login_code_service import (
    ADMIN_LOGIN_KEY_PREFIX,
    CODE_TTL_SECONDS,
    REQUEST_COOLDOWN_SECONDS,
    claim_request_slot,
    issue_admin_login_code,
    release_request_slot,
)
from app.services.admin_session_service import (
    AdminSessionPrincipal,
    create_admin_session,
    refresh_admin_session,
    revoke_admin_session,
    revoke_all_admin_sessions,
)

log = get_logger(__name__)

__all__ = ["ADMIN_LOGIN_KEY_PREFIX", "router"]

ADMIN_COOKIE_NAME = "__Host-kans-admin"
ADMIN_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

router = APIRouter(prefix="/auth/admin", tags=["admin-auth"])


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


def _require_exact_origin(request: Request) -> None:
    if request.headers.get("origin") != settings.webapp_origin:
        raise CsrfFailedError("Request origin check failed")


def _session_out(admin: Admin, principal: AdminSessionPrincipal) -> AdminSessionOut:
    return AdminSessionOut(
        admin_id=admin.id,
        full_name=admin.full_name,
        role=admin.role,
        csrf_token=principal.csrf_token,
    )


def _require_json(request: Request, message: str) -> None:
    content_type = request.headers.get("content-type", "").split(";", maxsplit=1)[0].strip()
    if content_type.lower() != "application/json" and not content_type.lower().endswith(
        "+json"
    ):
        raise UnsupportedMediaTypeError(message)


async def _find_admin_by_identifier(session: AsyncSession, identifier: str) -> Admin | None:
    """Resolve a Telegram user ID or @username to an active admin, or None."""
    value = identifier.strip()
    if value.isdigit():
        admin = await admin_repository.get_by_telegram_id(session, int(value))
    else:
        username = value.removeprefix("@").strip().lower()
        if not username:
            return None
        telegram_id = await session.scalar(
            select(User.telegram_id).where(func.lower(User.username) == username).limit(1)
        )
        if telegram_id is None:
            return None
        admin = await admin_repository.get_by_telegram_id(session, telegram_id)
    if admin is None or not admin.is_active:
        return None
    return admin


async def _send_admin_login_code(
    bot: Bot, *, telegram_id: int, code: str, language: str
) -> None:
    try:
        await bot.send_message(
            telegram_id,
            translate(language, "admin.login_code", code=code, minutes=CODE_TTL_SECONDS // 60),
        )
    except Exception:
        # Telegram unreachable or the admin blocked the bot: let them ask again right away.
        log.warning("admin_login_code_delivery_failed", telegram_id=telegram_id, exc_info=True)
        await release_request_slot(get_redis(), telegram_id)


@router.post("/code/request", response_model=AdminCodeRequestOut)
async def request_admin_code(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db, scope="function"),
) -> AdminCodeRequestOut:
    """Send a fresh five-minute login code to the admin's Telegram chat.

    The answer is the same whether or not the identifier belongs to an admin, so the page
    cannot be used to discover who the admins are; delivery happens after the response.
    """
    _require_exact_origin(request)
    _require_json(request, "Admin code request requires JSON")
    _no_store(response)
    result = AdminCodeRequestOut(
        expires_in=CODE_TTL_SECONDS, resend_after=REQUEST_COOLDOWN_SECONDS
    )
    try:
        payload = AdminCodeRequestIn.model_validate(await request.json())
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError):
        return result

    admin = await _find_admin_by_identifier(session, payload.identifier)
    if admin is None:
        return result

    redis = get_redis()
    if not await claim_request_slot(redis, admin.telegram_id):
        return result
    code = await issue_admin_login_code(redis, admin.telegram_id)
    language = await session.scalar(
        select(User.language).where(User.telegram_id == admin.telegram_id).limit(1)
    )
    background_tasks.add_task(
        _send_admin_login_code,
        get_bot(request),
        telegram_id=admin.telegram_id,
        code=code,
        language=language if language in SUPPORTED_LANGUAGES else "uz",
    )
    return result


@router.post(
    "/code/exchange",
    response_model=AdminSessionOut,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": AdminCodeAuthIn.model_json_schema()}},
        }
    },
)
async def exchange_admin_code(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db, scope="function"),
) -> AdminSessionOut:
    _require_exact_origin(request)
    _require_json(request, "Admin code exchange requires JSON")

    try:
        payload = AdminCodeAuthIn.model_validate(await request.json())
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError):
        raise InvalidOrExpiredAdminCodeError("Invalid or expired code") from None

    redis = get_redis()
    telegram_id_text = await redis.getdel(f"{ADMIN_LOGIN_KEY_PREFIX}{payload.code}")
    if telegram_id_text is None:
        raise InvalidOrExpiredAdminCodeError("Invalid or expired code")
    try:
        telegram_id = int(telegram_id_text)
    except (TypeError, ValueError):
        raise InvalidOrExpiredAdminCodeError("Invalid or expired code") from None

    admin = await admin_repository.get_by_telegram_id(session, telegram_id)
    if admin is None or not admin.is_active:
        raise InvalidOrExpiredAdminCodeError("Invalid or expired code")

    principal, raw_cookie = await create_admin_session(
        session, admin_id=admin.id, now=datetime.now(UTC)
    )
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=raw_cookie,
        max_age=ADMIN_COOKIE_MAX_AGE_SECONDS,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    _no_store(response)
    return _session_out(admin, principal)


@router.get("/session", response_model=AdminSessionOut)
async def get_admin_session(
    response: Response,
    principal: AdminSessionPrincipal = Depends(get_admin_session_principal),
    admin: Admin = Depends(get_current_admin),
) -> AdminSessionOut:
    _no_store(response)
    return _session_out(admin, principal)


@router.post("/session/refresh", response_model=AdminSessionOut)
async def refresh_admin_session_endpoint(
    response: Response,
    principal: AdminSessionPrincipal = Depends(get_admin_session_principal),
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> AdminSessionOut:
    try:
        await refresh_admin_session(session, principal=principal, now=datetime.now(UTC))
    except AdminSessionInvalidError:
        await session.commit()
        raise
    _no_store(response)
    return _session_out(admin, principal)


@router.post("/logout")
async def logout_admin(
    response: Response,
    principal: AdminSessionPrincipal = Depends(get_admin_session_principal),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    await revoke_admin_session(session, principal=principal, now=datetime.now(UTC))
    response.delete_cookie(
        key=ADMIN_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    _no_store(response)
    return {"ok": True}


@router.post("/logout-all")
async def logout_all_admin_sessions(
    response: Response,
    admin: Admin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    await revoke_all_admin_sessions(session, admin=admin, now=datetime.now(UTC))
    response.delete_cookie(
        key=ADMIN_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    _no_store(response)
    return {"ok": True}

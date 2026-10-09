import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_admin_session_principal, get_current_admin, get_db
from app.api.schemas.auth import AdminCodeAuthIn, AdminSessionOut
from app.core.config import settings
from app.core.exceptions import (
    AdminSessionInvalidError,
    CsrfFailedError,
    InvalidOrExpiredAdminCodeError,
    UnsupportedMediaTypeError,
)
from app.core.redis import get_redis
from app.db.models.admin import Admin
from app.db.repositories import admin_repository
from app.services.admin_session_service import (
    AdminSessionPrincipal,
    create_admin_session,
    refresh_admin_session,
    revoke_admin_session,
    revoke_all_admin_sessions,
)

ADMIN_LOGIN_KEY_PREFIX = "admin_login:"
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
    content_type = request.headers.get("content-type", "").split(";", maxsplit=1)[0].strip()
    if content_type.lower() != "application/json" and not content_type.lower().endswith(
        "+json"
    ):
        raise UnsupportedMediaTypeError("Admin code exchange requires JSON")

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

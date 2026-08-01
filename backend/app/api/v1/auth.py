from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas.auth import BotCodeAuthIn, RefreshIn, TelegramAuthIn, TokenOut
from app.bot.handlers.admin.auth import ADMIN_LOGIN_KEY_PREFIX
from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_telegram_init_data,
)
from app.db.models.enums import UserSource
from app.db.repositories import admin_repository, user_repository

router = APIRouter(prefix="/auth", tags=["auth"])


async def _issue_tokens(session: AsyncSession, telegram_id: int) -> TokenOut:
    user = await user_repository.get_by_telegram_id(session, telegram_id)
    if user is None:
        raise UnauthorizedError("User not found")
    admin = await admin_repository.get_by_telegram_id(session, telegram_id)
    access = create_access_token(
        user_id=user.id, telegram_id=user.telegram_id, is_admin=admin is not None
    )
    refresh = create_refresh_token(user_id=user.id, telegram_id=user.telegram_id)
    return TokenOut(access_token=access, refresh_token=refresh, is_admin=admin is not None)


@router.post("/telegram", response_model=TokenOut)
async def auth_telegram(
    payload: TelegramAuthIn, session: AsyncSession = Depends(get_db)
) -> TokenOut:
    """Validates Telegram WebApp `initData` (Mini App) and issues a JWT pair."""
    data = verify_telegram_init_data(payload.init_data, bot_token=settings.bot_token)
    tg_user = data["user"]
    user, _created = await user_repository.get_or_create(
        session,
        telegram_id=tg_user["id"],
        first_name=tg_user.get("first_name", ""),
        last_name=tg_user.get("last_name"),
        username=tg_user.get("username"),
        source=UserSource.WEBAPP,
    )
    await user_repository.touch_last_active(session, user)
    return await _issue_tokens(session, user.telegram_id)


@router.post("/telegram/code", response_model=TokenOut)
async def auth_bot_code(
    payload: BotCodeAuthIn, session: AsyncSession = Depends(get_db)
) -> TokenOut:
    """Admin-panel login fallback: exchanges a one-time code issued by /admin_login in the bot
    for a JWT (used for local dev / non-HTTPS admin access, see docs/ASSUMPTIONS.md)."""
    redis = get_redis()
    key = f"{ADMIN_LOGIN_KEY_PREFIX}{payload.code}"
    telegram_id_str = await redis.get(key)
    if telegram_id_str is None:
        raise UnauthorizedError("Invalid or expired code")
    await redis.delete(key)
    return await _issue_tokens(session, int(telegram_id_str))


@router.post("/refresh", response_model=TokenOut)
async def refresh_token(
    payload: RefreshIn, session: AsyncSession = Depends(get_db)
) -> TokenOut:
    data = decode_token(payload.refresh_token, expected_type="refresh")
    return await _issue_tokens(session, data["telegram_id"])

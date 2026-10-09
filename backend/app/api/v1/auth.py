from aiogram import Bot
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_db
from app.api.schemas.auth import (
    BotCodeAuthIn,
    CustomerCodeAuthIn,
    RefreshIn,
    TelegramAuthIn,
    TokenOut,
)
from app.core.config import settings
from app.core.exceptions import ForbiddenError, GoneError, UnauthorizedError
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_telegram_init_data,
)
from app.db.models.enums import UserSource
from app.db.repositories import admin_repository, user_repository
from app.services.customer_auth_service import (
    InvalidOrExpiredCustomerCodeError,
    consume_customer_code,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _issue_tokens(session: AsyncSession, telegram_id: int) -> TokenOut:
    user = await user_repository.get_by_telegram_id(session, telegram_id)
    if user is None:
        raise UnauthorizedError("User not found")
    if user.is_blocked:
        raise ForbiddenError("User is blocked")
    admin = await admin_repository.get_by_telegram_id(session, telegram_id)
    is_admin = admin is not None and admin.is_active
    access = create_access_token(
        user_id=user.id, telegram_id=user.telegram_id, is_admin=is_admin
    )
    refresh = create_refresh_token(user_id=user.id, telegram_id=user.telegram_id)
    return TokenOut(access_token=access, refresh_token=refresh, is_admin=is_admin)


@router.post("/telegram", response_model=TokenOut)
async def auth_telegram(
    payload: TelegramAuthIn,
    session: AsyncSession = Depends(get_db),
    bot: Bot = Depends(get_bot),
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
    if _created:
        from app.bot.services.user_notifications import notify_admins_new_users_batch

        await notify_admins_new_users_batch(bot, session, user)
    await user_repository.touch_last_active(session, user)
    return await _issue_tokens(session, user.telegram_id)


@router.post("/telegram/code")
async def auth_bot_code(_payload: BotCodeAuthIn) -> None:
    """Retired admin JWT exchange; browser admins must use the secure session flow."""
    raise GoneError("Admin JWT code exchange has been retired")


@router.post("/customer/code", response_model=TokenOut)
async def auth_customer_code(
    payload: CustomerCodeAuthIn, session: AsyncSession = Depends(get_db)
) -> TokenOut:
    """Exchange a private customer code from the bot for a JWT pair."""
    telegram_id = await consume_customer_code(get_redis(), payload.code)
    try:
        return await _issue_tokens(session, telegram_id)
    except UnauthorizedError as exc:
        raise InvalidOrExpiredCustomerCodeError("Invalid or expired code") from exc


@router.post("/refresh", response_model=TokenOut)
async def refresh_token(
    payload: RefreshIn, session: AsyncSession = Depends(get_db)
) -> TokenOut:
    data = decode_token(payload.refresh_token, expected_type="refresh")
    return await _issue_tokens(session, data["telegram_id"])

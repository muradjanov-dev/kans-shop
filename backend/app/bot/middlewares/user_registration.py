from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import UserSource
from app.db.repositories import admin_repository, user_repository


class UserRegistrationMiddleware(BaseMiddleware):
    """Ensures every update has a `users` row (creating one on first contact), touches
    last_active_at, and attaches the matching `admins` row (or None) for downstream handlers.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        session: AsyncSession = data["session"]
        user, created = await user_repository.get_or_create(
            session,
            telegram_id=tg_user.id,
            first_name=tg_user.first_name or "",
            last_name=tg_user.last_name,
            username=tg_user.username,
            source=UserSource.BOT,
        )
        if not created:
            await user_repository.touch_last_active(session, user)

        data["user"] = user
        data["is_new_user"] = created
        data["admin"] = await admin_repository.get_by_telegram_id(session, tg_user.id)
        return await handler(event, data)

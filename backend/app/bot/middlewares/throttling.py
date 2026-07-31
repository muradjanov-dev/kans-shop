from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject
from redis.asyncio import Redis


class ThrottlingMiddleware(BaseMiddleware):
    """Fixed-window rate limit per Telegram user, backed by Redis (spec: 20 req/min)."""

    def __init__(self, redis: Redis, *, limit: int = 20, window_seconds: int = 60) -> None:
        self.redis = redis
        self.limit = limit
        self.window_seconds = window_seconds

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        key = f"throttle:{tg_user.id}"
        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, self.window_seconds)

        if current > self.limit:
            translator = data.get("_")
            message = translator("common.rate_limited") if translator else "Rate limited."
            if isinstance(event, CallbackQuery):
                await event.answer(message, show_alert=True)
            return None

        return await handler(event, data)

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.db.session import async_session_maker
from app.services.after_commit import commit_with_after_commit


class DbSessionMiddleware(BaseMiddleware):
    """Opens one AsyncSession per update, commits on success, rolls back on any exception."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with async_session_maker() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise
            await commit_with_after_commit(session)
            return result

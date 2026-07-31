from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.bot.utils.i18n import translate
from app.core.config import settings


class I18nMiddleware(BaseMiddleware):
    """Attaches `data["lang"]` and `data["_"]` (a `_(key, **kwargs)` translator bound to the
    current user's language) so handlers never hardcode user-facing text."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("user")
        lang = user.language if user is not None else settings.default_language
        data["lang"] = lang
        data["_"] = partial(translate, lang)
        return await handler(event, data)

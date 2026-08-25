"""The bot's own @username, resolved from Telegram rather than trusted from config.

`BOT_USERNAME` is hand-entered and drifts: production had `kansshop_bot` while the bot is
actually `@kansshopbot`, which would have shipped every generated deep link pointing at a bot
that does not exist. getMe is authoritative, so ask it once and cache the answer for the
process lifetime; the setting stays as the fallback for when that call fails.
"""

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_cached_username: str | None = None


async def bot_username(bot: Bot) -> str:
    global _cached_username

    if _cached_username is not None:
        return _cached_username

    try:
        me = await bot.get_me()
    except TelegramAPIError as exc:
        log.error("get_me_failed", error=str(exc))
        return settings.bot_username

    if me.username:
        if me.username != settings.bot_username:
            log.warning(
                "bot_username_setting_mismatch",
                configured=settings.bot_username,
                actual=me.username,
            )
        _cached_username = me.username
    else:
        _cached_username = settings.bot_username
    return _cached_username

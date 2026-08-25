"""Bot command menu (the "/" list next to the input bar).

Registered on startup because the main menu moved from a persistent reply keyboard to an
inline one: inline keyboards scroll out of view, so /menu is the guaranteed way back.
"""

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeDefault

from app.bot.utils.i18n import SUPPORTED_LANGUAGES, translate
from app.core.logging import get_logger

log = get_logger(__name__)

_COMMANDS = (
    ("start", "commands.start"),
    ("menu", "commands.menu"),
    ("admin", "commands.admin"),
)


async def setup_bot_commands(bot: Bot) -> None:
    for lang in SUPPORTED_LANGUAGES:
        commands = [
            BotCommand(command=name, description=translate(lang, key))
            for name, key in _COMMANDS
        ]
        try:
            await bot.set_my_commands(
                commands, scope=BotCommandScopeDefault(), language_code=lang
            )
        except TelegramAPIError as exc:
            log.error("set_my_commands_failed", lang=lang, error=str(exc))

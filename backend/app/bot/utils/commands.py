"""Bot command menu (the "/" list next to the input bar).

Registered on startup alongside the versioned WebApp entry. Catalog browsing keeps a
persistent Cart shortcut; /menu also returns to the complete inline main menu.
"""

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonWebApp, WebAppInfo

from app.bot.utils.i18n import SUPPORTED_LANGUAGES, translate
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_COMMANDS = (
    ("start", "commands.start"),
    ("menu", "commands.menu"),
    ("web_login", "commands.web_login"),
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


async def setup_webapp_menu_button(bot: Bot) -> None:
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Kans Shop",
                web_app=WebAppInfo(url=settings.webapp_entry_url),
            )
        )
    except TelegramAPIError as exc:
        log.error("set_webapp_menu_button_failed", error_type=type(exc).__name__)
        return
    log.info("webapp_menu_button_configured", entry_version=settings.webapp_entry_version)

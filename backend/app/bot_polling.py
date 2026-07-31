import asyncio

from app.bot.loader import create_bot, create_dispatcher
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)


async def main() -> None:
    configure_logging()
    bot = create_bot()
    dp = create_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("bot_polling_start")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

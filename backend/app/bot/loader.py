from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis, from_url

from app.bot.handlers import root_router
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.i18n import I18nMiddleware
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.bot.middlewares.user_registration import UserRegistrationMiddleware
from app.core.config import settings


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(redis: Redis | None = None) -> Dispatcher:
    redis = redis or from_url(settings.redis_url)
    storage = RedisStorage(redis)

    dp = Dispatcher(storage=storage)
    dp["redis"] = redis

    # Outer middlewares run once per Update, in this order, before routing to a handler.
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(UserRegistrationMiddleware())
    dp.update.outer_middleware(I18nMiddleware())
    dp.update.outer_middleware(ThrottlingMiddleware(redis))

    dp.include_router(root_router)
    return dp

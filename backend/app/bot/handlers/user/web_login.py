from collections.abc import Callable

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message
from redis.asyncio import Redis

from app.core.exceptions import RateLimitedError
from app.db.models.user import User
from app.services.customer_auth_service import issue_customer_code

router = Router(name="user_web_login")


async def send_customer_login_code(
    message: Message, user: User, redis: Redis, translator: Callable
) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer(translator("auth.private_chat_only"))
        return
    if user.is_blocked:
        await message.answer(translator("auth.blocked"))
        return

    try:
        code = await issue_customer_code(redis, user.telegram_id)
    except RateLimitedError:
        await message.answer(translator("common.rate_limited"))
        return

    await message.answer(
        translator(
            "auth.customer_code",
            code=code,
            minutes=5,
        )
    )


@router.message(Command("web_login"))
async def cmd_web_login(
    message: Message,
    user: User,
    redis: Redis,
    _: Callable,
) -> None:
    await send_customer_login_code(message, user, redis, _)

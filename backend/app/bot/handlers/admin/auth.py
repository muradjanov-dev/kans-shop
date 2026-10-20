from collections.abc import Callable

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message
from redis.asyncio import Redis

from app.bot.utils.admin_guard import require_admin
from app.db.models.admin import Admin
from app.services.admin_login_code_service import (
    ADMIN_LOGIN_KEY_PREFIX,
    CODE_TTL_SECONDS,
    issue_admin_login_code,
)

router = Router(name="admin_auth")

__all__ = ["ADMIN_LOGIN_KEY_PREFIX", "CODE_TTL_SECONDS", "router"]


@router.message(Command("admin_login"))
async def cmd_admin_login(
    message: Message, admin: Admin | None, redis: Redis, _: Callable
) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer(_("auth.private_chat_only"))
        return
    if not await require_admin(message, admin, _):
        return
    assert admin is not None  # require_admin() only returns True when admin is set
    code = await issue_admin_login_code(redis, admin.telegram_id)
    await message.answer(_("admin.login_code", code=code, minutes=CODE_TTL_SECONDS // 60))

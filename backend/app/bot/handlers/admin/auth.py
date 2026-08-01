import secrets
from collections.abc import Callable

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from redis.asyncio import Redis

from app.bot.utils.admin_guard import require_admin
from app.db.models.admin import Admin

router = Router(name="admin_auth")

CODE_TTL_SECONDS = 300
ADMIN_LOGIN_KEY_PREFIX = "admin_login:"


@router.message(Command("admin_login"))
async def cmd_admin_login(
    message: Message, admin: Admin | None, redis: Redis, _: Callable
) -> None:
    if not await require_admin(message, admin, _):
        return
    assert admin is not None  # require_admin() only returns True when admin is set
    code = f"{secrets.randbelow(1_000_000):06d}"
    await redis.set(
        f"{ADMIN_LOGIN_KEY_PREFIX}{code}", str(admin.telegram_id), ex=CODE_TTL_SECONDS
    )
    await message.answer(_("admin.login_code", code=code, minutes=CODE_TTL_SECONDS // 60))

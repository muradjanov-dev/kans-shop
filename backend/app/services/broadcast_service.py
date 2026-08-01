import asyncio
from collections.abc import Awaitable, Callable, Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.db.repositories import user_repository

MESSAGES_PER_SECOND = 20
PROGRESS_UPDATE_EVERY = 20


async def _send_one(
    bot: Bot,
    session: AsyncSession,
    user: User,
    *,
    text: str,
    photo_file_id: str | None,
    button_markup: InlineKeyboardMarkup | None,
) -> bool:
    try:
        if photo_file_id:
            await bot.send_photo(
                user.telegram_id, photo_file_id, caption=text, reply_markup=button_markup
            )
        else:
            await bot.send_message(user.telegram_id, text, reply_markup=button_markup)
        return True
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        try:
            if photo_file_id:
                await bot.send_photo(
                    user.telegram_id, photo_file_id, caption=text, reply_markup=button_markup
                )
            else:
                await bot.send_message(user.telegram_id, text, reply_markup=button_markup)
            return True
        except (TelegramForbiddenError, TelegramRetryAfter):
            return False
    except TelegramForbiddenError:
        await user_repository.set_blocked(session, user, True)
        return False


async def run_broadcast(
    bot: Bot,
    session: AsyncSession,
    audience: Sequence[User],
    *,
    text: str,
    photo_file_id: str | None,
    button_markup: InlineKeyboardMarkup | None,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> tuple[int, int]:
    """Paced (20 msg/sec) broadcast send, shared by the bot's inline-composer flow and the
    admin API's background-task flow. `on_progress` is UI-specific (e.g. editing a Telegram
    progress message) and is a no-op when the caller has nothing to update in real time."""
    sent = 0
    failed = 0
    total = len(audience)
    for index, user in enumerate(audience, start=1):
        ok = await _send_one(
            bot,
            session,
            user,
            text=text,
            photo_file_id=photo_file_id,
            button_markup=button_markup,
        )
        if ok:
            sent += 1
        else:
            failed += 1
        if on_progress is not None and (index % PROGRESS_UPDATE_EVERY == 0 or index == total):
            await on_progress(index, total)
        await asyncio.sleep(1 / MESSAGES_PER_SECOND)
    await session.commit()
    return sent, failed

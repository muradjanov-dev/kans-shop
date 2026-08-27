import asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.db.models.user import User
from app.db.repositories import admin_repository, user_repository
from app.bot.services.order_notifications import translator_for_admin


async def notify_admins_new_users_batch(
    bot: Bot, session: AsyncSession, new_user: User
) -> None:
    """
    Checks the total number of users and notifies admins if the total is a multiple of 5.
    """
    total_users = (await session.scalar(select(func.count()).select_from(User))) or 0

    if total_users > 0 and total_users % 5 == 0:
        admins = await admin_repository.list_active(session)
        if not admins:
            return

        for admin in admins:
            translator = await translator_for_admin(session, admin.telegram_id)
            text = translator("admin.new_users_batch_notification", total=total_users)
            try:
                await bot.send_message(admin.telegram_id, text)
            except (TelegramBadRequest, TelegramForbiddenError):
                pass


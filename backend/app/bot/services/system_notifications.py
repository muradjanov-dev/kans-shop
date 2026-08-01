import contextlib

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.services.order_notifications import translator_for_admin
from app.db.repositories import admin_repository


async def notify_admins_deploy(bot: Bot, session: AsyncSession) -> None:
    """Sent once at process startup when the app comes up in webhook (production) mode — lets
    admins know a deploy/restart just happened, without needing to check Railway themselves."""
    admins = await admin_repository.list_active_notifiable(session)
    for admin in admins:
        translator = await translator_for_admin(session, admin.telegram_id)
        with contextlib.suppress(TelegramBadRequest, TelegramForbiddenError):
            await bot.send_message(admin.telegram_id, translator("admin.deploy_notification"))

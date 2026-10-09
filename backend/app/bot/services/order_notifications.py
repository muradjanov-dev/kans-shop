"""Shared order-notification presentation helpers.

New order/status/payment delivery is queued by the business services and sent only by the
durable outbox worker. Keep locale resolution here for the existing bot order-card renderer.
"""

from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.utils.i18n import translate
from app.core.config import settings
from app.db.repositories import user_repository


async def translator_for_admin(session: AsyncSession, admin_telegram_id: int):
    admin_user = await user_repository.get_by_telegram_id(session, admin_telegram_id)
    lang = admin_user.language if admin_user else settings.default_language
    return partial(translate, lang)

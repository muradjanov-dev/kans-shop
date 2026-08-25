from collections.abc import Awaitable, Callable
from contextlib import suppress
from functools import partial
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from aiogram.types.update import UpdateTypeLookupError
from redis.asyncio import Redis

from app.bot.keyboards.callback_data import (
    CheckSubscriptionCallback,
    LanguageCallback,
)
from app.bot.keyboards.inline.subscription import subscription_gate_keyboard
from app.bot.utils.i18n import translate
from app.bot.utils.subscription import (
    channel_url,
    forget_subscription,
    is_gate_enabled,
    is_subscribed,
)
from app.core.config import settings

_CHECK_CALLBACK = CheckSubscriptionCallback().pack()
_LANGUAGE_PREFIX = f"{LanguageCallback.__prefix__}{LanguageCallback.__separator__}"


class SubscriptionMiddleware(BaseMiddleware):
    """Blocks every customer interaction until the user has joined the required channel.

    Bypassed for admins (who must stay able to run the shop) and for the two callbacks the
    gate itself depends on: the "I subscribed" re-check, and language selection — a first-time
    user picks their language before anything else, so the gate can be shown in it.
    """

    def __init__(self, redis: Redis | None = None) -> None:
        self.redis = redis

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not is_gate_enabled():
            return await handler(event, data)

        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        admin = data.get("admin")
        if (admin is not None and admin.is_active) or tg_user.id in settings.admin_ids_list:
            return await handler(event, data)

        # A first-ever update is the user's /start: let it through so they reach the language
        # picker. Everything after it is gated — and by then the gate speaks their language.
        if data.get("is_new_user"):
            return await handler(event, data)

        if isinstance(event, Update):
            try:
                inner = event.event
            except UpdateTypeLookupError:
                # An update type this aiogram build does not know: nothing to gate, and
                # raising here would break the whole update pipeline.
                return await handler(event, data)
        else:
            inner = event
        if not isinstance(inner, Message | CallbackQuery):
            return await handler(event, data)

        callback_data = inner.data if isinstance(inner, CallbackQuery) else None
        if callback_data is not None and callback_data.startswith(_LANGUAGE_PREFIX):
            return await handler(event, data)

        bot: Bot = data["bot"]
        translator = data.get("_") or partial(translate, settings.default_language)
        is_recheck = callback_data == _CHECK_CALLBACK

        if is_recheck:
            # The user says they have just joined — bypass the cached verdict.
            await forget_subscription(self.redis, tg_user.id)

        if await is_subscribed(bot, tg_user.id, self.redis):
            if is_recheck:
                await self._on_confirmed(inner, data, translator)
                return None
            return await handler(event, data)

        await self._show_gate(inner, bot, translator, is_recheck=is_recheck)
        return None

    async def _show_gate(
        self,
        inner: Message | CallbackQuery,
        bot: Bot,
        translator: Callable[..., str],
        *,
        is_recheck: bool,
    ) -> None:
        if isinstance(inner, CallbackQuery):
            await inner.answer(
                translator("subscription.not_subscribed_alert"), show_alert=True
            )
            if is_recheck:
                # The gate message is already on screen; re-sending it would just spam.
                return

        url = await channel_url(bot)
        target = inner.message if isinstance(inner, CallbackQuery) else inner
        if target is None or not isinstance(target, Message):
            return
        await target.answer(
            translator("subscription.required"),
            reply_markup=subscription_gate_keyboard(translator, channel_url=url),
        )

    async def _on_confirmed(
        self,
        inner: Message | CallbackQuery,
        data: dict[str, Any],
        translator: Callable[..., str],
    ) -> None:
        from app.bot.keyboards.inline.main_menu import main_menu_inline_keyboard

        if not isinstance(inner, CallbackQuery):
            return
        await inner.answer(translator("subscription.confirmed_alert"))

        message = inner.message
        if message is None or not isinstance(message, Message):
            return

        # The gate message may be too old to edit — the confirmation below still lands.
        with suppress(TelegramAPIError):
            await message.edit_text(translator("subscription.confirmed"))

        user = data.get("user")
        admin = data.get("admin")
        is_admin = admin is not None and admin.is_active
        await message.answer(
            translator("start.welcome", name=user.first_name if user else ""),
            reply_markup=main_menu_inline_keyboard(translator, is_admin=is_admin),
        )

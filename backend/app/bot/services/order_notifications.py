import contextlib
from datetime import datetime
from functools import partial
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.utils.admin_order_card import build_admin_order_keyboard, build_admin_order_text
from app.bot.utils.i18n import translate
from app.core.config import settings
from app.db.models.enums import OrderStatus
from app.db.models.order import Order
from app.db.repositories import admin_repository, user_repository
from app.services import order_service

STATUS_LABEL_KEYS = {
    OrderStatus.NEW: "orders.status_new",
    OrderStatus.CONFIRMED: "orders.status_confirmed",
    OrderStatus.PREPARING: "orders.status_preparing",
    OrderStatus.DELIVERING: "orders.status_delivering",
    OrderStatus.COMPLETED: "orders.status_completed",
    OrderStatus.CANCELLED: "orders.status_cancelled",
}

ACTION_KEY_BY_STATUS = {
    OrderStatus.CONFIRMED: "admin.confirmed_by",
    OrderStatus.PREPARING: "admin.preparing_by",
    OrderStatus.DELIVERING: "admin.delivering_by",
    OrderStatus.COMPLETED: "admin.completed_by",
    OrderStatus.CANCELLED: "admin.cancelled_by",
}


async def translator_for_admin(session: AsyncSession, admin_telegram_id: int):
    admin_user = await user_repository.get_by_telegram_id(session, admin_telegram_id)
    lang = admin_user.language if admin_user else settings.default_language
    return partial(translate, lang)


async def notify_admins_new_order(bot: Bot, session: AsyncSession, order: Order) -> None:
    """Sends the new-order card to every active, notification-enabled admin, each localized to
    that admin's own language (admins are `users` too, via UserRegistrationMiddleware)."""
    customer = await user_repository.get_by_id(session, order.user_id)
    if customer is None:
        return

    admins = await admin_repository.list_active_notifiable(session)
    for admin in admins:
        translator = await translator_for_admin(session, admin.telegram_id)
        text = build_admin_order_text(order, customer, translator=translator)
        keyboard = build_admin_order_keyboard(order, translator=translator)
        try:
            sent = await bot.send_message(admin.telegram_id, text, reply_markup=keyboard)
        except (TelegramBadRequest, TelegramForbiddenError):
            continue

        await order_service.set_admin_message_id(
            session, order, admin.telegram_id, sent.message_id
        )

        if order.receipt_file_id:
            is_pdf = order.receipt_url is not None and order.receipt_url.endswith(".pdf")
            try:
                if is_pdf:
                    await bot.send_document(
                        admin.telegram_id,
                        order.receipt_file_id,
                        reply_to_message_id=sent.message_id,
                    )
                else:
                    await bot.send_photo(
                        admin.telegram_id,
                        order.receipt_file_id,
                        reply_to_message_id=sent.message_id,
                    )
            except (TelegramBadRequest, TelegramForbiddenError):
                pass


async def sync_admin_cards(
    bot: Bot,
    session: AsyncSession,
    order: Order,
    *,
    action_key: str | None = None,
    admin_name: str | None = None,
    reason: str | None = None,
) -> None:
    """Re-renders the order card (new status, new keyboard) on every admin's copy — each in
    that admin's own language — and stamps who acted on it (action_key/admin_name/reason)."""
    customer = await user_repository.get_by_id(session, order.user_id)
    if customer is None:
        return

    local_time = datetime.now(ZoneInfo(settings.timezone)).strftime("%H:%M")

    for admin_telegram_id_str, message_id in list(order.admin_message_ids.items()):
        admin_telegram_id = int(admin_telegram_id_str)
        translator = await translator_for_admin(session, admin_telegram_id)

        processed_line = None
        if action_key:
            kwargs: dict[str, str | None] = {"admin": admin_name, "time": local_time}
            if reason:
                kwargs["reason"] = reason
            processed_line = translator(action_key, **kwargs)

        text = build_admin_order_text(
            order, customer, translator=translator, processed_line=processed_line
        )
        keyboard = build_admin_order_keyboard(order, translator=translator)
        try:
            await bot.edit_message_text(
                text, chat_id=admin_telegram_id, message_id=message_id, reply_markup=keyboard
            )
        except (TelegramBadRequest, TelegramForbiddenError):
            continue


async def notify_customer_status_change(
    bot: Bot,
    session: AsyncSession,
    order: Order,
    key: str,
    *,
    status_key: str | None = None,
    **kwargs: str,
) -> None:
    """Sends a status-change DM to the order's customer, localized to their own language."""
    customer = await user_repository.get_by_id(session, order.user_id)
    if customer is None:
        return
    translator = partial(translate, customer.language)
    if status_key is not None:
        kwargs["status"] = translator(status_key)
    text = translator(key, order_number=order.order_number, **kwargs)
    with contextlib.suppress(TelegramBadRequest, TelegramForbiddenError):
        await bot.send_message(customer.telegram_id, text)

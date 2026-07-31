import contextlib
from collections.abc import Callable
from functools import partial

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import (
    AdminAdvanceCallback,
    AdminBackToOrderCallback,
    AdminCancelReasonCallback,
    AdminCancelRequestCallback,
    AdminConfirmCallback,
    AdminMessageCustomerCallback,
    AdminViewReceiptCallback,
    AdminWriteViaBotCallback,
)
from app.bot.keyboards.inline.admin_orders import (
    back_to_order_keyboard,
    cancel_reason_keyboard,
    message_customer_keyboard,
)
from app.bot.services.order_notifications import sync_admin_cards
from app.bot.states.admin import AdminOrderStates
from app.bot.utils.admin_order_card import build_admin_order_keyboard, build_admin_order_text
from app.bot.utils.i18n import translate
from app.bot.utils.messages import require_message
from app.core.exceptions import OrderAlreadyProcessedError, OrderNotFoundError
from app.db.models.admin import Admin
from app.db.models.enums import OrderStatus
from app.db.models.order import Order
from app.db.repositories import admin_repository, user_repository
from app.services import order_service

router = Router(name="admin_orders")

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


async def _require_admin(
    callback: CallbackQuery, admin: Admin | None, translator: Callable[..., str]
) -> bool:
    if admin is None or not admin.is_active:
        await callback.answer(translator("admin.not_admin_alert"), show_alert=True)
        return False
    return True


async def _get_order_or_alert(
    callback: CallbackQuery,
    session: AsyncSession,
    order_id: int,
    translator: Callable[..., str],
) -> Order | None:
    try:
        return await order_service.get_order(session, order_id)
    except OrderNotFoundError:
        await callback.answer(translator("admin.order_not_found"), show_alert=True)
        return None


async def _already_processed_alert(
    callback: CallbackQuery,
    session: AsyncSession,
    order: Order,
    translator: Callable[..., str],
) -> None:
    admin_name = "?"
    if order.processed_by_admin_id:
        processor = await admin_repository.get_by_id(session, order.processed_by_admin_id)
        if processor:
            admin_name = processor.full_name
    await callback.answer(
        translator("admin.already_processed_alert", admin=admin_name), show_alert=True
    )


async def _notify_customer(
    bot: Bot,
    session: AsyncSession,
    order: Order,
    key: str,
    *,
    status_key: str | None = None,
    **kwargs: str,
) -> None:
    customer = await user_repository.get_by_id(session, order.user_id)
    if customer is None:
        return
    translator = partial(translate, customer.language)
    if status_key is not None:
        kwargs["status"] = translator(status_key)
    text = translator(key, order_number=order.order_number, **kwargs)
    with contextlib.suppress(TelegramBadRequest, TelegramForbiddenError):
        await bot.send_message(customer.telegram_id, text)


async def _render_order_card(
    message: Message, session: AsyncSession, order: Order, _: Callable
) -> None:
    customer = await user_repository.get_by_id(session, order.user_id)
    if customer is None:
        return
    await message.edit_text(
        build_admin_order_text(order, customer, translator=_),
        reply_markup=build_admin_order_keyboard(order, translator=_),
    )


# --- Confirm ---


@router.callback_query(AdminConfirmCallback.filter())
async def on_confirm_order(
    callback: CallbackQuery,
    callback_data: AdminConfirmCallback,
    session: AsyncSession,
    admin: Admin | None,
    bot: Bot,
    _: Callable,
) -> None:
    if not await _require_admin(callback, admin, _):
        return
    order = await _get_order_or_alert(callback, session, callback_data.order_id, _)
    if order is None:
        return
    assert admin is not None

    try:
        order = await order_service.confirm_order(session, order, admin_id=admin.id)
    except OrderAlreadyProcessedError:
        await _already_processed_alert(callback, session, order, _)
        return

    await sync_admin_cards(
        bot,
        session,
        order,
        action_key=ACTION_KEY_BY_STATUS[OrderStatus.CONFIRMED],
        admin_name=admin.full_name,
    )
    await _notify_customer(bot, session, order, "orders.confirmed_notification")
    await callback.answer()


# --- Advance status (preparing / delivering / completed) ---


@router.callback_query(AdminAdvanceCallback.filter())
async def on_advance_status(
    callback: CallbackQuery,
    callback_data: AdminAdvanceCallback,
    session: AsyncSession,
    admin: Admin | None,
    bot: Bot,
    _: Callable,
) -> None:
    if not await _require_admin(callback, admin, _):
        return
    order = await _get_order_or_alert(callback, session, callback_data.order_id, _)
    if order is None:
        return
    assert admin is not None

    to_status = OrderStatus(callback_data.to_status)
    try:
        order = await order_service.advance_status(
            session, order, to_status, admin_id=admin.id
        )
    except OrderAlreadyProcessedError:
        await _already_processed_alert(callback, session, order, _)
        return

    await sync_admin_cards(
        bot,
        session,
        order,
        action_key=ACTION_KEY_BY_STATUS[to_status],
        admin_name=admin.full_name,
    )
    await _notify_customer(
        bot,
        session,
        order,
        "orders.status_changed_notification",
        status_key=STATUS_LABEL_KEYS[to_status],
    )
    await callback.answer()


# --- Cancel ---


@router.callback_query(AdminCancelRequestCallback.filter())
async def on_cancel_request(
    callback: CallbackQuery,
    callback_data: AdminCancelRequestCallback,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await _require_admin(callback, admin, _):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    await message.edit_reply_markup(
        reply_markup=cancel_reason_keyboard(callback_data.order_id, _)
    )
    await callback.answer()


@router.callback_query(AdminCancelReasonCallback.filter())
async def on_cancel_reason_selected(
    callback: CallbackQuery,
    callback_data: AdminCancelReasonCallback,
    session: AsyncSession,
    admin: Admin | None,
    bot: Bot,
    state: FSMContext,
    _: Callable,
) -> None:
    if not await _require_admin(callback, admin, _):
        return

    if callback_data.reason == "other":
        message = await require_message(callback, _)
        if message is None:
            return
        await state.set_state(AdminOrderStates.entering_cancel_reason)
        await state.update_data(order_id=callback_data.order_id)
        await message.edit_text(_("admin.cancel_reason_enter_custom"))
        await callback.answer()
        return

    reason_text = _(f"admin.cancel_reason_{callback_data.reason}")
    await _finalize_cancel(
        callback, session, bot, callback_data.order_id, admin, reason_text, _
    )


@router.message(AdminOrderStates.entering_cancel_reason, F.text)
async def on_custom_cancel_reason(
    message: Message,
    session: AsyncSession,
    admin: Admin | None,
    bot: Bot,
    state: FSMContext,
    _: Callable,
) -> None:
    if admin is None or not admin.is_active:
        await state.clear()
        return
    data = await state.get_data()
    order_id = data.get("order_id")
    await state.clear()
    if order_id is None:
        return
    reason_text = (message.text or "").strip() or "-"
    try:
        order = await order_service.get_order(session, order_id)
    except OrderNotFoundError:
        await message.answer(_("admin.order_not_found"))
        return
    order = await order_service.cancel_order(
        session, order, admin_id=admin.id, reason=reason_text
    )
    await sync_admin_cards(
        bot,
        session,
        order,
        action_key=ACTION_KEY_BY_STATUS[OrderStatus.CANCELLED],
        admin_name=admin.full_name,
        reason=reason_text,
    )
    await _notify_customer(
        bot, session, order, "orders.cancelled_notification", reason=reason_text
    )
    await message.answer(
        _("admin.back_button"), reply_markup=back_to_order_keyboard(order_id, _)
    )


async def _finalize_cancel(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    order_id: int,
    admin: Admin | None,
    reason_text: str,
    _: Callable,
) -> None:
    assert admin is not None
    order = await _get_order_or_alert(callback, session, order_id, _)
    if order is None:
        return
    try:
        order = await order_service.cancel_order(
            session, order, admin_id=admin.id, reason=reason_text
        )
    except OrderAlreadyProcessedError:
        await _already_processed_alert(callback, session, order, _)
        return

    await sync_admin_cards(
        bot,
        session,
        order,
        action_key=ACTION_KEY_BY_STATUS[OrderStatus.CANCELLED],
        admin_name=admin.full_name,
        reason=reason_text,
    )
    await _notify_customer(
        bot, session, order, "orders.cancelled_notification", reason=reason_text
    )
    await callback.answer()


# --- Back to order card ---


@router.callback_query(AdminBackToOrderCallback.filter())
async def on_back_to_order(
    callback: CallbackQuery,
    callback_data: AdminBackToOrderCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await _require_admin(callback, admin, _):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    order = await _get_order_or_alert(callback, session, callback_data.order_id, _)
    if order is None:
        return
    await _render_order_card(message, session, order, _)
    await callback.answer()


# --- Message customer ---


@router.callback_query(AdminMessageCustomerCallback.filter())
async def on_message_customer(
    callback: CallbackQuery,
    callback_data: AdminMessageCustomerCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await _require_admin(callback, admin, _):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    order = await _get_order_or_alert(callback, session, callback_data.order_id, _)
    if order is None:
        return
    customer = await user_repository.get_by_id(session, order.user_id)
    if customer is None:
        await callback.answer(_("common.not_found"), show_alert=True)
        return
    await message.edit_reply_markup(
        reply_markup=message_customer_keyboard(
            order.id, customer.telegram_id, customer.username, _
        )
    )
    await callback.answer()


@router.callback_query(AdminWriteViaBotCallback.filter())
async def on_write_via_bot(
    callback: CallbackQuery,
    callback_data: AdminWriteViaBotCallback,
    session: AsyncSession,
    admin: Admin | None,
    state: FSMContext,
    _: Callable,
) -> None:
    if not await _require_admin(callback, admin, _):
        return
    order = await _get_order_or_alert(callback, session, callback_data.order_id, _)
    if order is None:
        return
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(AdminOrderStates.writing_to_customer)
    await state.update_data(order_id=order.id, customer_user_id=order.user_id)
    await message.edit_text(_("admin.enter_message_to_customer"))
    await callback.answer()


@router.message(AdminOrderStates.writing_to_customer, F.text)
async def on_customer_message_entered(
    message: Message,
    session: AsyncSession,
    admin: Admin | None,
    bot: Bot,
    state: FSMContext,
    _: Callable,
) -> None:
    if admin is None or not admin.is_active:
        await state.clear()
        return
    data = await state.get_data()
    order_id = data.get("order_id")
    customer_user_id = data.get("customer_user_id")
    await state.clear()
    if order_id is None or customer_user_id is None:
        return

    customer = await user_repository.get_by_id(session, customer_user_id)
    if customer is None:
        await message.answer(_("common.not_found"))
        return

    translator = partial(translate, customer.language)
    text = translator("admin.message_from_admin_prefix") + (message.text or "")
    with contextlib.suppress(TelegramBadRequest, TelegramForbiddenError):
        await bot.send_message(customer.telegram_id, text)

    await message.answer(
        _("admin.message_sent_to_customer"), reply_markup=back_to_order_keyboard(order_id, _)
    )


# --- Receipt ---


@router.callback_query(AdminViewReceiptCallback.filter())
async def on_view_receipt(
    callback: CallbackQuery,
    callback_data: AdminViewReceiptCallback,
    session: AsyncSession,
    admin: Admin | None,
    bot: Bot,
    _: Callable,
) -> None:
    if not await _require_admin(callback, admin, _):
        return
    order = await _get_order_or_alert(callback, session, callback_data.order_id, _)
    if order is None:
        return
    if not order.receipt_file_id:
        await callback.answer(_("admin.no_receipt"), show_alert=True)
        return

    is_pdf = order.receipt_url is not None and order.receipt_url.endswith(".pdf")
    if callback.message is not None:
        if is_pdf:
            await bot.send_document(callback.message.chat.id, order.receipt_file_id)
        else:
            await bot.send_photo(callback.message.chat.id, order.receipt_file_id)
    await callback.answer()

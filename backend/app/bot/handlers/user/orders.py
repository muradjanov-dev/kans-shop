from collections.abc import Callable
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import OrderDetailCallback, ReorderCallback
from app.bot.keyboards.inline.orders import (
    STATUS_LABEL_KEYS,
    order_detail_keyboard,
    order_list_keyboard,
)
from app.bot.utils.i18n import menu_button_texts
from app.bot.utils.messages import require_message
from app.core.exceptions import OutOfStockError, ProductNotFoundError
from app.db.models.user import User
from app.db.repositories import order_repository
from app.services import cart_service

router = Router(name="orders")

ORDER_HISTORY_LIMIT = 10


def _format_price(price: Decimal) -> str:
    return f"{price:,.0f}".replace(",", " ")


@router.message(StateFilter(None), F.text.in_(menu_button_texts("menu.orders")))
async def open_orders(
    message: Message, session: AsyncSession, user: User, _: Callable
) -> None:
    orders, _total = await order_repository.list_by_user(
        session, user.id, page=1, limit=ORDER_HISTORY_LIMIT
    )
    if not orders:
        await message.answer(_("orders.empty"))
        return
    await message.answer(
        _("orders.title"), reply_markup=order_list_keyboard(orders, translator=_)
    )


@router.callback_query(OrderDetailCallback.filter())
async def on_order_detail(
    callback: CallbackQuery,
    callback_data: OrderDetailCallback,
    session: AsyncSession,
    user: User,
    _: Callable,
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return

    order = await order_repository.get_by_id(session, callback_data.order_id)
    if order is None or order.user_id != user.id:
        await callback.answer(_("common.not_found"), show_alert=True)
        return

    status_label = _(STATUS_LABEL_KEYS[order.status.value])
    lines = [
        _("orders.detail_title", order_number=order.order_number),
        "",
        f"{status_label}",
        "",
    ]
    for idx, item in enumerate(order.items, start=1):
        lines.append(
            _(
                "checkout.summary_item_line",
                index=idx,
                name=item.product_name_snapshot,
                price=_format_price(item.price),
                qty=item.quantity,
                subtotal=_format_price(item.total),
            )
        )
    lines.append("")
    lines.append(_("checkout.summary_total", value=_format_price(order.total)))

    await message.edit_text(
        "\n".join(lines), reply_markup=order_detail_keyboard(order.id, translator=_)
    )
    await callback.answer()


@router.callback_query(ReorderCallback.filter())
async def on_reorder(
    callback: CallbackQuery,
    callback_data: ReorderCallback,
    session: AsyncSession,
    user: User,
    _: Callable,
) -> None:
    order = await order_repository.get_by_id(session, callback_data.order_id)
    if order is None or order.user_id != user.id:
        await callback.answer(_("common.not_found"), show_alert=True)
        return

    added = 0
    for item in order.items:
        if item.product_id is None:
            continue
        try:
            await cart_service.add_item(session, user.id, item.product_id, item.quantity)
            added += 1
        except (OutOfStockError, ProductNotFoundError):
            continue

    if added:
        await callback.answer(_("orders.reorder_done"), show_alert=True)
    else:
        await callback.answer(_("orders.reorder_none"), show_alert=True)

from collections.abc import Callable, Sequence
from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import OrderDetailCallback, ReorderCallback
from app.db.models.order import Order

STATUS_LABEL_KEYS = {
    "new": "orders.status_new",
    "confirmed": "orders.status_confirmed",
    "preparing": "orders.status_preparing",
    "delivering": "orders.status_delivering",
    "completed": "orders.status_completed",
    "cancelled": "orders.status_cancelled",
}


def _format_price(price: Decimal) -> str:
    return f"{price:,.0f}".replace(",", " ")


def order_list_keyboard(
    orders: Sequence[Order], *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        status_label = translator(STATUS_LABEL_KEYS[order.status.value])
        text = translator(
            "orders.list_item",
            order_number=order.order_number,
            status=status_label,
            total=_format_price(order.total),
        )
        builder.row(
            InlineKeyboardButton(
                text=text, callback_data=OrderDetailCallback(order_id=order.id, page=1).pack()
            )
        )
    return builder.as_markup()


def order_detail_keyboard(
    order_id: int, *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("orders.reorder_button"),
            callback_data=ReorderCallback(order_id=order_id).pack(),
        )
    )
    return builder.as_markup()

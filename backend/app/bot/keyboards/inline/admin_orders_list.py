from collections.abc import Callable
from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import (
    AdminBackToOrderCallback,
    AdminMenuCallback,
    AdminOrderFilterCallback,
)
from app.db.models.enums import OrderStatus
from app.db.models.order import Order
from app.services.common import Page

STATUS_FILTERS = ("all", *[s.value for s in OrderStatus])


def _format_price(price: Decimal) -> str:
    return f"{price:,.0f}".replace(",", " ")


def admin_order_list_keyboard(
    page: Page[Order], *, status: str, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    filter_buttons = []
    for status_filter in STATUS_FILTERS:
        label = (
            translator("admin.orders_filter_all")
            if status_filter == "all"
            else translator(f"orders.status_{status_filter}")
        )
        if status_filter == status:
            label = f"• {label}"
        filter_buttons.append(
            InlineKeyboardButton(
                text=label,
                callback_data=AdminOrderFilterCallback(status=status_filter, page=1).pack(),
            )
        )
    for i in range(0, len(filter_buttons), 3):
        builder.row(*filter_buttons[i : i + 3])

    for order in page.items:
        status_label = translator(f"orders.status_{order.status.value}")
        builder.row(
            InlineKeyboardButton(
                text=f"#{order.order_number} — {status_label} — {_format_price(order.total)}",
                callback_data=AdminBackToOrderCallback(order_id=order.id).pack(),
            )
        )

    nav_row = []
    if page.has_prev:
        nav_row.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=AdminOrderFilterCallback(
                    status=status, page=page.page - 1
                ).pack(),
            )
        )
    if page.total:
        nav_row.append(
            InlineKeyboardButton(
                text=translator(
                    "catalog.page_indicator", page=page.page, total_pages=page.total_pages
                ),
                callback_data="noop",
            )
        )
    if page.has_next:
        nav_row.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=AdminOrderFilterCallback(
                    status=status, page=page.page + 1
                ).pack(),
            )
        )
    if nav_row:
        builder.row(*nav_row)

    builder.row(
        InlineKeyboardButton(
            text=translator("admin.back_to_menu"),
            callback_data=AdminMenuCallback(section="menu").pack(),
        )
    )
    return builder.as_markup()

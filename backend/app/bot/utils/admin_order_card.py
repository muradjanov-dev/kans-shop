from collections.abc import Callable
from decimal import Decimal
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import (
    AdminAdvanceCallback,
    AdminCancelRequestCallback,
    AdminConfirmCallback,
    AdminMessageCustomerCallback,
    AdminViewReceiptCallback,
)
from app.core.config import settings
from app.db.models.enums import OrderStatus, OrderType, PaymentMethod
from app.db.models.order import Order
from app.db.models.user import User

ORDER_TYPE_LABEL_KEYS = {
    OrderType.DELIVERY.value: "checkout.type_delivery",
    OrderType.PICKUP.value: "checkout.type_pickup",
    OrderType.PREORDER.value: "checkout.type_preorder",
}


def _format_price(price: Decimal) -> str:
    return f"{price:,.0f}".replace(",", " ")


def build_admin_order_text(
    order: Order,
    customer: User,
    *,
    translator: Callable[..., str],
    processed_line: str | None = None,
) -> str:
    lines = [translator("admin.new_order_title", order_number=order.order_number)]
    if processed_line:
        lines.append(processed_line)
    lines.append(translator("admin.divider"))
    lines.append(translator("admin.customer_label", name=order.customer_name))
    lines.append(translator("admin.phone_label", phone=order.customer_phone))
    username = (
        f"@{customer.username}" if customer.username else translator("admin.no_username")
    )
    lines.append(
        translator("admin.telegram_label", username=username, telegram_id=customer.telegram_id)
    )
    lines.append(
        translator(
            "admin.type_label", value=translator(ORDER_TYPE_LABEL_KEYS[order.order_type.value])
        )
    )
    if order.address:
        lines.append(translator("admin.address_label", value=order.address))
    elif order.latitude is not None:
        lines.append(
            translator("admin.address_label", value=f"{order.latitude}, {order.longitude}")
        )
    if order.comment:
        lines.append(translator("admin.comment_label", value=order.comment))

    lines.append(translator("admin.divider"))
    lines.append(translator("admin.items_header"))
    for idx, item in enumerate(order.items, start=1):
        lines.append(
            translator(
                "admin.item_line",
                index=idx,
                name=item.product_name_snapshot,
                price=_format_price(item.price),
                qty=item.quantity,
                subtotal=_format_price(item.total),
            )
        )

    lines.append(translator("admin.divider"))
    lines.append(translator("admin.subtotal_line", value=_format_price(order.subtotal)))
    if order.order_type == OrderType.DELIVERY:
        lines.append(
            translator("admin.delivery_line", value=_format_price(order.delivery_fee))
        )
    lines.append(translator("admin.total_line", value=_format_price(order.total)))

    method_key = (
        "admin.payment_cash"
        if order.payment_method == PaymentMethod.CASH
        else "admin.payment_card"
    )
    receipt_suffix = (
        translator("admin.receipt_uploaded_suffix") if order.receipt_file_id else ""
    )
    lines.append(
        translator(
            "admin.payment_line", method=translator(method_key), receipt_suffix=receipt_suffix
        )
    )

    local_time = order.created_at.astimezone(ZoneInfo(settings.timezone))
    lines.append(
        translator("admin.timestamp_line", value=local_time.strftime("%d.%m.%Y %H:%M"))
    )
    return "\n".join(lines)


def build_admin_order_keyboard(
    order: Order, *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if order.status == OrderStatus.NEW:
        builder.row(
            InlineKeyboardButton(
                text=translator("admin.confirm_button"),
                callback_data=AdminConfirmCallback(order_id=order.id).pack(),
            ),
            InlineKeyboardButton(
                text=translator("admin.cancel_button"),
                callback_data=AdminCancelRequestCallback(order_id=order.id).pack(),
            ),
        )
    elif order.status == OrderStatus.CONFIRMED:
        builder.row(
            InlineKeyboardButton(
                text=translator("admin.preparing_button"),
                callback_data=AdminAdvanceCallback(
                    order_id=order.id, to_status=OrderStatus.PREPARING.value
                ).pack(),
            ),
            InlineKeyboardButton(
                text=translator("admin.cancel_button"),
                callback_data=AdminCancelRequestCallback(order_id=order.id).pack(),
            ),
        )
    elif order.status == OrderStatus.PREPARING:
        if order.order_type == OrderType.DELIVERY:
            next_status = OrderStatus.DELIVERING
            next_text = translator("admin.delivering_button")
        else:
            next_status = OrderStatus.COMPLETED
            next_text = translator("admin.completed_button")
        builder.row(
            InlineKeyboardButton(
                text=next_text,
                callback_data=AdminAdvanceCallback(
                    order_id=order.id, to_status=next_status.value
                ).pack(),
            ),
            InlineKeyboardButton(
                text=translator("admin.cancel_button"),
                callback_data=AdminCancelRequestCallback(order_id=order.id).pack(),
            ),
        )
    elif order.status == OrderStatus.DELIVERING:
        builder.row(
            InlineKeyboardButton(
                text=translator("admin.completed_button"),
                callback_data=AdminAdvanceCallback(
                    order_id=order.id, to_status=OrderStatus.COMPLETED.value
                ).pack(),
            ),
            InlineKeyboardButton(
                text=translator("admin.cancel_button"),
                callback_data=AdminCancelRequestCallback(order_id=order.id).pack(),
            ),
        )

    utility_row = [
        InlineKeyboardButton(
            text=translator("admin.message_customer_button"),
            callback_data=AdminMessageCustomerCallback(order_id=order.id).pack(),
        )
    ]
    if order.payment_method == PaymentMethod.CARD_TRANSFER and order.receipt_file_id:
        utility_row.append(
            InlineKeyboardButton(
                text=translator("admin.view_receipt_button"),
                callback_data=AdminViewReceiptCallback(order_id=order.id).pack(),
            )
        )
    builder.row(*utility_row)

    return builder.as_markup()

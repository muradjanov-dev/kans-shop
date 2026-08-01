from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.models.enums import OrderStatus, OrderType, PaymentMethod, PaymentStatus


class CheckoutIn(BaseModel):
    order_type: OrderType
    customer_name: str
    customer_phone: str
    payment_method: PaymentMethod = PaymentMethod.CASH
    address: str | None = None
    address_comment: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    comment: str | None = None


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int | None
    product_name_snapshot: str
    product_sku_snapshot: str
    price: Decimal
    quantity: int
    total: Decimal


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    status: OrderStatus
    order_type: OrderType
    customer_name: str
    customer_phone: str
    address: str | None
    address_comment: str | None
    comment: str | None
    subtotal: Decimal
    delivery_fee: Decimal
    discount: Decimal
    total: Decimal
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    receipt_url: str | None
    cancel_reason: str | None
    created_at: datetime
    confirmed_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    items: list[OrderItemOut]

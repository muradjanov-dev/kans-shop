from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.models.enums import OrderStatus, OrderType, PaymentStatus


class OrderHistoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    created_at: datetime
    status: OrderStatus
    payment_status: PaymentStatus
    order_type: OrderType
    total: Decimal


class OrderTimelineEventOut(BaseModel):
    status: OrderStatus
    occurred_at: datetime

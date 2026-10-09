from decimal import Decimal

from pydantic import BaseModel

from app.db.models.enums import OrderType, PaymentMethod


class CheckoutQuoteIn(BaseModel):
    order_type: OrderType
    payment_method: PaymentMethod


class CheckoutQuoteOut(BaseModel):
    subtotal: Decimal
    delivery_fee: Decimal | None
    total: Decimal | None
    payment_methods: list[PaymentMethod]
    ready: bool
    reasons: list[str]
    quote_fingerprint: str | None

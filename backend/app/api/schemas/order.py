from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.bot.utils.helpers import is_valid_uz_phone, normalize_uz_phone
from app.db.models.enums import (
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
)


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
    purchase_contract_version: Literal[1] | None = None
    expected_total: Decimal | None = None
    expected_quote: str | None = None

    @field_validator("customer_name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not 1 <= len(normalized) <= 128:
            raise ValueError("Name must contain 1 to 128 characters")
        return normalized

    @field_validator("customer_phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        normalized = normalize_uz_phone(value)
        if not is_valid_uz_phone(normalized):
            raise ValueError(f"Invalid Uzbek phone number: {value}")
        return normalized

    @model_validator(mode="after")
    def _validate_purchase_contract(self) -> "CheckoutIn":
        has_quote_metadata = self.expected_total is not None or self.expected_quote is not None
        if self.purchase_contract_version is None and has_quote_metadata:
            raise ValueError("Quote metadata requires purchase_contract_version=1")
        if self.purchase_contract_version == 1 and (
            self.expected_total is None or not self.expected_quote
        ):
            raise ValueError(
                "purchase_contract_version=1 requires expected_total and expected_quote"
            )
        return self


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


class LotLinkOut(BaseModel):
    product_name: str
    url: str


class LotLinksOut(BaseModel):
    links: list[LotLinkOut]
    missing: list[str]


class PayIn(BaseModel):
    provider: PaymentProvider


class PayOut(BaseModel):
    payment_url: str

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.api.schemas.catalog import ProductOut
from app.db.models.enums import (
    AdminRole,
    BroadcastStatus,
    BroadcastTarget,
    OrderStatus,
    ProductUnit,
    UserSource,
)


class AdminProductOut(ProductOut):
    barcode: str | None
    sort_order: int


class AdminCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_id: int = Field(gt=0, lt=2**63, strict=True)
    full_name: str = Field(min_length=1, max_length=128)
    role: AdminRole

    @field_validator("full_name")
    @classmethod
    def normalize_admin_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("full_name must not be empty")
        return normalized


class AdminChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=128)
    role: AdminRole | None = None
    is_active: bool | None = Field(default=None, strict=True)
    notifications_enabled: bool | None = Field(default=None, strict=True)

    @field_validator("full_name")
    @classmethod
    def normalize_admin_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("full_name must not be empty")
        return normalized

    @model_validator(mode="after")
    def require_admin_change(self) -> AdminChanges:
        if not self.model_fields_set:
            raise ValueError("at least one admin field must be provided")
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    full_name: str
    role: AdminRole
    is_active: bool
    notifications_enabled: bool
    created_at: datetime


class AdminSessionsRevokedOut(BaseModel):
    revoked_sessions: int = Field(ge=0)


class CategoryCreateIn(BaseModel):
    name_uz: str = Field(min_length=1, max_length=128)
    name_ru: str = Field(min_length=1, max_length=128)
    parent_id: int | None = Field(default=None, ge=1)
    description_uz: str | None = None
    description_ru: str | None = None
    sort_order: int = 0


class CategoryUpdateIn(BaseModel):
    expected_edit_version: int = Field(ge=0)
    parent_id: int | None = Field(default=None, ge=1)
    name_uz: str | None = Field(default=None, min_length=1, max_length=128)
    name_ru: str | None = Field(default=None, min_length=1, max_length=128)
    description_uz: str | None = None
    description_ru: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None

    @model_validator(mode="after")
    def reject_null_category_values(self) -> CategoryUpdateIn:
        for field_name in ("name_uz", "name_ru", "is_active", "sort_order"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class CategoryMoveIn(BaseModel):
    expected_edit_version: int = Field(ge=0)
    parent_id: int | None = Field(ge=1)


class ProductCreateIn(BaseModel):
    category_id: int = Field(ge=1)
    name_uz: str = Field(min_length=1, max_length=255)
    name_ru: str = Field(min_length=1, max_length=255)
    description_uz: str | None = None
    description_ru: str | None = None
    sku: str = Field(min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    price: Decimal = Field(gt=0)
    old_price: Decimal | None = Field(default=None, gt=0)
    stock_qty: int = Field(default=0, ge=0)
    unit: ProductUnit
    min_order_qty: int = Field(default=1, ge=1)
    is_featured: bool = False
    sort_order: int = 0
    lot_url: str | None = Field(default=None, max_length=512)

    @field_validator("lot_url")
    @classmethod
    def validate_lot_url(cls, value: str | None) -> str | None:
        return _https_lot_url(value)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("sku must not be empty")
        return normalized


class ProductUpdateIn(BaseModel):
    expected_edit_version: int = Field(ge=0)
    category_id: int | None = Field(default=None, ge=1)
    name_uz: str | None = Field(default=None, min_length=1, max_length=255)
    name_ru: str | None = Field(default=None, min_length=1, max_length=255)
    description_uz: str | None = None
    description_ru: str | None = None
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    price: Decimal | None = Field(default=None, gt=0)
    old_price: Decimal | None = Field(default=None, gt=0)
    stock_qty: int | None = Field(default=None, ge=0)
    min_order_qty: int | None = Field(default=None, ge=1)
    unit: ProductUnit | None = None
    is_active: bool | None = None
    is_featured: bool | None = None
    sort_order: int | None = None
    lot_url: str | None = Field(default=None, max_length=512)

    @field_validator("lot_url")
    @classmethod
    def validate_lot_url(cls, value: str | None) -> str | None:
        return _https_lot_url(value)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("sku must not be empty")
        return normalized

    @model_validator(mode="after")
    def reject_null_product_values(self) -> ProductUpdateIn:
        for field_name in (
            "category_id",
            "name_uz",
            "name_ru",
            "sku",
            "price",
            "stock_qty",
            "min_order_qty",
            "unit",
            "is_active",
            "is_featured",
            "sort_order",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


def _https_lot_url(value: str | None) -> str | None:
    if value is None:
        return None
    from urllib.parse import urlsplit

    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("lot_url must be an HTTPS URL")
    return value


class AdminOrderStatusUpdateIn(BaseModel):
    status: OrderStatus
    comment: str | None = None


class AdminAcceptPaymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_receipt_version: int = Field(ge=0, strict=True)


class BroadcastCreateIn(BaseModel):
    text: str
    photo_file_id: str | None = None
    button_text: str | None = None
    button_url: str | None = None
    target: BroadcastTarget


class BroadcastOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    photo_file_id: str | None
    button_text: str | None
    button_url: str | None
    target: BroadcastTarget
    status: BroadcastStatus
    sent_count: int
    failed_count: int
    created_at: datetime


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    first_name: str
    last_name: str | None
    phone: str | None
    language: str
    is_blocked: bool
    source: UserSource
    created_at: datetime
    last_active_at: datetime | None


class AdminUserSourceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str


class AdminUserDetail(UserOut):
    orders_count: int
    first_touch_source: AdminUserSourceSummary | None


STORE_SETTING_FIELDS = (
    "delivery_fee",
    "free_delivery_from",
    "min_order_amount",
    "work_hours",
    "card_number",
    "card_holder",
    "support_username",
    "shop_phone",
    "is_shop_open",
    "welcome_text_uz",
    "welcome_text_ru",
)

_STORE_SETTING_NUMERIC_FIELDS = (
    "delivery_fee",
    "free_delivery_from",
    "min_order_amount",
)
_STORE_SETTING_STRING_FIELDS = (
    "work_hours",
    "card_number",
    "card_holder",
    "support_username",
    "shop_phone",
    "welcome_text_uz",
    "welcome_text_ru",
)


class StoreSettingsPatch(BaseModel):
    """Strict delta of persisted store settings plus the version being edited."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(strict=True, ge=0)
    delivery_fee: Decimal | None = Field(default=None, ge=0)
    free_delivery_from: Decimal | None = Field(default=None, ge=0)
    min_order_amount: Decimal | None = Field(default=None, ge=0)
    work_hours: str | None = Field(default=None, max_length=128)
    card_number: str | None = Field(default=None, max_length=64)
    card_holder: str | None = Field(default=None, max_length=128)
    support_username: str | None = Field(default=None, max_length=32)
    shop_phone: str | None = Field(default=None, max_length=20)
    is_shop_open: bool | None = None
    welcome_text_uz: str | None = Field(default=None, max_length=4000)
    welcome_text_ru: str | None = Field(default=None, max_length=4000)

    @field_validator(*_STORE_SETTING_NUMERIC_FIELDS, mode="before")
    @classmethod
    def parse_decimal_strings(cls, value: object) -> Decimal | None:
        if value is None or isinstance(value, Decimal):
            return value
        if not isinstance(value, str):
            raise ValueError("numeric settings must be decimal strings or null")
        try:
            parsed = Decimal(value.strip())
        except (InvalidOperation, ValueError):
            raise ValueError("numeric settings must be decimal strings or null") from None
        if not parsed.is_finite():
            raise ValueError("numeric settings must be finite")
        return parsed

    @field_validator(*_STORE_SETTING_STRING_FIELDS, mode="before")
    @classmethod
    def normalize_optional_strings(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("store settings must be strings or null")
        normalized = value.strip()
        return normalized or None

    @field_validator("support_username")
    @classmethod
    def validate_support_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.removeprefix("@").strip()
        if re.fullmatch(r"[A-Za-z0-9_]{5,32}", normalized) is None:
            raise ValueError("support_username must be a Telegram username")
        return normalized

    @field_validator("shop_phone")
    @classmethod
    def validate_shop_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if (
            not value.startswith("+")
            or not value[1:].isdigit()
            or not 7 <= len(value[1:]) <= 15
        ):
            raise ValueError("shop_phone must be an E.164 phone number")
        if value[1] == "0":
            raise ValueError("shop_phone must be an E.164 phone number")
        return value

    @field_validator("is_shop_open", mode="before")
    @classmethod
    def require_boolean_shop_state(cls, value: object) -> bool | None:
        if value is None or isinstance(value, bool):
            return value
        raise ValueError("is_shop_open must be a boolean or null")


class StoreSettingsSnapshot(BaseModel):
    """Typed, secret-free view of the keys that can be configured by store staff."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0)
    delivery_fee: Decimal | None = Field(ge=0)
    free_delivery_from: Decimal | None = Field(ge=0)
    min_order_amount: Decimal | None = Field(ge=0)
    work_hours: str | None
    card_number: str | None
    card_holder: str | None
    support_username: str | None
    shop_phone: str | None
    is_shop_open: bool | None
    welcome_text_uz: str | None
    welcome_text_ru: str | None
    readiness: dict[str, bool]

    @field_serializer(*_STORE_SETTING_NUMERIC_FIELDS)
    def serialize_decimal_settings(self, value: Decimal | None) -> str | None:
        return str(value) if value is not None else None


class UserBlockIn(BaseModel):
    blocked: bool


class TopProductOut(BaseModel):
    name: str
    sold: int


class StatsOverviewOut(BaseModel):
    period: str
    orders_count: int
    revenue: Decimal
    avg_check: Decimal
    new_users: int
    top_products: list[TopProductOut]


class AdminAuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    actor_admin_id: int | None
    actor_name_snapshot: str | None
    action: str
    resource_type: str
    resource_id: str | None
    request_id: str
    before_json: dict[str, object] | None
    after_json: dict[str, object] | None

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.models.enums import (
    BroadcastStatus,
    BroadcastTarget,
    OrderStatus,
    ProductUnit,
    UserSource,
)


class CategoryCreateIn(BaseModel):
    name_uz: str
    name_ru: str
    parent_id: int | None = None


class CategoryUpdateIn(BaseModel):
    name_uz: str | None = None
    name_ru: str | None = None
    description_uz: str | None = None
    description_ru: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class ProductCreateIn(BaseModel):
    category_id: int
    name_uz: str
    name_ru: str
    description_uz: str | None = None
    description_ru: str | None = None
    sku: str
    price: Decimal
    old_price: Decimal | None = None
    stock_qty: int = 0
    unit: ProductUnit
    min_order_qty: int = 1
    is_featured: bool = False


class ProductUpdateIn(BaseModel):
    category_id: int | None = None
    name_uz: str | None = None
    name_ru: str | None = None
    description_uz: str | None = None
    description_ru: str | None = None
    sku: str | None = None
    price: Decimal | None = None
    old_price: Decimal | None = None
    stock_qty: int | None = None
    unit: ProductUnit | None = None
    is_active: bool | None = None
    is_featured: bool | None = None


class AdminOrderStatusUpdateIn(BaseModel):
    status: OrderStatus
    comment: str | None = None


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

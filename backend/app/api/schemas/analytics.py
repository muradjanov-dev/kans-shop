"""Storefront analytics: the batch the browser posts and what the admin dashboard reads."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AnalyticsPeriod = Literal["today", "week", "month", "quarter"]


# --------------------------------------------------------------------------- collection


class AnalyticsEventIn(BaseModel):
    """One thing a visitor did. Unknown types and malformed fields are dropped, not rejected,
    so an older API never throws away a newer storefront's whole batch."""

    model_config = ConfigDict(extra="ignore")

    type: str = Field(min_length=1, max_length=32)
    at: int | None = Field(default=None, ge=0, description="Client clock, epoch milliseconds")
    path: str | None = Field(default=None, max_length=512)
    section: str | None = Field(default=None, max_length=64)
    target: str | None = Field(default=None, max_length=128)
    label: str | None = Field(default=None, max_length=256)
    product_id: int | None = Field(default=None, gt=0, le=9_223_372_036_854_775_807)
    value: int | None = Field(default=None, ge=0, le=2_000_000_000)


class AnalyticsBatchIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    visitor_id: uuid.UUID
    session_id: uuid.UUID
    sent_at: int | None = Field(default=None, ge=0, description="Client clock, epoch ms")
    platform: Literal["telegram", "web"] = "web"
    device: Literal["mobile", "tablet", "desktop"] = "mobile"
    language: str | None = Field(default=None, max_length=16)
    entry_path: str | None = Field(default=None, max_length=512)
    referrer: str | None = Field(default=None, max_length=512)
    source: str | None = Field(default=None, max_length=128)
    events: list[AnalyticsEventIn] = Field(default_factory=list, max_length=100)


class AnalyticsAcceptedOut(BaseModel):
    accepted: int


# --------------------------------------------------------------------------- dashboard


class CountOut(BaseModel):
    key: str
    count: int


class AmountOut(BaseModel):
    key: str
    count: int
    amount: Decimal


class TimelinePointOut(BaseModel):
    day: date
    visitors: int
    sessions: int
    orders: int
    revenue: Decimal


class SalesSummaryOut(BaseModel):
    orders: int
    revenue: Decimal
    paid_amount: Decimal
    avg_check: Decimal
    items_sold: int
    cancelled: int
    customers: int
    new_customers: int
    returning_customers: int


class AnalyticsSummaryOut(BaseModel):
    period: AnalyticsPeriod
    since: datetime
    until: datetime
    visitors: int
    new_visitors: int
    returning_visitors: int
    signed_in_visitors: int
    sessions: int
    page_views: int
    engaged_seconds: int
    avg_session_seconds: int
    bounce_rate: float
    product_views: int
    cart_adds: int
    conversion_rate: float
    platforms: list[CountOut]
    devices: list[CountOut]
    sources: list[CountOut]
    timeline: list[TimelinePointOut]
    sales: SalesSummaryOut


class SectionStatOut(BaseModel):
    path: str
    section: str
    position: int
    sessions: int
    reach_rate: float
    total_seconds: int
    avg_seconds: float


class PageStatOut(BaseModel):
    path: str
    views: int
    sessions: int
    total_seconds: int
    avg_seconds: float


class ScrollStatOut(BaseModel):
    path: str
    page_views: int
    reached_25: float
    reached_50: float
    reached_75: float
    reached_90: float


class ClickStatOut(BaseModel):
    section: str | None
    target: str | None
    label: str | None
    clicks: int
    sessions: int


class SearchStatOut(BaseModel):
    term: str
    searches: int
    sessions: int
    zero_results: int


class FunnelStepOut(BaseModel):
    key: str
    sessions: int


class AnalyticsBehaviorOut(BaseModel):
    period: AnalyticsPeriod
    sessions: int
    sections: list[SectionStatOut]
    pages: list[PageStatOut]
    scroll: list[ScrollStatOut]
    clicks: list[ClickStatOut]
    funnel: list[FunnelStepOut]
    hours: list[int]
    searches: list[SearchStatOut]
    filters: list[CountOut]
    carousel: list[CountOut]


class ProductInterestOut(BaseModel):
    product_id: int
    name: str
    price: Decimal | None
    image_url: str | None
    impressions: int
    views: int
    viewers: int
    view_seconds: int
    cart_adds: int
    favorites: int
    ordered_qty: int
    revenue: Decimal


class AnalyticsProductsOut(BaseModel):
    period: AnalyticsPeriod
    products: list[ProductInterestOut]
    interested_not_bought: list[ProductInterestOut]


class CustomerActivityOut(BaseModel):
    user_id: int
    name: str
    username: str | None
    phone: str | None
    sessions: int
    engaged_seconds: int
    page_views: int
    first_seen: datetime
    last_seen: datetime
    platform: str
    products_viewed: int
    cart_adds: int
    orders: int
    revenue: Decimal
    interests: list[str]


class AnalyticsCustomersOut(BaseModel):
    period: AnalyticsPeriod
    items: list[CustomerActivityOut]
    total: int
    page: int
    limit: int
    guest_visitors: int
    guest_sessions: int


class CustomerSessionOut(BaseModel):
    started_at: datetime
    last_seen_at: datetime
    engaged_seconds: int
    page_views: int
    platform: str
    device: str
    entry_path: str | None


class CustomerProductOut(BaseModel):
    product_id: int
    name: str
    views: int
    view_seconds: int
    cart_adds: int
    favorites: int
    ordered_qty: int


class CustomerEventOut(BaseModel):
    occurred_at: datetime
    type: str
    path: str | None
    section: str | None
    target: str | None
    label: str | None
    product_name: str | None
    value: int | None


class AnalyticsCustomerDetailOut(BaseModel):
    period: AnalyticsPeriod
    customer: CustomerActivityOut
    sessions: list[CustomerSessionOut]
    products: list[CustomerProductOut]
    searches: list[str]
    events: list[CustomerEventOut]


class HeatCellOut(BaseModel):
    weekday: int
    hour: int
    orders: int


class TopCustomerOut(BaseModel):
    user_id: int
    name: str
    orders: int
    revenue: Decimal


class TopSoldProductOut(BaseModel):
    name: str
    quantity: int
    revenue: Decimal


class AnalyticsSalesOut(BaseModel):
    period: AnalyticsPeriod
    summary: SalesSummaryOut
    statuses: list[AmountOut]
    payment_methods: list[AmountOut]
    order_types: list[AmountOut]
    categories: list[AmountOut]
    top_products: list[TopSoldProductOut]
    top_customers: list[TopCustomerOut]
    heatmap: list[HeatCellOut]
    avg_items_per_order: float

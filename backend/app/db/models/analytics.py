"""Storefront behaviour analytics: one row per browsing session, many events per session.

The storefront batches what a visitor does (pages, sections seen, time spent, clicks,
products looked at, searches) and posts it to `/api/v1/analytics/events`. Sessions carry
the customer once they are signed in, so the admin dashboard can show who was interested
in what. Staff sessions are flagged so the dashboard can leave them out.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import IDMixin, TimestampMixin

ANALYTICS_EVENT_TYPES = (
    "page_view",
    "page_time",
    "section_view",
    "section_time",
    "scroll_depth",
    "click",
    "product_impression",
    "product_view",
    "add_to_cart",
    "favorite_add",
    "favorite_remove",
    "search",
    "filter",
    "carousel",
    "checkout_start",
    "checkout_step",
    "order_placed",
)


class AnalyticsSession(IDMixin, TimestampMixin, Base):
    __tablename__ = "analytics_sessions"
    __table_args__ = (
        CheckConstraint("platform IN ('telegram', 'web')", name="analytics_platform_known"),
        CheckConstraint(
            "device IN ('mobile', 'tablet', 'desktop')", name="analytics_device_known"
        ),
        Index("ix_analytics_sessions_started_at", "started_at"),
        Index("ix_analytics_sessions_last_seen_at", "last_seen_at"),
    )

    # Random ids made by the browser: the session lives 30 idle minutes, the visitor id
    # stays in local storage so returning visitors can be told apart from new ones.
    session_key: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, nullable=False)
    visitor_key: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    is_staff: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    device: Mapped[str] = mapped_column(String(16), nullable=False)
    language: Mapped[str | None] = mapped_column(String(8))
    entry_path: Mapped[str | None] = mapped_column(String(160))
    referrer: Mapped[str | None] = mapped_column(String(160))
    source: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    page_views: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    events_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    engaged_ms: Mapped[int] = mapped_column(BigInteger, server_default="0", nullable=False)

    def __repr__(self) -> str:
        return f"<AnalyticsSession id={self.id} user_id={self.user_id}>"


class AnalyticsEvent(IDMixin, Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_type_occurred_at", "type", "occurred_at"),
        Index("ix_analytics_events_occurred_at", "occurred_at"),
        Index(
            "ix_analytics_events_product_id_occurred_at",
            "product_id",
            "occurred_at",
            postgresql_where=text("product_id IS NOT NULL"),
        ),
    )

    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("analytics_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    path: Mapped[str | None] = mapped_column(String(160))
    section: Mapped[str | None] = mapped_column(String(48))
    target: Mapped[str | None] = mapped_column(String(96))
    label: Mapped[str | None] = mapped_column(String(160))
    product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="SET NULL")
    )
    value: Mapped[int | None] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<AnalyticsEvent id={self.id} type={self.type}>"

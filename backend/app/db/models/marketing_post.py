from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import IDMixin, TimestampMixin


class MarketingPost(IDMixin, TimestampMixin, Base):
    """The daily channel advert: one row per Tashkent calendar day.

    The unique `post_date` is the claim that keeps a restart (or a second worker) from
    publishing twice; a failed day is retried a few times on the same row.
    """

    __tablename__ = "marketing_posts"
    __table_args__ = (
        # The naming convention turns this into ck_marketing_posts_marketing_post_status_known.
        CheckConstraint(
            "status IN ('rendering', 'sent', 'failed')", name="marketing_post_status_known"
        ),
    )

    post_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="rendering")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    product_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False, server_default="[]")
    caption: Mapped[str | None] = mapped_column(Text)
    caption_source: Mapped[str | None] = mapped_column(String(16))
    template_key: Mapped[str | None] = mapped_column(String(64))
    channel_id: Mapped[int | None] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    video_seconds: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<MarketingPost {self.post_date} status={self.status}>"

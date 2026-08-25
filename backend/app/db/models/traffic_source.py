from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import IDMixin, TimestampMixin


class TrafficSource(IDMixin, TimestampMixin, Base):
    """A named campaign behind a `t.me/<bot>?start=src_<code>` deep link, so leads can be
    attributed to where they came from (Instagram, a reseller, a printed QR, ...).

    `clicks_count` counts every /start on the link (including returning users); attribution
    itself lives on `users.traffic_source_id` and is written once, on the user's first contact.
    """

    __tablename__ = "traffic_sources"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    clicks_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)

    def __repr__(self) -> str:
        return f"<TrafficSource id={self.id} code={self.code}>"

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import UserSource, pg_enum
from app.db.models.mixins import IDMixin, TimestampMixin


class User(IDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(2), server_default="uz", nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[UserSource] = mapped_column(
        pg_enum(UserSource, "user_source"),
        server_default=UserSource.BOT.value,
        nullable=False,
    )
    # Which campaign deep link brought this user in — written once, on first contact.
    traffic_source_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("traffic_sources.id", ondelete="SET NULL"),
        index=True,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} telegram_id={self.telegram_id}>"

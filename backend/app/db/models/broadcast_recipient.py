from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import BroadcastRecipientStatus, pg_enum
from app.db.models.mixins import IDMixin, TimestampMixin


class BroadcastRecipient(IDMixin, TimestampMixin, Base):
    __tablename__ = "broadcast_recipients"
    __table_args__ = (
        UniqueConstraint(
            "broadcast_id", "user_id", name="uq_broadcast_recipients_broadcast_user"
        ),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint(
            "(lease_token IS NULL) = (lease_expires_at IS NULL)", name="lease_fields_paired"
        ),
    )

    broadcast_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("broadcasts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[BroadcastRecipientStatus] = mapped_column(
        pg_enum(BroadcastRecipientStatus, "broadcast_recipient_status"),
        server_default=BroadcastRecipientStatus.PENDING.value,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    next_available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(512))

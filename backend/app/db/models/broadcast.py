from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import BroadcastStatus, BroadcastTarget, pg_enum
from app.db.models.mixins import IDMixin, TimestampMixin


class Broadcast(IDMixin, TimestampMixin, Base):
    __tablename__ = "broadcasts"
    __table_args__ = (
        UniqueConstraint(
            "launch_idempotency_key", name="uq_broadcasts_launch_idempotency_key"
        ),
        CheckConstraint(
            "launch_count IS NULL OR launch_count >= 0", name="launch_count_nonnegative"
        ),
        CheckConstraint(
            "launcher_auth_epoch IS NULL OR launcher_auth_epoch >= 0",
            name="launcher_auth_epoch_nonnegative",
        ),
    )

    admin_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    photo_file_id: Mapped[str | None] = mapped_column(String(255))
    photo_storage_key: Mapped[str | None] = mapped_column(String(512))
    button_text: Mapped[str | None] = mapped_column(String(64))
    button_url: Mapped[str | None] = mapped_column(Text)
    preview_content_fingerprint: Mapped[str | None] = mapped_column(String(64))
    target: Mapped[BroadcastTarget] = mapped_column(
        pg_enum(BroadcastTarget, "broadcast_target"), nullable=False
    )
    status: Mapped[BroadcastStatus] = mapped_column(
        pg_enum(BroadcastStatus, "broadcast_status"),
        server_default=BroadcastStatus.DRAFT.value,
        nullable=False,
    )
    sent_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    launch_idempotency_key: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    launch_fingerprint: Mapped[str | None] = mapped_column(String(64))
    launch_count: Mapped[int | None] = mapped_column(Integer)
    launcher_auth_epoch: Mapped[int | None] = mapped_column(Integer)
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Broadcast id={self.id} status={self.status}>"

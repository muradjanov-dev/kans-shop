from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import BroadcastStatus, BroadcastTarget, pg_enum
from app.db.models.mixins import IDMixin, TimestampMixin


class Broadcast(IDMixin, TimestampMixin, Base):
    __tablename__ = "broadcasts"

    admin_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    photo_file_id: Mapped[str | None] = mapped_column(String(255))
    button_text: Mapped[str | None] = mapped_column(String(64))
    button_url: Mapped[str | None] = mapped_column(Text)
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

    def __repr__(self) -> str:
        return f"<Broadcast id={self.id} status={self.status}>"

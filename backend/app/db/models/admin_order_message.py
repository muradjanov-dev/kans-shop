from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.db.models.mixins import IDMixin


class AdminOrderMessage(IDMixin, Base):
    __tablename__ = "admin_order_messages"
    __table_args__ = (
        UniqueConstraint(
            "admin_id",
            "order_id",
            "idempotency_key",
            name="uq_admin_order_messages_admin_order_idempotency_key",
        ),
        CheckConstraint("length(btrim(text)) > 0", name="text_not_blank"),
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    admin_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("admins.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # User-visible private content; application authorization controls access to this field.
    text: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

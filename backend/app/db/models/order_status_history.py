from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import OrderStatus, pg_enum
from app.db.models.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.order import Order


class OrderStatusHistory(IDMixin, TimestampMixin, Base):
    __tablename__ = "order_status_history"

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[OrderStatus | None] = mapped_column(
        pg_enum(OrderStatus, "order_status", create_type=False)
    )
    to_status: Mapped[OrderStatus] = mapped_column(
        pg_enum(OrderStatus, "order_status", create_type=False), nullable=False
    )
    changed_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("admins.id", ondelete="SET NULL")
    )
    comment: Mapped[str | None] = mapped_column(Text)

    order: Mapped["Order"] = relationship("Order", back_populates="status_history")

    def __repr__(self) -> str:
        return (
            f"<OrderStatusHistory id={self.id} order_id={self.order_id} to={self.to_status}>"
        )

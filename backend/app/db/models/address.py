from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import IDMixin, TimestampMixin


class Address(IDMixin, TimestampMixin, Base):
    __tablename__ = "addresses"
    __table_args__ = (
        Index(
            "uq_addresses_user_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default IS TRUE"),
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    address_text: Mapped[str] = mapped_column(Text, nullable=False)
    address_comment: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)

    def __repr__(self) -> str:
        return f"<Address id={self.id} user_id={self.user_id} label={self.label!r}>"

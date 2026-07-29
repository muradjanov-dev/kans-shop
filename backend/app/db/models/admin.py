from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import AdminRole, pg_enum
from app.db.models.mixins import IDMixin, TimestampMixin


class Admin(IDMixin, TimestampMixin, Base):
    __tablename__ = "admins"

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[AdminRole] = mapped_column(pg_enum(AdminRole, "admin_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )

    def __repr__(self) -> str:
        return f"<Admin id={self.id} telegram_id={self.telegram_id} role={self.role}>"

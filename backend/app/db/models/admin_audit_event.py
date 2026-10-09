from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import IDMixin, TimestampMixin


class AdminAuditEvent(IDMixin, TimestampMixin, Base):
    __tablename__ = "admin_audit_events"

    actor_admin_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("admins.id", ondelete="SET NULL"), index=True
    )
    actor_name_snapshot: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128))
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    before_json: Mapped[dict | None] = mapped_column(JSONB)
    after_json: Mapped[dict | None] = mapped_column(JSONB)

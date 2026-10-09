from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import IDMixin, TimestampMixin


class AdminSession(IDMixin, TimestampMixin, Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_admin_sessions_token_hash"),
        UniqueConstraint("csrf_token", name="uq_admin_sessions_csrf_token"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_is_sha256_hex"),
        CheckConstraint("auth_epoch >= 0", name="auth_epoch_nonnegative"),
        CheckConstraint(
            "idle_expires_at <= absolute_expires_at", name="idle_within_absolute_expiry"
        ),
    )

    admin_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("admins.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # This is the SHA-256 digest of the cookie value. The raw bearer cookie is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Independent random nonce returned to the browser for CSRF checks.
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False)
    auth_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

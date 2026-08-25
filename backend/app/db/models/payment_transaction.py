from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import PaymentProvider, PaymentTxState, pg_enum
from app.db.models.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.order import Order


class PaymentTransaction(IDMixin, TimestampMixin, Base):
    """Audit trail of gateway callbacks for a single order. `provider_transaction_id` is the
    gateway's own transaction id (Click's click_trans_id, Payme's id, ...); the unique
    constraint with `provider` makes webhook handling idempotent against duplicate callbacks.
    """

    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_transaction_id", name="uq_payment_tx_provider_tx_id"
        ),
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[PaymentProvider] = mapped_column(
        pg_enum(PaymentProvider, "payment_provider"), nullable=False
    )
    provider_transaction_id: Mapped[str | None] = mapped_column(String(64), index=True)
    state: Mapped[PaymentTxState] = mapped_column(
        pg_enum(PaymentTxState, "payment_tx_state"),
        server_default=PaymentTxState.CREATED.value,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    order: Mapped["Order"] = relationship("Order")

    def __repr__(self) -> str:
        return (
            f"<PaymentTransaction id={self.id} order_id={self.order_id} "
            f"provider={self.provider} state={self.state}>"
        )

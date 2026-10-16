"""add sourcing inventory policy and checkout stock snapshot

Revision ID: 4b9d2ac7e501
Revises: 3a8d0f24c1e6
Create Date: 2026-10-16 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b9d2ac7e501"
down_revision: str | None = "3a8d0f24c1e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("stock_deducted", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.execute(
        """
        INSERT INTO settings (key, value, description)
        VALUES (
            'stock_tracking_enabled',
            'false'::jsonb,
            'Controls public stock visibility and stock deductions at checkout'
        )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    has_untracked_orders = op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM orders WHERE stock_deducted IS FALSE)")
    ).scalar_one()
    if has_untracked_orders:
        raise RuntimeError(
            "Cannot remove orders.stock_deducted while sourcing-mode orders exist; "
            "preserve or migrate their inventory history before downgrading."
        )
    op.drop_column("orders", "stock_deducted")

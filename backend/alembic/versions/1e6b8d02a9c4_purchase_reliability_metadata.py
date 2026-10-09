"""add purchase reliability metadata and cart replay records

Revision ID: 1e6b8d02a9c4
Revises: 9c1f4a7be2d0
Create Date: 2026-10-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1e6b8d02a9c4"
down_revision: str | None = "9c1f4a7be2d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cart_mutations",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("mutation_key", sa.String(length=36), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_cart_mutations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cart_mutations")),
        sa.UniqueConstraint(
            "user_id", "mutation_key", name="uq_cart_mutations_user_mutation_key"
        ),
    )

    op.add_column("orders", sa.Column("checkout_key", sa.String(length=36), nullable=True))
    op.add_column(
        "orders", sa.Column("checkout_fingerprint", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "orders",
        sa.Column(
            "payment_instructions", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        "orders", sa.Column("receipt_storage_key", sa.String(length=512), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("receipt_content_type", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "orders",
        sa.Column("receipt_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "orders",
        sa.Column("payment_reviewed_by_admin_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("payment_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_orders_payment_reviewed_by_admin_id_admins"),
        "orders",
        "admins",
        ["payment_reviewed_by_admin_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_orders_user_checkout_key", "orders", ["user_id", "checkout_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_orders_user_checkout_key", "orders", type_="unique")
    op.drop_constraint(
        op.f("fk_orders_payment_reviewed_by_admin_id_admins"),
        "orders",
        type_="foreignkey",
    )
    op.drop_column("orders", "payment_reviewed_at")
    op.drop_column("orders", "payment_reviewed_by_admin_id")
    op.drop_column("orders", "receipt_version")
    op.drop_column("orders", "receipt_content_type")
    op.drop_column("orders", "receipt_storage_key")
    op.drop_column("orders", "payment_instructions")
    op.drop_column("orders", "checkout_fingerprint")
    op.drop_column("orders", "checkout_key")
    op.drop_table("cart_mutations")

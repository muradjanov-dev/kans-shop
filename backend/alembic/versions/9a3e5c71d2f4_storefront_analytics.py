"""storefront behaviour analytics

Revision ID: 9a3e5c71d2f4
Revises: 6d4c1f2a8b90
Create Date: 2026-10-21 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a3e5c71d2f4"
down_revision: str | None = "6d4c1f2a8b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_key", sa.Uuid(), nullable=False),
        sa.Column("visitor_key", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("is_staff", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("device", sa.String(length=16), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("entry_path", sa.String(length=160), nullable=True),
        sa.Column("referrer", sa.String(length=160), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("page_views", sa.Integer(), server_default="0", nullable=False),
        sa.Column("events_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("engaged_ms", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "platform IN ('telegram', 'web')",
            name=op.f("ck_analytics_sessions_analytics_platform_known"),
        ),
        sa.CheckConstraint(
            "device IN ('mobile', 'tablet', 'desktop')",
            name=op.f("ck_analytics_sessions_analytics_device_known"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_analytics_sessions_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_sessions")),
        sa.UniqueConstraint("session_key", name=op.f("uq_analytics_sessions_session_key")),
    )
    op.create_index(
        "ix_analytics_sessions_started_at", "analytics_sessions", ["started_at"], unique=False
    )
    op.create_index(
        "ix_analytics_sessions_last_seen_at",
        "analytics_sessions",
        ["last_seen_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analytics_sessions_visitor_key"),
        "analytics_sessions",
        ["visitor_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analytics_sessions_user_id"), "analytics_sessions", ["user_id"], unique=False
    )

    op.create_table(
        "analytics_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("path", sa.String(length=160), nullable=True),
        sa.Column("section", sa.String(length=48), nullable=True),
        sa.Column("target", sa.String(length=96), nullable=True),
        sa.Column("label", sa.String(length=160), nullable=True),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("value", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["analytics_sessions.id"],
            name=op.f("fk_analytics_events_session_id_analytics_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_analytics_events_product_id_products"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_events")),
    )
    op.create_index(
        "ix_analytics_events_type_occurred_at",
        "analytics_events",
        ["type", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_events_occurred_at", "analytics_events", ["occurred_at"], unique=False
    )
    op.create_index(
        "ix_analytics_events_product_id_occurred_at",
        "analytics_events",
        ["product_id", "occurred_at"],
        unique=False,
        postgresql_where=sa.text("product_id IS NOT NULL"),
    )
    op.create_index(
        op.f("ix_analytics_events_session_id"), "analytics_events", ["session_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_analytics_events_session_id"), table_name="analytics_events")
    op.drop_index(
        "ix_analytics_events_product_id_occurred_at",
        table_name="analytics_events",
        postgresql_where=sa.text("product_id IS NOT NULL"),
    )
    op.drop_index("ix_analytics_events_occurred_at", table_name="analytics_events")
    op.drop_index("ix_analytics_events_type_occurred_at", table_name="analytics_events")
    op.drop_table("analytics_events")
    op.drop_index(op.f("ix_analytics_sessions_user_id"), table_name="analytics_sessions")
    op.drop_index(op.f("ix_analytics_sessions_visitor_key"), table_name="analytics_sessions")
    op.drop_index("ix_analytics_sessions_last_seen_at", table_name="analytics_sessions")
    op.drop_index("ix_analytics_sessions_started_at", table_name="analytics_sessions")
    op.drop_table("analytics_sessions")

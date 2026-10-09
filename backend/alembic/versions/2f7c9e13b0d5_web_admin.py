"""add persistence for the web admin

Revision ID: 2f7c9e13b0d5
Revises: 1e6b8d02a9c4
Create Date: 2026-10-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f7c9e13b0d5"
down_revision: str | None = "1e6b8d02a9c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admins", sa.Column("auth_epoch", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "products", sa.Column("edit_version", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "categories",
        sa.Column("edit_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("broadcasts", sa.Column("photo_storage_key", sa.String(length=512)))

    # Existing broadcast status values and rows remain intact; this only widens the enum.
    op.execute("ALTER TYPE broadcast_status ADD VALUE IF NOT EXISTS 'cancelled'")
    op.execute(
        "CREATE TYPE notification_outbox_status AS ENUM "
        "('pending', 'sending', 'sent', 'failed')"
    )
    op.execute(
        "CREATE TYPE broadcast_recipient_status AS ENUM "
        "('pending', 'sending', 'sent', 'failed', 'cancelled')"
    )
    notification_status = postgresql.ENUM(
        "pending", "sending", "sent", "failed", name="notification_outbox_status", create_type=False
    )
    recipient_status = postgresql.ENUM(
        "pending",
        "sending",
        "sent",
        "failed",
        "cancelled",
        name="broadcast_recipient_status",
        create_type=False,
    )

    op.create_table(
        "admin_sessions",
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token", sa.String(length=128), nullable=False),
        sa.Column("auth_epoch", sa.Integer(), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_admin_sessions_token_hash_is_sha256_hex"),
        ),
        sa.CheckConstraint(
            "auth_epoch >= 0", name=op.f("ck_admin_sessions_auth_epoch_nonnegative")
        ),
        sa.CheckConstraint(
            "idle_expires_at <= absolute_expires_at",
            name=op.f("ck_admin_sessions_idle_within_absolute_expiry"),
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["admins.id"],
            name=op.f("fk_admin_sessions_admin_id_admins"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_sessions")),
        sa.UniqueConstraint("csrf_token", name=op.f("uq_admin_sessions_csrf_token")),
        sa.UniqueConstraint("token_hash", name="uq_admin_sessions_token_hash"),
    )
    op.create_index(op.f("ix_admin_sessions_admin_id"), "admin_sessions", ["admin_id"])

    op.create_table(
        "admin_audit_events",
        sa.Column("actor_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128)),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["actor_admin_id"],
            ["admins.id"],
            name=op.f("fk_admin_audit_events_actor_admin_id_admins"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit_events")),
    )
    op.create_index(
        op.f("ix_admin_audit_events_actor_admin_id"),
        "admin_audit_events",
        ["actor_admin_id"],
    )

    op.create_table(
        "notification_outbox",
        sa.Column("recipient_user_id", sa.BigInteger(), nullable=True),
        sa.Column("recipient_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("payload_id", sa.String(length=128)),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("status", notification_status, server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_token", sa.String(length=64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(length=512)),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "(recipient_user_id IS NOT NULL) <> (recipient_admin_id IS NOT NULL)",
            name=op.f("ck_notification_outbox_exactly_one_recipient"),
        ),
        sa.CheckConstraint(
            "attempts >= 0", name=op.f("ck_notification_outbox_attempts_nonnegative")
        ),
        sa.CheckConstraint(
            "(lease_token IS NULL) = (lease_expires_at IS NULL)",
            name=op.f("ck_notification_outbox_lease_fields_paired"),
        ),
        sa.ForeignKeyConstraint(
            ["recipient_admin_id"],
            ["admins.id"],
            name=op.f("fk_notification_outbox_recipient_admin_id_admins"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name=op.f("fk_notification_outbox_recipient_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_outbox")),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe_key"),
    )
    op.create_index(
        op.f("ix_notification_outbox_recipient_admin_id"),
        "notification_outbox",
        ["recipient_admin_id"],
    )
    op.create_index(
        op.f("ix_notification_outbox_recipient_user_id"),
        "notification_outbox",
        ["recipient_user_id"],
    )
    op.create_index(
        op.f("ix_notification_outbox_next_available_at"),
        "notification_outbox",
        ["next_available_at"],
    )

    op.create_table(
        "admin_order_messages",
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "length(btrim(text)) > 0", name=op.f("ck_admin_order_messages_text_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["admins.id"],
            name=op.f("fk_admin_order_messages_admin_id_admins"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_admin_order_messages_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_order_messages")),
        sa.UniqueConstraint(
            "admin_id",
            "order_id",
            "idempotency_key",
            name="uq_admin_order_messages_admin_order_idempotency_key",
        ),
    )
    op.create_index(
        op.f("ix_admin_order_messages_admin_id"), "admin_order_messages", ["admin_id"]
    )
    op.create_index(
        op.f("ix_admin_order_messages_order_id"), "admin_order_messages", ["order_id"]
    )

    op.create_table(
        "broadcast_recipients",
        sa.Column("broadcast_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", recipient_status, server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_token", sa.String(length=64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(length=512)),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "attempts >= 0", name=op.f("ck_broadcast_recipients_attempts_nonnegative")
        ),
        sa.CheckConstraint(
            "(lease_token IS NULL) = (lease_expires_at IS NULL)",
            name=op.f("ck_broadcast_recipients_lease_fields_paired"),
        ),
        sa.ForeignKeyConstraint(
            ["broadcast_id"],
            ["broadcasts.id"],
            name=op.f("fk_broadcast_recipients_broadcast_id_broadcasts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_broadcast_recipients_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broadcast_recipients")),
        sa.UniqueConstraint(
            "broadcast_id", "user_id", name="uq_broadcast_recipients_broadcast_user"
        ),
    )
    op.create_index(
        op.f("ix_broadcast_recipients_broadcast_id"),
        "broadcast_recipients",
        ["broadcast_id"],
    )
    op.create_index(
        op.f("ix_broadcast_recipients_user_id"), "broadcast_recipients", ["user_id"]
    )
    op.create_index(
        op.f("ix_broadcast_recipients_next_available_at"),
        "broadcast_recipients",
        ["next_available_at"],
    )

    op.create_table(
        "store_state",
        sa.Column("id", sa.Integer(), server_default="1", autoincrement=False, nullable=False),
        sa.Column("settings_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_store_state_singleton_id")),
        sa.CheckConstraint(
            "settings_version >= 0", name=op.f("ck_store_state_settings_version_nonnegative")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_store_state")),
    )
    op.execute("INSERT INTO store_state (id, settings_version) VALUES (1, 0)")


def downgrade() -> None:
    op.drop_table("store_state")

    op.drop_index(op.f("ix_broadcast_recipients_next_available_at"), table_name="broadcast_recipients")
    op.drop_index(op.f("ix_broadcast_recipients_user_id"), table_name="broadcast_recipients")
    op.drop_index(op.f("ix_broadcast_recipients_broadcast_id"), table_name="broadcast_recipients")
    op.drop_table("broadcast_recipients")

    op.drop_index(op.f("ix_admin_order_messages_order_id"), table_name="admin_order_messages")
    op.drop_index(op.f("ix_admin_order_messages_admin_id"), table_name="admin_order_messages")
    op.drop_table("admin_order_messages")

    op.drop_index(
        op.f("ix_notification_outbox_next_available_at"), table_name="notification_outbox"
    )
    op.drop_index(
        op.f("ix_notification_outbox_recipient_user_id"), table_name="notification_outbox"
    )
    op.drop_index(
        op.f("ix_notification_outbox_recipient_admin_id"), table_name="notification_outbox"
    )
    op.drop_table("notification_outbox")

    op.drop_index(
        op.f("ix_admin_audit_events_actor_admin_id"), table_name="admin_audit_events"
    )
    op.drop_table("admin_audit_events")

    op.drop_index(op.f("ix_admin_sessions_admin_id"), table_name="admin_sessions")
    op.drop_table("admin_sessions")

    op.drop_column("broadcasts", "photo_storage_key")
    op.drop_column("categories", "edit_version")
    op.drop_column("products", "edit_version")
    op.drop_column("admins", "auth_epoch")

    op.execute("DROP TYPE broadcast_recipient_status")
    op.execute("DROP TYPE notification_outbox_status")

    # PostgreSQL cannot remove one enum label. Recreate the original enum and map cancelled
    # records to failed so a downgrade remains possible after a cancellation was recorded.
    op.execute("UPDATE broadcasts SET status = 'failed' WHERE status::text = 'cancelled'")
    op.execute("ALTER TABLE broadcasts ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE broadcast_status RENAME TO broadcast_status_with_cancelled")
    op.execute(
        "CREATE TYPE broadcast_status AS ENUM ('draft', 'sending', 'completed', 'failed')"
    )
    op.execute(
        "ALTER TABLE broadcasts ALTER COLUMN status TYPE broadcast_status "
        "USING status::text::broadcast_status"
    )
    op.execute("ALTER TABLE broadcasts ALTER COLUMN status SET DEFAULT 'draft'")
    op.execute("DROP TYPE broadcast_status_with_cancelled")

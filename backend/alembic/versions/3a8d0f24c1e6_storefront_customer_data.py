"""add customer profile names and saved addresses

Revision ID: 3a8d0f24c1e6
Revises: 2f7c9e13b0d5
Create Date: 2026-10-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a8d0f24c1e6"
down_revision: str | None = "2f7c9e13b0d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=128), nullable=True))
    op.execute("""
        UPDATE users
        SET display_name = left(COALESCE(
            NULLIF(concat_ws(
                ' ',
                NULLIF(regexp_replace(
                    coalesce(first_name, ''),
                    '^[[:space:]]+|[[:space:]]+$', '', 'g'
                ), ''),
                NULLIF(regexp_replace(
                    coalesce(last_name, ''),
                    '^[[:space:]]+|[[:space:]]+$', '', 'g'
                ), '')
            ), ''),
            NULLIF(regexp_replace(
                coalesce(username, ''),
                '^[[:space:]]+|[[:space:]]+$', '', 'g'
            ), ''),
            'Foydalanuvchi'
        ), 128)
        """)
    op.alter_column(
        "users",
        "display_name",
        existing_type=sa.String(length=128),
        server_default="Foydalanuvchi",
        nullable=False,
    )

    op.create_table(
        "addresses",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("address_text", sa.Text(), nullable=False),
        sa.Column("address_comment", sa.Text()),
        sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_addresses_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_addresses")),
    )
    op.create_index(op.f("ix_addresses_user_id"), "addresses", ["user_id"])
    op.create_index(
        "uq_addresses_user_default",
        "addresses",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_addresses_user_default", table_name="addresses")
    op.drop_index(op.f("ix_addresses_user_id"), table_name="addresses")
    op.drop_table("addresses")
    op.drop_column("users", "display_name")

"""daily channel advert posts

Revision ID: 6d4c1f2a8b90
Revises: 4b9d2ac7e501
Create Date: 2026-10-20 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d4c1f2a8b90"
down_revision: str | None = "4b9d2ac7e501"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "marketing_posts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("post_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="rendering", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "product_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("caption_source", sa.String(length=16), nullable=True),
        sa.Column("template_key", sa.String(length=64), nullable=True),
        sa.Column("channel_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("video_seconds", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('rendering', 'sent', 'failed')",
            name=op.f("ck_marketing_posts_marketing_post_status_known"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_marketing_posts")),
        sa.UniqueConstraint("post_date", name=op.f("uq_marketing_posts_post_date")),
    )


def downgrade() -> None:
    op.drop_table("marketing_posts")

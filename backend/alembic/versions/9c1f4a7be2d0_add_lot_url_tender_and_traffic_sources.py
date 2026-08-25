"""add product.lot_url, tender payment method and traffic_sources

Revision ID: 9c1f4a7be2d0
Revises: 54d226ca08b4
Create Date: 2026-08-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9c1f4a7be2d0'
down_revision: Union[str, None] = '54d226ca08b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres forbids using a value added by ALTER TYPE ... ADD VALUE in the same
    # transaction, so this must be the first statement of its own migration step
    # (same pattern as 54d226ca08b4 for 'paynet').
    op.execute("ALTER TYPE payment_method ADD VALUE IF NOT EXISTS 'tender'")

    op.add_column('products', sa.Column('lot_url', sa.String(length=512), nullable=True))

    op.create_table(
        'traffic_sources',
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('clicks_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_traffic_sources')),
    )
    op.create_index(op.f('ix_traffic_sources_code'), 'traffic_sources', ['code'], unique=True)

    op.add_column('users', sa.Column('traffic_source_id', sa.BigInteger(), nullable=True))
    op.create_index(
        op.f('ix_users_traffic_source_id'), 'users', ['traffic_source_id'], unique=False
    )
    op.create_foreign_key(
        op.f('fk_users_traffic_source_id_traffic_sources'),
        'users',
        'traffic_sources',
        ['traffic_source_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f('fk_users_traffic_source_id_traffic_sources'), 'users', type_='foreignkey'
    )
    op.drop_index(op.f('ix_users_traffic_source_id'), table_name='users')
    op.drop_column('users', 'traffic_source_id')

    op.drop_index(op.f('ix_traffic_sources_code'), table_name='traffic_sources')
    op.drop_table('traffic_sources')

    op.drop_column('products', 'lot_url')
    # Postgres has no ALTER TYPE ... DROP VALUE — 'tender' is left on payment_method rather
    # than rebuilding the enum type, keeping downgrade non-destructive.

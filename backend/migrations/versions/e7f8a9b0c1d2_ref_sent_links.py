"""pozycje zamówień (REF) z SAP i powiązania SENT

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-07-08 10:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'order_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('order_number', sa.String(length=60), nullable=False),
        sa.Column('position', sa.String(length=20), nullable=False),
        sa.Column('material', sa.String(length=120), nullable=False),
        sa.Column('description', sa.String(length=300), nullable=False),
        sa.Column('quantity', sa.String(length=40), nullable=False),
        sa.Column('unit', sa.String(length=20), nullable=False),
        sa.Column('net_weight', sa.String(length=30), nullable=False),
        sa.Column('gross_weight', sa.String(length=30), nullable=False),
        sa.Column('volume', sa.String(length=30), nullable=False),
        sa.Column('volume_unit', sa.String(length=20), nullable=False),
        sa.Column('planned_ship_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'order_number', 'position'),
    )
    op.create_index(op.f('ix_order_items_company_id'), 'order_items', ['company_id'])
    op.create_index(op.f('ix_order_items_order_number'), 'order_items', ['order_number'])
    op.create_table(
        'sent_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('sent_number', sa.String(length=120), nullable=False),
        sa.Column('order_number', sa.String(length=60), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sent_links_company_id'), 'sent_links', ['company_id'])
    op.create_index(op.f('ix_sent_links_order_number'), 'sent_links', ['order_number'])


def downgrade() -> None:
    op.drop_table('sent_links')
    op.drop_table('order_items')

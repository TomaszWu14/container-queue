"""Zamówienia specjalnej troski: tabela customer_orders.

Revision ID: care001
Revises: special001
Create Date: 2026-09-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'care001'
# łańcuch po freight001 (#412), nie special001 — inaczej dwie głowy alembica na main
down_revision: Union[str, Sequence[str], None] = 'freight001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'customer_orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('customer_name', sa.String(length=200), nullable=False, server_default=''),
        sa.Column('order_refs', sa.Text(), nullable=False, server_default=''),
        sa.Column('deadline', sa.Date(), nullable=True),
        sa.Column('max_etd', sa.Date(), nullable=True),
        sa.Column('buffer_days', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('responsible_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('alert_on_delay', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_customer_orders_company_id', 'customer_orders', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_customer_orders_company_id', table_name='customer_orders')
    op.drop_table('customer_orders')

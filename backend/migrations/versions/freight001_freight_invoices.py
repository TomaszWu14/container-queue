"""Faktury transportowe BL: freight_invoices + m2m freight_invoice_containers.

Revision ID: freight001
Revises: special001
Create Date: 2026-09-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'freight001'
down_revision: Union[str, Sequence[str], None] = 'special001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'freight_invoices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('bl_number', sa.String(length=80), nullable=False, server_default=''),
        sa.Column('invoice_number', sa.String(length=80), nullable=False, server_default=''),
        sa.Column('forwarder_id', sa.Integer(), sa.ForeignKey('forwarders.id'), nullable=True),
        sa.Column('amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='EUR'),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('filename', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('stored_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('content_type', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('uploaded_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_freight_invoices_company_id', 'freight_invoices', ['company_id'])
    op.create_table(
        'freight_invoice_containers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('freight_invoices.id'), nullable=False),
        sa.Column('container_id', sa.Integer(), sa.ForeignKey('containers.id'), nullable=False),
        sa.UniqueConstraint('invoice_id', 'container_id'),
    )
    op.create_index('ix_freight_invoice_containers_invoice_id',
                    'freight_invoice_containers', ['invoice_id'])
    op.create_index('ix_freight_invoice_containers_container_id',
                    'freight_invoice_containers', ['container_id'])


def downgrade() -> None:
    op.drop_table('freight_invoice_containers')
    op.drop_index('ix_freight_invoices_company_id', table_name='freight_invoices')
    op.drop_table('freight_invoices')

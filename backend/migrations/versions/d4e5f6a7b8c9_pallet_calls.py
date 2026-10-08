"""Wywołania-DLT: tabele powerbi_tokens, pallet_stock_cache, product_paz,
pallet_calls, pallet_call_lines.

Revision ID: d4e5f6a7b8c9
Revises: a7b8c9d0e1f2
Create Date: 2026-08-05
"""
import sqlalchemy as sa
from alembic import op

revision = 'd4e5f6a7b8c9'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None

_STATUS = ('draft', 'sent', 'confirmed', 'cancelled')


def upgrade() -> None:
    op.create_table(
        'powerbi_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cache', sa.Text(), nullable=False, server_default=''),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_table(
        'pallet_stock_cache',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('discrepancies', sa.Text(), nullable=False, server_default='[]'),
    )
    op.create_table(
        'product_paz',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('produkt', sa.String(length=60), nullable=False),
        sa.Column('sztuk_na_palete', sa.Numeric(14, 3), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_product_paz_produkt', 'product_paz', ['produkt'], unique=True)
    status_enum = sa.Enum(*_STATUS, name='palletcallstatus')
    op.create_table(
        'pallet_calls',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'),
                  nullable=False),
        sa.Column('number', sa.String(length=30), nullable=False),
        sa.Column('status', status_enum, nullable=False, server_default='draft'),
        sa.Column('needed_by', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('company_id', 'number', name='uq_pallet_calls_company_number'),
    )
    op.create_index('ix_pallet_calls_company_id', 'pallet_calls', ['company_id'])
    op.create_table(
        'pallet_call_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pallet_call_id', sa.Integer(),
                  sa.ForeignKey('pallet_calls.id', ondelete='CASCADE'), nullable=False),
        sa.Column('produkt', sa.String(length=60), nullable=False),
        sa.Column('krotki_opis', sa.String(length=200), nullable=False, server_default=''),
        sa.Column('ilosc_pal', sa.Numeric(14, 3), nullable=False, server_default='0'),
        sa.Column('data_dostawy', sa.Date(), nullable=True),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
    )
    op.create_index('ix_pallet_call_lines_pallet_call_id', 'pallet_call_lines',
                    ['pallet_call_id'])


def downgrade() -> None:
    op.drop_index('ix_pallet_call_lines_pallet_call_id', 'pallet_call_lines')
    op.drop_table('pallet_call_lines')
    op.drop_index('ix_pallet_calls_company_id', 'pallet_calls')
    op.drop_table('pallet_calls')
    op.drop_index('ix_product_paz_produkt', 'product_paz')
    op.drop_table('product_paz')
    op.drop_table('pallet_stock_cache')
    op.drop_table('powerbi_tokens')
    sa.Enum(name='palletcallstatus').drop(op.get_bind(), checkfirst=True)

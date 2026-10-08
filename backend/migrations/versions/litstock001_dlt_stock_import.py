"""Import stanów DLT z xlsx: tabela dlt_stock (fallback gdy Power BI ich nie podaje).

Revision ID: litstock001
Revises: w14sec2fa001
Create Date: 2026-09-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'litstock001'
down_revision: Union[str, Sequence[str], None] = 'w14sec2fa001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dlt_stock',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('produkt', sa.String(length=60), nullable=False),
        sa.Column('hu', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('ilosc', sa.Numeric(14, 3), nullable=False, server_default='0'),
        sa.Column('lokalizacja', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('source_file', sa.String(length=200), nullable=False, server_default=''),
        sa.Column('imported_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_dlt_stock_produkt', 'dlt_stock', ['produkt'])


def downgrade() -> None:
    op.drop_index('ix_dlt_stock_produkt', table_name='dlt_stock')
    op.drop_table('dlt_stock')

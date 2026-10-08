"""Wywołania-DLT: auta (4×33 miejsca), HU i palety ułamkowe na liniach,
cele pokrycia zapasu (dni) per materiał.

Revision ID: a1b2c3d4e5f7
Revises: e6f1a2b3c4d5
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, Sequence[str], None] = 'e6f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pallet_call_trucks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pallet_call_id', sa.Integer(),
                  sa.ForeignKey('pallet_calls.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('capacity', sa.Integer(), nullable=False, server_default='33'),
        sa.UniqueConstraint('pallet_call_id', 'ordinal', name='uq_pallet_call_truck'),
    )
    op.create_table(
        'material_stock_targets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('material_no', sa.String(length=60), nullable=False, unique=True),
        sa.Column('days', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.add_column('pallet_call_lines',
                  sa.Column('truck_id', sa.Integer(),
                            sa.ForeignKey('pallet_call_trucks.id'), nullable=True))
    op.add_column('pallet_call_lines',
                  sa.Column('hu_numbers', sa.Text(), nullable=False, server_default=''))
    op.add_column('pallet_call_lines',
                  sa.Column('pallets', sa.Numeric(7, 3), nullable=True))


def downgrade() -> None:
    op.drop_column('pallet_call_lines', 'pallets')
    op.drop_column('pallet_call_lines', 'hu_numbers')
    op.drop_column('pallet_call_lines', 'truck_id')
    op.drop_table('material_stock_targets')
    op.drop_table('pallet_call_trucks')

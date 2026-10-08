"""Kongestia portów: dzienny licznik naszych statków na redzie per port.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f7
Create Date: 2026-09-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'port_congestion',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('port', sa.String(length=40), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('waiting', sa.Integer(), nullable=False),
        sa.UniqueConstraint('port', 'day'),
    )
    op.create_index('ix_port_congestion_port', 'port_congestion', ['port'])


def downgrade() -> None:
    op.drop_index('ix_port_congestion_port', table_name='port_congestion')
    op.drop_table('port_congestion')

"""vessel_port_calls — historia wejść/wyjść statku z portów (#31)

Revision ID: a3b4c5d6e7f8
Revises: de45fa67bc89
Create Date: 2026-09-08 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'de45fa67bc89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'vessel_port_calls',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('vessel_id', sa.Integer(), sa.ForeignKey('tracked_vessels.id'),
                  nullable=False),
        sa.Column('port', sa.String(40), nullable=False),
        sa.Column('arrived_at', sa.DateTime(), nullable=False),
        sa.Column('departed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_vessel_port_calls_vessel_id', 'vessel_port_calls', ['vessel_id'])


def downgrade() -> None:
    op.drop_index('ix_vessel_port_calls_vessel_id', table_name='vessel_port_calls')
    op.drop_table('vessel_port_calls')

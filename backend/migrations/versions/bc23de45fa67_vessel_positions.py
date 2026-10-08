"""vessel_positions — historia pozycji AIS (linia przebyta na mapie)

Revision ID: bc23de45fa67
Revises: ab12cd34ef56
Create Date: 2026-09-08 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'bc23de45fa67'
down_revision: Union[str, Sequence[str], None] = 'ab12cd34ef56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'vessel_positions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('vessel_id', sa.Integer(), sa.ForeignKey('tracked_vessels.id'),
                  nullable=False),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lon', sa.Float(), nullable=False),
        sa.Column('at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_vessel_positions_vessel_id', 'vessel_positions', ['vessel_id'])


def downgrade() -> None:
    op.drop_index('ix_vessel_positions_vessel_id', table_name='vessel_positions')
    op.drop_table('vessel_positions')

"""tracked_vessels — pozycje statków z AIS (aisstream.io)

Revision ID: ab12cd34ef56
Revises: c1d2e3f4a5b6
Create Date: 2026-09-08 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'ab12cd34ef56'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tracked_vessels',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=160), nullable=False, unique=True),
        sa.Column('mmsi', sa.Integer(), nullable=True, unique=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lon', sa.Float(), nullable=True),
        sa.Column('sog', sa.Float(), nullable=True),
        sa.Column('cog', sa.Float(), nullable=True),
        sa.Column('destination', sa.String(length=80), nullable=False, server_default=''),
        sa.Column('ais_eta', sa.DateTime(), nullable=True),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_tracked_vessels_mmsi', 'tracked_vessels', ['mmsi'])


def downgrade() -> None:
    op.drop_index('ix_tracked_vessels_mmsi', table_name='tracked_vessels')
    op.drop_table('tracked_vessels')

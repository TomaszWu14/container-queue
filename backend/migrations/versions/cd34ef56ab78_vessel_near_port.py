"""tracked_vessels.near_port — geofence portowy z AIS

Revision ID: cd34ef56ab78
Revises: bc23de45fa67
Create Date: 2026-09-08 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'cd34ef56ab78'
down_revision: Union[str, Sequence[str], None] = 'bc23de45fa67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tracked_vessels', sa.Column('near_port', sa.String(length=40),
                                               nullable=False, server_default=''))
    op.add_column('tracked_vessels', sa.Column('near_port_since', sa.DateTime(),
                                               nullable=True))


def downgrade() -> None:
    op.drop_column('tracked_vessels', 'near_port_since')
    op.drop_column('tracked_vessels', 'near_port')

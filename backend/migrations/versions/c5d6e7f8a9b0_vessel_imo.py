"""tracked_vessels.imo — numer IMO z AIS ShipStaticData

Revision ID: c5d6e7f8a9b0
Revises: a3b4c5d6e7f8
Create Date: 2026-09-08 19:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, Sequence[str], None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tracked_vessels', sa.Column('imo', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('tracked_vessels', 'imo')

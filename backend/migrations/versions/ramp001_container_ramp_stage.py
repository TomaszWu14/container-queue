"""D9: etap rampy jako drugi wymiar kontenera (Container.ramp_stage, nullable).

Revision ID: ramp001
Revises: totpstep001
Create Date: 2026-09-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'ramp001'
down_revision: Union[str, Sequence[str], None] = 'totpstep001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('containers', sa.Column('ramp_stage', sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column('containers', 'ramp_stage')

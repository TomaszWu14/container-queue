"""przewoźnicy: flaga aktywności (dezaktywacja zamiast usuwania)

Revision ID: c7d8e9f0a1b2
Revises: f1a2b3c4d5e6
Create Date: 2026-07-13 23:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # jedyny słownik bez is_active — pozostałe (porty, dostawcy, spedytorzy...) już go mają.
    # server_default=1: istniejący przewoźnicy zostają aktywni.
    op.add_column('carriers', sa.Column('is_active', sa.Boolean(create_constraint=False),
                                        nullable=False, server_default=sa.text('true')))


def downgrade() -> None:
    op.drop_column('carriers', 'is_active')

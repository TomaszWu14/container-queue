"""data wyboru zwycięzcy (chosen_at) — poprawne przypisanie kosztów/statystyk do miesiąca

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-07-10 16:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e0f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transport_jobs', sa.Column('chosen_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('transport_jobs', 'chosen_at')

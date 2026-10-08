"""Powód śledzenia kontenera: containers.special_reason + special_note.

Revision ID: special001
Revises: litstock001
Create Date: 2026-09-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'special001'
down_revision: Union[str, Sequence[str], None] = 'litstock001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('containers', sa.Column('special_reason', sa.String(length=40), nullable=True))
    op.add_column('containers', sa.Column('special_note', sa.Text(), nullable=False,
                                          server_default=''))


def downgrade() -> None:
    op.drop_column('containers', 'special_note')
    op.drop_column('containers', 'special_reason')

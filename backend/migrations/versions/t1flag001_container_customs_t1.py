"""Znacznik T1 tranzytu celnego poza portem: Container.customs_t1.

Revision ID: t1flag001
Revises: care001
Create Date: 2026-09-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 't1flag001'
down_revision: Union[str, Sequence[str], None] = 'frontmodel001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('containers', sa.Column(
        'customs_t1', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('containers', 'customs_t1')

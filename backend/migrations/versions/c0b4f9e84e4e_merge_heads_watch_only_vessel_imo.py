"""merge heads: watch_only + vessel_imo

Revision ID: c0b4f9e84e4e
Revises: a3f7c2e91b04, c5d6e7f8a9b0
Create Date: 2026-09-09 07:56:24.048454

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c0b4f9e84e4e'
down_revision: Union[str, Sequence[str], None] = ('a3f7c2e91b04', 'c5d6e7f8a9b0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

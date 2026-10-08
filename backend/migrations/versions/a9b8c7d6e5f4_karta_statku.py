"""karta statku: zdjęcie i wymiary statku (AIS) + flaga „specjalny" kontenera

Revision ID: a9b8c7d6e5f4
Revises: d7e8f9a0b1c3
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("tracked_vessels", sa.Column("length_m", sa.Integer(), nullable=True))
    op.add_column("tracked_vessels", sa.Column("beam_m", sa.Integer(), nullable=True))
    op.add_column("tracked_vessels",
                  sa.Column("photo", sa.String(255), nullable=False, server_default=""))
    op.add_column("containers",
                  sa.Column("is_special", sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("containers", "is_special")
    op.drop_column("tracked_vessels", "photo")
    op.drop_column("tracked_vessels", "beam_m")
    op.drop_column("tracked_vessels", "length_m")

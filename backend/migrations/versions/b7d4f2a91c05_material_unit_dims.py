"""material_units — wymiary jednostki z MARM (LAENG/BREIT/HOEH + MEABM)

Revision ID: b7d4f2a91c05
Revises: a1c2e3f4b5d6
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7d4f2a91c05'
down_revision: Union[str, Sequence[str], None] = 'a1c2e3f4b5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("material_units", sa.Column("length", sa.Numeric(14, 3), nullable=True))
    op.add_column("material_units", sa.Column("width", sa.Numeric(14, 3), nullable=True))
    op.add_column("material_units", sa.Column("height", sa.Numeric(14, 3), nullable=True))
    op.add_column("material_units", sa.Column(
        "dimension_unit", sa.String(10), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("material_units", "dimension_unit")
    op.drop_column("material_units", "height")
    op.drop_column("material_units", "width")
    op.drop_column("material_units", "length")

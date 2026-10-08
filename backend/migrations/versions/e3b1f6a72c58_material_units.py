"""material_units — jednostki alternatywne materiałów z eksportu SAP MARM

Revision ID: e3b1f6a72c58
Revises: d5a2b8e31c47
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e3b1f6a72c58'
down_revision: Union[str, Sequence[str], None] = 'd5a2b8e31c47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("material_no", sa.String(60), nullable=False),
        sa.Column("unit", sa.String(10), nullable=False),
        sa.Column("numerator", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("denominator", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("volume", sa.Numeric(14, 4), nullable=True),
        sa.Column("volume_unit", sa.String(10), nullable=False, server_default=""),
        sa.Column("gross_weight", sa.Numeric(14, 3), nullable=True),
        sa.Column("weight_unit", sa.String(10), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("material_no", "unit", name="uq_material_unit"),
    )
    op.create_index("ix_material_units_material_no", "material_units", ["material_no"])


def downgrade() -> None:
    op.drop_table("material_units")

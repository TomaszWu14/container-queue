"""container_ports — słownik portów kontenerowych (warstwa mapy trackingu)

Revision ID: a9c2e4f61b03
Revises: e3b1f6a72c58
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a9c2e4f61b03'
down_revision: Union[str, Sequence[str], None] = 'e3b1f6a72c58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "container_ports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(10), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False, server_default=""),
        sa.Column("country_name", sa.String(80), nullable=False, server_default=""),
        sa.Column("lat", sa.Numeric(9, 4), nullable=True),
        sa.Column("lon", sa.Numeric(9, 4), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("container_ports")

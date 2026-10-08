"""port_transit_times — sezonowy (miesięczny) transit time portów

Revision ID: a1c7d4e90b26
Revises: b7e4c1a90f32
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c7d4e90b26"
down_revision: Union[str, Sequence[str], None] = "b7e4c1a90f32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "port_transit_times",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("port_id", sa.Integer(), sa.ForeignKey("ports.id"), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.UniqueConstraint("port_id", "month", name="uq_port_transit_times_port_month"),
    )
    op.create_index("ix_port_transit_times_port_id", "port_transit_times", ["port_id"])


def downgrade() -> None:
    op.drop_index("ix_port_transit_times_port_id", table_name="port_transit_times")
    op.drop_table("port_transit_times")

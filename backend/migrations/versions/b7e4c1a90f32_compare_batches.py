"""compare_batches — paczki faktur wysłane do Compare (DocCompare)

Revision ID: b7e4c1a90f32
Revises: c3f8a1d7e924
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e4c1a90f32"
down_revision: Union[str, Sequence[str], None] = "c3f8a1d7e924"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "compare_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("container_id", sa.Integer(), sa.ForeignKey("containers.id"), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("supplier_code", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirmed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("jobs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("attachment_id", sa.Integer(), sa.ForeignKey("attachments.id"), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_compare_batches_container_id", "compare_batches", ["container_id"])


def downgrade() -> None:
    op.drop_index("ix_compare_batches_container_id", table_name="compare_batches")
    op.drop_table("compare_batches")

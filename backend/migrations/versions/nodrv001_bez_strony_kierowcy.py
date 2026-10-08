"""Bez publicznej strony kierowcy /dostawa/ (decyzja 2026-10-07: nic bez logowania) —
drop driver_links. SMS do kierowcy zostaje (sms_messages), ale bez linku.

Revision ID: nodrv001
Revises: nolink001
"""
import sqlalchemy as sa
from alembic import op

revision = "nodrv001"
down_revision = "nolink001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("driver_links")


def downgrade() -> None:
    op.create_table(
        "driver_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("container_id", sa.Integer(), sa.ForeignKey("containers.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(), nullable=True),
    )

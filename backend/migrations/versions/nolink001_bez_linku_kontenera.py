"""Bez publicznego linku „mój kontener” /k/ (decyzja 2026-10-07: odbiorcy nie mają żadnych
podglądów, nic bez logowania) — drop container_share_links.

Revision ID: nolink001
Revises: nocust001
"""
import sqlalchemy as sa
from alembic import op

revision = "nolink001"
down_revision = "nocust001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("container_share_links")


def downgrade() -> None:
    op.create_table(
        "container_share_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("container_id", sa.Integer(), sa.ForeignKey("containers.id"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_container_share_links_token", "container_share_links", ["token"], unique=True)
    op.create_index("ix_container_share_links_container_id", "container_share_links",
                    ["container_id"], unique=True)

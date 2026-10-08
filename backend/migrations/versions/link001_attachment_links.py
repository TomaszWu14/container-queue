"""Wspólny plik dla kilku kontenerów (spec 2026-10-06 decyzja 24): attachment_links.

Revision ID: link001
Revises: intake001
"""
import sqlalchemy as sa
from alembic import op

revision = "link001"
down_revision = "intake001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachment_links",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("attachment_id", sa.Integer,
                  sa.ForeignKey("attachments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("container_id", sa.Integer, sa.ForeignKey("containers.id"), nullable=False),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("attachment_id", "container_id", name="uq_attachment_links"),
    )
    op.create_index("ix_attachment_links_attachment_id", "attachment_links", ["attachment_id"])
    op.create_index("ix_attachment_links_container_id", "attachment_links", ["container_id"])


def downgrade() -> None:
    op.drop_index("ix_attachment_links_container_id", "attachment_links")
    op.drop_index("ix_attachment_links_attachment_id", "attachment_links")
    op.drop_table("attachment_links")

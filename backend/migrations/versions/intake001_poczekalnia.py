"""Poczekalnia dokumentów (spec 2026-10-06 §2): intake_batches + intake_items.

Revision ID: intake001
Revises: nodrv001
"""
import sqlalchemy as sa
from alembic import op

revision = "intake001"
down_revision = "nodrv001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intake_batches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("container_id", sa.Integer, sa.ForeignKey("containers.id"), nullable=False),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
    )
    op.create_index("ix_intake_batches_container_id", "intake_batches", ["container_id"])
    op.create_table(
        "intake_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("batch_id", sa.Integer,
                  sa.ForeignKey("intake_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stored_name", sa.String(255), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("page_from", sa.Integer, nullable=False),
        sa.Column("page_to", sa.Integer, nullable=False),
        sa.Column("pages", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("doc_type", sa.String(12), nullable=False),
        sa.Column("target_container_id", sa.Integer, sa.ForeignKey("containers.id"), nullable=True),
        sa.Column("gate_status", sa.String(12), nullable=False),
        sa.Column("gate_message", sa.Text, nullable=False),
        sa.Column("found_containers", sa.JSON, nullable=False),
        sa.Column("decision", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_intake_items_batch_id", "intake_items", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_intake_items_batch_id", table_name="intake_items")
    op.drop_table("intake_items")
    op.drop_index("ix_intake_batches_container_id", table_name="intake_batches")
    op.drop_table("intake_batches")

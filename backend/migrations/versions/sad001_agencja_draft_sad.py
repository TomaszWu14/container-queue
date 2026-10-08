"""Agencja celna: potwierdzenie odbioru paczki faktur i wersjonowane drafty SAD.

Revision ID: sad001
Revises: spmat001
"""
import sqlalchemy as sa
from alembic import op

revision = "sad001"
down_revision = "spmat001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agency_acks",
        sa.Column("batch_id", sa.Integer,
                  sa.ForeignKey("invoice_batches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("acked_at", sa.DateTime, nullable=False),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("acked_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "sad_drafts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("batch_id", sa.Integer,
                  sa.ForeignKey("invoice_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("attachment_id", sa.Integer, sa.ForeignKey("attachments.id"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("decision", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("comment", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("decided_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("batch_id", "version", name="uq_sad_drafts_batch_version"),
        sa.UniqueConstraint("batch_id", "sha256", name="uq_sad_drafts_batch_sha"),
    )
    op.create_index("ix_sad_drafts_batch_id", "sad_drafts", ["batch_id"])
    op.create_index("ix_sad_drafts_attachment_id", "sad_drafts", ["attachment_id"])


def downgrade() -> None:
    op.drop_index("ix_sad_drafts_attachment_id", table_name="sad_drafts")
    op.drop_index("ix_sad_drafts_batch_id", table_name="sad_drafts")
    op.drop_table("sad_drafts")
    op.drop_table("agency_acks")

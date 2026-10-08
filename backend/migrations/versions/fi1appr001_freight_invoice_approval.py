"""freight_invoice approval — obieg akceptacji faktur transportowych (#42)

Revision ID: fi1appr001
Revises: gr1recv001
Create Date: 2026-09-22
"""
import sqlalchemy as sa
from alembic import op

revision = "fi1appr001"
down_revision = "gr1recv001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("freight_invoices",
                  sa.Column("status", sa.String(20), nullable=False, server_default="NOWA"))
    op.add_column("freight_invoices",
                  sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("freight_invoices",
                  sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.add_column("freight_invoices",
                  sa.Column("approval_note", sa.String(300), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("freight_invoices", "approval_note")
    op.drop_column("freight_invoices", "approved_at")
    op.drop_column("freight_invoices", "approved_by_id")
    op.drop_column("freight_invoices", "status")

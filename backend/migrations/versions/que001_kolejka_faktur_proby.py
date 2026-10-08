"""Kolejka faktur w tle: invoice_jobs.processing_started_at + attempts.

Zestaw „WGRANE” wisiał bez informacji (czeka? liczy? przerwany restartem?). Teraz widać start
przetwarzania, a przerwane 2× przechodzi w błąd z przyczyną zamiast wracać do kolejki bez końca.

Revision ID: que001
Revises: bull001
"""
import sqlalchemy as sa
from alembic import op

revision = "que001"
down_revision = "bull001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("invoice_jobs") as b:
        b.add_column(sa.Column("processing_started_at", sa.DateTime, nullable=True))
        b.add_column(sa.Column("attempts", sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("invoice_jobs") as b:
        b.drop_column("attempts")
        b.drop_column("processing_started_at")

"""Skrót sha256 wgranych plików: attachments + invoice_jobs (spec 2026-10-06 §4 pkt 14–17, 40).

Dubel = ten sam skrót w kontenerze — w załącznikach ALBO w paczce faktur (oba kanały naraz).
Unikalność (kontener, skrót) w załącznikach zamyka wyścig dwóch równoległych wgrań. Stare
wiersze zostają z NULL (bez przeliczania plików w migracji) — bramka porównuje je jak dotąd.

Revision ID: sha001
Revises: que001
"""
import sqlalchemy as sa
from alembic import op

revision = "sha001"
down_revision = "que001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("attachments") as b:
        b.add_column(sa.Column("sha256", sa.String(64), nullable=True))
        b.create_unique_constraint("uq_attachments_container_sha", ["container_id", "sha256"])
    with op.batch_alter_table("invoice_jobs") as b:
        b.add_column(sa.Column("sha256", sa.String(64), nullable=True))
        b.create_index("ix_invoice_jobs_sha256", ["sha256"])


def downgrade() -> None:
    with op.batch_alter_table("invoice_jobs") as b:
        b.drop_index("ix_invoice_jobs_sha256")
        b.drop_column("sha256")
    with op.batch_alter_table("attachments") as b:
        b.drop_constraint("uq_attachments_container_sha", type_="unique")
        b.drop_column("sha256")

"""Odbiorcy bez dostępu do aplikacji (decyzja 2026-10-07, spec dokumenty-dostaw §4 pkt 25):
usunięty portal kliencki (customer_share_links) i flaga pliku attachments.client_visible.
Słownik klientów i customer_id kontenera zostają — to znacznik do śledzenia wewnętrznego.

Revision ID: nocust001
Revises: sha001
"""
import sqlalchemy as sa
from alembic import op

revision = "nocust001"
down_revision = "sha001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("customer_share_links")
    with op.batch_alter_table("attachments") as b:
        b.drop_column("client_visible")


def downgrade() -> None:
    with op.batch_alter_table("attachments") as b:
        b.add_column(sa.Column("client_visible", sa.Boolean, nullable=False, server_default=sa.false()))
    op.create_table(
        "customer_share_links",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("deactivated_at", sa.DateTime, nullable=True),
    )

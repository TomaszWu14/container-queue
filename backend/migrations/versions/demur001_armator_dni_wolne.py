"""Dni wolne od demurrage per armator (decyzja 2026-09-28).

Revision ID: demur001
Revises: sales001
"""
import sqlalchemy as sa
from alembic import op

revision = "demur001"
down_revision = "sales001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("carriers", sa.Column("demurrage_free_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("carriers", "demurrage_free_days")

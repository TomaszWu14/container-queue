"""Draft SAD: dane odczytane z PDF i wynik porównania z fakturami (JSON).

Revision ID: sad002
Revises: sad001
"""
import sqlalchemy as sa
from alembic import op

revision = "sad002"
down_revision = "sad001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sad_drafts", sa.Column("parsed", sa.JSON, nullable=True))
    op.add_column("sad_drafts", sa.Column("comparison", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("sad_drafts", "comparison")
    op.drop_column("sad_drafts", "parsed")

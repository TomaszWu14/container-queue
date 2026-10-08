"""EAN jednostki z eksportu MARM (EAN11) — kolumna material_units.ean.

Revision ID: marmean001
Revises: typed001
"""
import sqlalchemy as sa
from alembic import op

revision = "marmean001"
down_revision = "typed001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("material_units", sa.Column("ean", sa.String(20), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("material_units", "ean")

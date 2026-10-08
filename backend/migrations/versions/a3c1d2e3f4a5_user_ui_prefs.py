"""users.ui_prefs — profil widoku UI per user (JSON w Text)

Revision ID: a3c1d2e3f4a5
Revises: c0b4f9e84e4e
Create Date: 2026-09-10
"""
import sqlalchemy as sa
from alembic import op

revision = "a3c1d2e3f4a5"
down_revision = "c0b4f9e84e4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column(
        "ui_prefs", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("users", "ui_prefs")

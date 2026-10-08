"""container sync_baseline

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
"""
import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("containers", sa.Column("sync_baseline", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("containers", "sync_baseline")

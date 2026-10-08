"""refresh_tokens.revoked_at — okno łaski dla wyścigu rotacji refresh tokenów

Revision ID: a1c2e3f4b5d6
Revises: a9c2e4f61b03
Create Date: 2026-09-18
"""
import sqlalchemy as sa
from alembic import op

revision = "a1c2e3f4b5d6"
down_revision = "a9c2e4f61b03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("revoked_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("refresh_tokens", "revoked_at")

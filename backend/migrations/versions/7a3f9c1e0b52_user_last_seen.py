"""users.last_seen — znacznik ostatniej aktywności (status „online")

Revision ID: 7a3f9c1e0b52
Revises: 9f1e7a2c4d60
Create Date: 2026-07-17
"""
import sqlalchemy as sa
from alembic import op

revision = '7a3f9c1e0b52'
down_revision = '9f1e7a2c4d60'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('last_seen', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'last_seen')

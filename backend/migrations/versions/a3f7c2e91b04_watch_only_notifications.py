"""Powiadomienia tylko-o-obserwowanych: users.watch_only_notifications

Kolumna Boolean (domyślnie False — zachowanie bez zmian dla istniejących kont).

Revision ID: a3f7c2e91b04
Revises: f9a0b1c2d3e4
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = 'a3f7c2e91b04'
down_revision = 'f9a0b1c2d3e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column(
        'watch_only_notifications', sa.Boolean(), server_default=sa.text('false'),
        nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'watch_only_notifications')

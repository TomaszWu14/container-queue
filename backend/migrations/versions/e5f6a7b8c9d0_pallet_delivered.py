"""Wywołania-DLT: status 'delivered' w enum palletcallstatus.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-05
"""
from alembic import op

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # ADD VALUE nie może działać w bloku transakcji; commit bieżącej transakcji
        op.execute('COMMIT')
        op.execute("ALTER TYPE palletcallstatus ADD VALUE IF NOT EXISTS 'delivered'")
    # sqlite/inne: enum trzymany jako VARCHAR — brak zmiany schematu


def downgrade() -> None:
    # PostgreSQL nie wspiera usuwania wartości z enum — no-op (bez utraty danych)
    pass

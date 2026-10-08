"""Główny transport kontenera: tryby morski i lotniczy (TransportType).

Revision ID: morlot001
Revises: kontrole001
"""
from alembic import op

revision = "morlot001"
down_revision = "kontrole001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # ADD VALUE nie może działać w bloku transakcji; commit bieżącej transakcji
        op.execute("COMMIT")
        op.execute("ALTER TYPE transporttype ADD VALUE IF NOT EXISTS 'morski'")
        op.execute("ALTER TYPE transporttype ADD VALUE IF NOT EXISTS 'lotniczy'")
    # sqlite/inne: enum trzymany jako VARCHAR — brak zmiany schematu


def downgrade() -> None:
    # PostgreSQL nie wspiera usuwania wartości z enum — no-op (bez utraty danych)
    pass

"""Status odprawy ZWOLNIONY (SAD-PW: towar zwolniony, można wydać) — między ODPRAWIONY
a ROZLICZONY (spec 2026-10-01-kafelki-dokumentow).

Revision ID: zwol001
Revises: sad003
"""
from alembic import op

revision = "zwol001"
down_revision = "sad003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite trzyma enum jako tekst (bez CHECK) — nic do zrobienia; PostgreSQL: wartość typu
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE customsstatus ADD VALUE IF NOT EXISTS 'ZWOLNIONY' AFTER 'ODPRAWIONY'")


def downgrade() -> None:
    # PostgreSQL nie wspiera DROP VALUE dla enuma — wartość zostaje w typie (nieszkodliwe)
    pass

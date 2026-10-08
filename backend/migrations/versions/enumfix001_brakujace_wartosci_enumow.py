"""Brakujące wartości natywnych enumów PG (audyt DB-001).

Kod zapisuje `role.customs` (konto agencji celnej), `customsstatus.ROZLICZONY` i
`quotestatus.WYGASLA`, ale żadna migracja ich nie dodała — na świeżym PostgreSQL te
akcje kończyły się 500 (`invalid input value for enum`). SQLite: no-op.

Revision ID: enumfix001
Revises: demur001
Create Date: 2026-09-28
"""
from alembic import op

revision = 'enumfix001'
down_revision = 'demur001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != 'postgresql':
        return
    # jak sales001/etapy001: ADD VALUE w transakcji jest OK na PG 12+, dopóki nowej wartości nie
    # używamy w tej samej transakcji; IF NOT EXISTS = idempotentnie (prod mógł ją już mieć)
    op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'customs'")
    op.execute("ALTER TYPE customsstatus ADD VALUE IF NOT EXISTS 'ROZLICZONY' AFTER 'ODPRAWIONY'")
    op.execute("ALTER TYPE quotestatus ADD VALUE IF NOT EXISTS 'WYGASLA'")


def downgrade() -> None:
    # PostgreSQL nie wspiera DROP VALUE dla enuma — wartości zostają (nieszkodliwe)
    pass

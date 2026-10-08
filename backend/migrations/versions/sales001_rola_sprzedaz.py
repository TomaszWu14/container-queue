"""Rola `sales` (sprzedaż) — decyzja usera 2026-09-27.

Tylko odczyt: kolejka, karta kontenera, kalendarz awizacji, śledzenie statków,
Specjalna troska (podgląd, pole „Odpowiedzialny”); bez kosztów. Zakres w deps.py.

Revision ID: sales001
Revises: kartoteka001
Create Date: 2026-09-27
"""
from alembic import op

revision = 'sales001'
down_revision = 'kartoteka001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # nowa wartość enuma — idempotentnie; nieużywana w tej transakcji (bezpieczne na PG 12+)
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'sales'")


def downgrade() -> None:
    # PostgreSQL nie wspiera DROP VALUE dla enuma — wartość zostaje w typie (nieszkodliwe)
    pass

"""Etapy procesu (2026-09-24): nowe statusy kontenera W_PRODUKCJI (etap 2) i
TRANSPORT_WSTEPNY (etap 3, pre-carriage) między ZAPOWIEDZIANY a W_TRANSPORCIE.

Postgres: natywny typ enum `containerstatus` — ADD VALUE z pozycją (kolejność typu =
kolejność procesu). SQLite: kolumna to VARCHAR bez CHECK — nic do zrobienia.
Downgrade: Postgres nie usuwa wartości z enuma; kontenery w nowych statusach wracają
do ZAPOWIEDZIANY, a wartości zostają w typie (nieszkodliwe).

Revision ID: etapy001
Revises: ramp001
"""
from alembic import op

revision = "etapy001"
down_revision = "ramp001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TYPE containerstatus ADD VALUE IF NOT EXISTS 'W_PRODUKCJI' AFTER 'ZAPOWIEDZIANY'")
    op.execute("ALTER TYPE containerstatus ADD VALUE IF NOT EXISTS 'TRANSPORT_WSTEPNY' AFTER 'W_PRODUKCJI'")


def downgrade() -> None:
    op.execute("UPDATE containers SET status = 'ZAPOWIEDZIANY' "
               "WHERE status IN ('W_PRODUKCJI', 'TRANSPORT_WSTEPNY')")

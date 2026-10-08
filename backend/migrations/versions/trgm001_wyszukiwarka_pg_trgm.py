"""Wyszukiwarka z podpowiedziami (2026-09-24): pg_trgm + indeksy GIN pod ILIKE '%…%'
i similarity() po numerze kontenera, PO, statku i nazwie dostawcy.

Tylko Postgres (SQLite w testach/dev nie ma pg_trgm — endpoint używa tam samego ILIKE).
pg_trgm jest rozszerzeniem „trusted" (PG13+) — tworzy je właściciel bazy. Gdyby rola nie
miała prawa, całość w SAVEPOINT: migracja przechodzi, wyszukiwarka działa bez indeksów.

Revision ID: trgm001
Revises: etapy001
"""
import logging

from alembic import op

revision = "trgm001"
down_revision = "etapy001"
branch_labels = None
depends_on = None

_INDEXES = {
    "ix_containers_no_trgm": "containers (container_no gin_trgm_ops)",
    "ix_containers_orders_trgm": "containers (order_numbers gin_trgm_ops)",
    "ix_containers_vessel_trgm": "containers (vessel gin_trgm_ops)",
    "ix_suppliers_name_trgm": "suppliers (name gin_trgm_ops)",
}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    try:
        with bind.begin_nested():
            bind.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            for name, target in _INDEXES.items():
                bind.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS {name} ON {target} USING gin")
    except Exception as exc:  # noqa: BLE001 — brak uprawnień ≠ zatrzymany deploy
        logging.getLogger("alembic").warning("pg_trgm niedostępne, pomijam indeksy: %s", exc)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for name in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")

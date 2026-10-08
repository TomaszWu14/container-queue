"""Poprawka trgm001 (audyt DB-002): pg_trgm + 4 indeksy GIN pod wyszukiwarkę.

trgm001 miał `... ON t (kol gin_trgm_ops) USING gin` (USING musi być PRZED listą kolumn)
i łapał każdy wyjątek, więc na prod nie powstało ani rozszerzenie, ani żaden indeks,
a routers/search.py (`_has_trgm`) wyłączał ranking. Tu błąd SQL zatrzymuje migrację;
jedyny świadomy wyjątek to brak pg_trgm w instalacji Postgresa (ostrzeżenie w logu).

Tylko Postgres — SQLite (testy/dev) dostaje zwykłe indeksy z modeli przez create_all.

Revision ID: trgm002
Revises: enumfix001
"""
import logging

from alembic import op

revision = "trgm002"
down_revision = "enumfix001"
branch_labels = None
depends_on = None

# nazwa -> (tabela, kolumna); te same co w trgm001 i w modelach (Container, Supplier)
_INDEXES = {
    "ix_containers_no_trgm": ("containers", "container_no"),
    "ix_containers_orders_trgm": ("containers", "order_numbers"),
    "ix_containers_vessel_trgm": ("containers", "vessel"),
    "ix_suppliers_name_trgm": ("suppliers", "name"),
}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    available = bind.exec_driver_sql(
        "SELECT 1 FROM pg_available_extensions WHERE name = 'pg_trgm'").scalar()
    if not available:
        logging.getLogger("alembic").warning(
            "pg_trgm niedostępne w tej instalacji Postgresa — pomijam indeksy wyszukiwarki")
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, (table, column) in _INDEXES.items():
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin ({column} gin_trgm_ops)")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for name in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")

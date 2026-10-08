"""Brakujące indeksy (A1/A2/A6): FK scope + status celny + kalendarz + historia audytu.

Na PostgreSQL zakładane przez CREATE INDEX CONCURRENTLY (bez blokady zapisów) —
poza transakcją (autocommit_block). Na SQLite (dev/testy) zwykłe CREATE INDEX.
Wszystko idempotentne (if_not_exists / if_exists), bo bootstrap create_all może
utworzyć te same indeksy z deklaracji modeli.

Revision ID: d1e2f3a4b5c6
Revises: b2c4d6e8f0a1
Create Date: 2026-07-19
"""
from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "b2c4d6e8f0a1"
branch_labels = None
depends_on = None

# (nazwa, tabela, kolumny) — nazwy zgodne z auto-nazwami SQLAlchemy z modeli
_INDEXES = [
    ("ix_containers_order_id", "containers", ["order_id"]),
    ("ix_containers_forwarder_id", "containers", ["forwarder_id"]),
    ("ix_containers_customs_status", "containers", ["customs_status"]),
    ("ix_containers_wh_notify", "containers", ["warehouse_id", "notify_date"]),
    ("ix_audit_entity", "audit_log", ["entity_type", "entity_id", "created_at"]),
]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        # CONCURRENTLY nie może działać w transakcji — autocommit_block ją zawiesza
        with op.get_context().autocommit_block():
            for name, table, cols in _INDEXES:
                op.create_index(name, table, cols, unique=False,
                                postgresql_concurrently=True, if_not_exists=True)
    else:
        for name, table, cols in _INDEXES:
            op.create_index(name, table, cols, unique=False, if_not_exists=True)


def downgrade() -> None:
    if _is_postgres():
        with op.get_context().autocommit_block():
            for name, table, _cols in reversed(_INDEXES):
                op.drop_index(name, table_name=table,
                              postgresql_concurrently=True, if_exists=True)
    else:
        for name, table, _cols in reversed(_INDEXES):
            op.drop_index(name, table_name=table, if_exists=True)

"""DB-010 + PERF-007: indeksy kluczy obcych na ścieżkach filtrów/kasowania + trigramy ?q=.

DB-010 — Postgres nie indeksuje FK sam. Tu tylko FK z realnych ścieżek (reszta z 59 z
`audit/sql/db_fk_bez_indeksu.sql` to `*_by_id` do users, których nikt nie kasuje — konto
jest anonimizowane — decyzja po `pg_stat_user_tables.seq_scan`, P-03):
  - containers.supplier_id, orders.supplier_id, invoice_batches.supplier_id — filtr/profil
    dostawcy, scalanie dostawców,
  - notifications.container_id, watched_containers.container_id — `_purge_containers`
    odpina/kasuje po tych kolumnach, a FK check przy DELETE kontenera skanuje je per wiersz,
  - invoice_batches.attachment_id, attachment_suggestions.attachment_id — FK check przy
    kasowaniu załączników (ta sama ścieżka kasowania kontenera),
  - avizo_requests.company_id (scope spółki), audit_log.user_id (filtr „kto zmienił”).

PERF-007 — pole ?q= kolejki to OR po 6 kolumnach; trgm002 dał GIN tylko 3 z nich, więc
każda gałąź bez indeksu (notes, transport_id, orders.number) wymuszała Seq Scan całej
tabeli. Tu brakujące GIN pg_trgm (tylko PG; brak pg_trgm w instalacji = ostrzeżenie, jak
trgm002). Router szuka po orders/suppliers przez `fk = ANY(ARRAY(podzapytanie))`
(containers_common.fk_matches), dzięki czemu cały OR łączy się w BitmapOr.

Postgres: CREATE INDEX CONCURRENTLY (bez blokady zapisów; audit_log i notifications to
największe tabele) w autocommit_block — CONCURRENTLY nie działa w transakcji. Pozostałość
po przerwanym CONCURRENTLY (indeks INVALID) jest najpierw zdejmowana, bo IF NOT EXISTS
by ją zostawił. SQLite (dev/testy): zwykłe CREATE INDEX IF NOT EXISTS; GIN-y z modeli
powstają tam przez create_all jako zwykłe indeksy.

Revision ID: fkidx001
Revises: drift001
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "fkidx001"
down_revision = "drift001"
branch_labels = None
depends_on = None

# nazwa -> (tabela, kolumna); nazwy = auto-nazwy SQLAlchemy z `index=True` w modelach
_FK_INDEXES = {
    "ix_containers_supplier_id": ("containers", "supplier_id"),
    "ix_orders_supplier_id": ("orders", "supplier_id"),
    "ix_invoice_batches_supplier_id": ("invoice_batches", "supplier_id"),
    "ix_notifications_container_id": ("notifications", "container_id"),
    "ix_watched_containers_container_id": ("watched_containers", "container_id"),
    "ix_invoice_batches_attachment_id": ("invoice_batches", "attachment_id"),
    "ix_attachment_suggestions_attachment_id": ("attachment_suggestions", "attachment_id"),
    "ix_avizo_requests_company_id": ("avizo_requests", "company_id"),
    "ix_audit_log_user_id": ("audit_log", "user_id"),
}
# GIN pg_trgm — te same nazwy co Index(...) w modelach Container / Order
_TRGM_INDEXES = {
    "ix_containers_notes_trgm": ("containers", "notes"),
    "ix_containers_transport_id_trgm": ("containers", "transport_id"),
    "ix_orders_number_trgm": ("orders", "number"),
}


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _drop_if_invalid(name: str) -> None:
    """Przerwane CREATE INDEX CONCURRENTLY zostawia indeks INVALID — IF NOT EXISTS by go
    pominął i zostalibyśmy z bezużytecznym indeksem. Zdejmij go przed ponowieniem."""
    invalid = op.get_bind().execute(sa.text(
        "SELECT 1 FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid "
        "WHERE c.relname = :n AND NOT i.indisvalid"), {"n": name}).scalar()
    if invalid:
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")


def _trgm_ready() -> bool:
    bind = op.get_bind()
    if bind.exec_driver_sql("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'").scalar():
        return True
    if not bind.exec_driver_sql(
            "SELECT 1 FROM pg_available_extensions WHERE name = 'pg_trgm'").scalar():
        logging.getLogger("alembic").warning(
            "pg_trgm niedostępne w tej instalacji Postgresa — pomijam indeksy trigramowe")
        return False
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    return True


def upgrade() -> None:
    if not _is_postgres():
        for name, (table, col) in _FK_INDEXES.items():
            op.create_index(name, table, [col], if_not_exists=True)
        return
    with op.get_context().autocommit_block():
        for name, (table, col) in _FK_INDEXES.items():
            _drop_if_invalid(name)
            op.create_index(name, table, [col], postgresql_concurrently=True,
                            if_not_exists=True)
        if not _trgm_ready():
            return
        for name, (table, col) in _TRGM_INDEXES.items():
            _drop_if_invalid(name)
            # jawny SQL (USING przed listą kolumn) — pilnuje test_migracje_trgm_sql (DB-002)
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                       f"ON {table} USING gin ({col} gin_trgm_ops)")


def downgrade() -> None:
    if not _is_postgres():
        for name, (table, _col) in _FK_INDEXES.items():
            op.drop_index(name, table_name=table, if_exists=True)
        return
    with op.get_context().autocommit_block():
        for name, (table, _col) in {**_TRGM_INDEXES, **_FK_INDEXES}.items():
            op.drop_index(name, table_name=table, postgresql_concurrently=True,
                          if_exists=True)

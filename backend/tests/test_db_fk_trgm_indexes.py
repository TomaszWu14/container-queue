"""DB-010 + PERF-007 — indeksy FK (filtry / kasowanie kontenera) i trigramy wyszukiwarki.

1. Modele deklarują indeksy (create_all na SQLite = to samo, co migracja na PG; zgodność
   modeli z migracjami na postgres:16 pilnuje db_drift.py w CI „migracje”).
2. Migracja fkidx001 w izolacji na SQLite: zakłada i zdejmuje indeksy FK, idempotentnie.
   Gałąź PostgreSQL (CREATE INDEX CONCURRENTLY, GIN pg_trgm) — CI „migracje”.
3. Kształt zapytania: warunek na tabeli powiązanej (orders.number, suppliers.name) to
   podzapytanie po id na kolumnie FK kontenera — na PG `= ANY(ARRAY(…))`, więc cały OR
   zostaje na `containers` i planista może złożyć BitmapOr z indeksów trigramowych.
   LEFT JOIN z warunkiem na tabeli obcej wymuszał Seq Scan całej tabeli kontenerów.
4. Semantyka wyszukiwania bez zmian (numer PO z powiązanego zamówienia, dostawca).
"""
import importlib.util
import pathlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.dialects import postgresql

from app.database import Base
from app.models import Container, Order

from .test_api import VALID_NO, _company_id

_MIG = (pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"
        / "fkidx001_indeksy_fk_i_trigramy.py")

FK_INDEXES = {
    "containers": {"ix_containers_supplier_id"},
    "notifications": {"ix_notifications_container_id"},
    "watched_containers": {"ix_watched_containers_container_id"},
    "avizo_requests": {"ix_avizo_requests_company_id"},
    "audit_log": {"ix_audit_log_user_id"},
    "orders": {"ix_orders_supplier_id"},
    "invoice_batches": {"ix_invoice_batches_supplier_id", "ix_invoice_batches_attachment_id"},
    "attachment_suggestions": {"ix_attachment_suggestions_attachment_id"},
}
TRGM_INDEXES = {
    "containers": {"ix_containers_notes_trgm", "ix_containers_transport_id_trgm"},
    "orders": {"ix_orders_number_trgm"},
}


def _load():
    spec = importlib.util.spec_from_file_location("mig_fkidx001", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _names(engine, table: str) -> set[str]:
    return {ix["name"] for ix in inspect(engine).get_indexes(table)}


def test_models_declare_fk_and_trgm_indexes():
    tables = Base.metadata.tables
    for table, names in (*FK_INDEXES.items(), *TRGM_INDEXES.items()):
        assert names <= {ix.name for ix in tables[table].indexes}, table
    # GIN pg_trgm tylko na PG (na SQLite zwykły indeks) — jak istniejące *_trgm z trgm002
    trgm = {ix.name: ix for t in TRGM_INDEXES for ix in tables[t].indexes}
    for name in set().union(*TRGM_INDEXES.values()):
        assert trgm[name].dialect_options["postgresql"]["using"] == "gin"


def test_migration_sqlite_isolated_idempotent(tmp_path, monkeypatch):
    mig = _load()
    assert mig.down_revision == "drift001"
    eng = create_engine(f"sqlite:///{tmp_path / 'fk.db'}")
    Base.metadata.create_all(eng)
    with eng.begin() as conn:   # stan sprzed migracji: indeksów FK nie ma
        for names in FK_INDEXES.values():
            for name in names:
                conn.exec_driver_sql(f"DROP INDEX {name}")

    def run(fn):
        with eng.connect() as conn:
            monkeypatch.setattr(mig, "op", Operations(MigrationContext.configure(conn)))
            fn()
            conn.commit()

    run(mig.upgrade)
    run(mig.upgrade)   # drugi raz = no-op (bootstrap create_all mógł je już założyć)
    for table, names in FK_INDEXES.items():
        assert names <= _names(eng, table), table
    run(mig.downgrade)
    for table, names in FK_INDEXES.items():
        assert not names & _names(eng, table), table
    assert "ix_containers_company_id" in _names(eng, "containers")   # cudze nietknięte
    eng.dispose()


def test_fk_match_is_indexable_any_array_on_postgres():
    from app.routers.containers_common import fk_matches

    class _Bind:
        class dialect:  # noqa: N801 — atrapa silnika: tylko nazwa dialektu
            name = "postgresql"

    class _Db:
        def get_bind(self):
            return _Bind()

    ids = select(Order.id).where(Order.number.ilike("%4500%"))
    sql = str(select(Container.id).where(fk_matches(_Db(), Container.order_id, ids))
              .compile(dialect=postgresql.dialect()))
    assert "= ANY (array((SELECT orders.id" in sql
    assert "JOIN" not in sql


def test_queue_search_by_linked_order_number(client, admin_headers):
    """?q= po numerze zamówienia powiązanego (orders.number, nie order_numbers)."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    r = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis, "order_number": "PO-LINK-7781"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    found = client.get("/api/containers", params={"q": "link-778"}, headers=admin_headers)
    assert found.status_code == 200, found.text
    assert [c["id"] for c in found.json()] == [cid]
    assert found.headers["X-Total-Count"] == "1"
    none = client.get("/api/containers", params={"q": "nie-ma-takiego"}, headers=admin_headers)
    assert none.json() == []

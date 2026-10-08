"""A1/A2/A6 — brakujące indeksy.

Trzy warstwy weryfikacji (uwaga: pełny łańcuch Alembica nie jest uruchamialny na
SQLite — wcześniejsze migracje robią ALTER ADD FK, którego SQLite nie wspiera;
dev korzysta z create_all. Dlatego migrację testujemy w izolacji):

1. Metadata ORM deklaruje nowe indeksy (spójność dev/create_all + prod).
2. create_all na SQLite faktycznie zakłada te indeksy (siatka bezpieczeństwa bootstrapu).
3. Realny kod migracji (gałąź nie-PostgreSQL) zakłada i zdejmuje indeksy.

Ścieżka CREATE INDEX CONCURRENTLY (PostgreSQL) jest do potwierdzenia na stagingu —
tu jej nie uruchomimy (brak żywego PG).
"""
import importlib.util
import pathlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from app.database import Base
from app.models import AuditLog, Container

BACKEND = pathlib.Path(__file__).resolve().parents[1]
_MIG_PATH = BACKEND / "migrations" / "versions" / "d1e2f3a4b5c6_missing_indexes.py"

_EXPECTED = {
    "containers": {"ix_containers_order_id", "ix_containers_forwarder_id",
                   "ix_containers_customs_status", "ix_containers_wh_notify"},
    "audit_log": {"ix_audit_entity"},
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_missing_indexes", _MIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _index_names(engine, table: str) -> set[str]:
    return {ix["name"] for ix in inspect(engine).get_indexes(table)}


def test_models_declare_new_indexes():
    cont = {ix.name for ix in Container.__table__.indexes}
    assert _EXPECTED["containers"] <= cont
    # indeks złożony ma właściwą kolejność (warehouse_id wiodąca — pokrywa scope roli magazynu)
    wh = next(ix for ix in Container.__table__.indexes if ix.name == "ix_containers_wh_notify")
    assert [c.name for c in wh.columns] == ["warehouse_id", "notify_date"]
    assert _EXPECTED["audit_log"] <= {ix.name for ix in AuditLog.__table__.indexes}


def test_create_all_builds_indexes_on_sqlite(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'ca.db'}")
    Base.metadata.create_all(eng)
    assert _EXPECTED["containers"] <= _index_names(eng, "containers")
    assert _EXPECTED["audit_log"] <= _index_names(eng, "audit_log")
    eng.dispose()


def test_migration_upgrade_downgrade_isolated(tmp_path, monkeypatch):
    mig = _load_migration()
    assert mig.down_revision == "b2c4d6e8f0a1"  # wpina się na aktualny head

    eng = create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    Base.metadata.create_all(eng)
    # symuluj stan sprzed migracji: usuń nasze indeksy (create_all już je założył)
    with eng.begin() as conn:
        for name, _table, _cols in mig._INDEXES:
            conn.exec_driver_sql(f"DROP INDEX IF EXISTS {name}")
    assert not (_EXPECTED["containers"] & _index_names(eng, "containers"))

    def _run(fn):
        with eng.connect() as conn:
            monkeypatch.setattr(mig, "op", Operations(MigrationContext.configure(conn)))
            fn()
            conn.commit()

    _run(mig.upgrade)
    assert _EXPECTED["containers"] <= _index_names(eng, "containers")
    assert _EXPECTED["audit_log"] <= _index_names(eng, "audit_log")

    _run(mig.downgrade)
    # nasze indeksy zniknęły; kolumnowe (np. ix_containers_company_id) zostają nietknięte
    assert not (_EXPECTED["containers"] & _index_names(eng, "containers"))
    assert not (_EXPECTED["audit_log"] & _index_names(eng, "audit_log"))
    assert "ix_containers_company_id" in _index_names(eng, "containers")
    eng.dispose()

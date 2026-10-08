"""DB-003 — migracja drift001 na SQLite (dev/testy): tylko tabela + indeksy, idempotentnie.

Część PostgreSQL (FK, NOT NULL, unique) sprawdza CI „migracje” (db_drift.py na postgres:16).
"""
import importlib.util
import pathlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from app.database import Base

_MIG = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions" / "drift001_dryf_schematu.py"


def _load():
    spec = importlib.util.spec_from_file_location("mig_drift001", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_drift001_sqlite_idempotent(tmp_path, monkeypatch):
    mig = _load()
    eng = create_engine(f"sqlite:///{tmp_path / 'd.db'}")
    Base.metadata.create_all(eng)   # stan jak po bootstrapie: obiekty już są
    with eng.begin() as conn:       # …poza indeksem statusu zakupów i tabelą wydań
        conn.exec_driver_sql("DROP INDEX ix_containers_purchasing_status")
        conn.exec_driver_sql("DROP TABLE material_issues")

    def run(fn):
        with eng.connect() as conn:
            monkeypatch.setattr(mig, "op", Operations(MigrationContext.configure(conn)))
            fn()
            conn.commit()

    run(mig.upgrade)
    run(mig.upgrade)   # drugi raz = no-op (obiekty z create_all / poprzedniego przebiegu)
    insp = inspect(eng)
    assert {"ix_material_issues_produkt", "ix_material_issues_date"} <= {
        ix["name"] for ix in insp.get_indexes("material_issues")}
    assert "ix_containers_purchasing_status" in {ix["name"] for ix in insp.get_indexes("containers")}

    run(mig.downgrade)
    insp = inspect(eng)
    assert "ix_containers_purchasing_status" not in {ix["name"] for ix in insp.get_indexes("containers")}
    assert insp.has_table("material_issues")   # dane wydań zostają celowo
    eng.dispose()

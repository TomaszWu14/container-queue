"""Migracja e6f1a2b3c4d5 (Faktury → Excel lokalnie) w izolacji na SQLite: upgrade tworzy
nowe tabele i kolumnę, kasuje compare_batches; downgrade odwraca. Cały łańcuch Alembica
jest tylko dla PostgreSQL (stare migracje bez batch mode), stąd test pojedynczej rewizji —
wzorzec jak test_missing_indexes."""
import importlib.util
import pathlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

_MIG_PATH = (pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"
             / "e6f1a2b3c4d5_invoices_local.py")


def _load():
    spec = importlib.util.spec_from_file_location("mig_invoices_local", _MIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_upgrade_downgrade_isolated(tmp_path, monkeypatch):
    mig = _load()
    assert mig.down_revision == "b7d4f2a91c05"   # wpina się na aktualny head

    eng = create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    # stan sprzed migracji: tylko tabele, których dotyka (FK w SQLite nie są sprawdzane przy DDL)
    with eng.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE suppliers (id INTEGER PRIMARY KEY, name VARCHAR(160))")
        conn.exec_driver_sql("CREATE TABLE compare_batches (id INTEGER PRIMARY KEY, container_id INTEGER)")
        conn.exec_driver_sql("CREATE INDEX ix_compare_batches_container_id ON compare_batches(container_id)")

    def _run(fn):
        with eng.connect() as conn:
            monkeypatch.setattr(mig, "op", Operations(MigrationContext.configure(conn)))
            fn()
            conn.commit()

    _run(mig.upgrade)
    tables = set(inspect(eng).get_table_names())
    assert {"materials", "material_overrides", "uom_conversions", "invoice_batches",
            "invoice_jobs", "invoice_items"} <= tables
    assert "compare_batches" not in tables
    assert "column_map" in {c["name"] for c in inspect(eng).get_columns("suppliers")}
    assert "ix_materials_ref_norm" in {ix["name"] for ix in inspect(eng).get_indexes("materials")}

    _run(mig.downgrade)
    tables = set(inspect(eng).get_table_names())
    assert "compare_batches" in tables and "materials" not in tables and "invoice_items" not in tables
    assert "column_map" not in {c["name"] for c in inspect(eng).get_columns("suppliers")}
    eng.dispose()

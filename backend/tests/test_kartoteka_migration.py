"""Migracje kartoteki dostawców (spec 2026-09-25-kartoteka-dostawcy) w izolacji na SQLite —
wzorzec jak test_invoices_migration: pełny łańcuch Alembica jest tylko dla PostgreSQL."""
import importlib.util
import pathlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"

# stan sprzed kartoteka001: tylko tabele, których migracja dotyka (kształt jak na prod,
# łącznie z ix_suppliers_sap_code z migracji c3f8a1d7e924 i unique(company_id, name))
PRE_001 = [
    "CREATE TABLE companies (id INTEGER PRIMARY KEY, name VARCHAR(120), code VARCHAR(20))",
    "CREATE TABLE users (id INTEGER PRIMARY KEY)",
    "CREATE TABLE ports (id INTEGER PRIMARY KEY, name VARCHAR(80))",
    "CREATE TABLE materials (id INTEGER PRIMARY KEY, ref_code VARCHAR(100) UNIQUE)",
    "CREATE TABLE suppliers (id INTEGER PRIMARY KEY, name VARCHAR(160) NOT NULL, "
    "company_id INTEGER NOT NULL REFERENCES companies(id), is_active BOOLEAN NOT NULL DEFAULT 1, "
    "address VARCHAR(300) DEFAULT '', note TEXT DEFAULT '', sap_code VARCHAR(20) NOT NULL DEFAULT '', "
    "country VARCHAR(2) NOT NULL DEFAULT '', column_map TEXT NOT NULL DEFAULT '', "
    "UNIQUE (company_id, name))",
    "CREATE INDEX ix_suppliers_sap_code ON suppliers (sap_code)",
    "CREATE TABLE supplier_contacts (id INTEGER PRIMARY KEY, supplier_id INTEGER NOT NULL "
    "REFERENCES suppliers(id), full_name VARCHAR(160) NOT NULL, email VARCHAR(200) DEFAULT '', "
    "phone VARCHAR(60) DEFAULT '', is_active BOOLEAN DEFAULT 1)",
    "CREATE TABLE supplier_material_maps (id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, "
    "supplier_id INTEGER NOT NULL, supplier_code VARCHAR(120) NOT NULL, ref_code VARCHAR(120) NOT NULL, "
    "note VARCHAR(300) DEFAULT '', created_at DATETIME, updated_at DATETIME, "
    "UNIQUE (company_id, supplier_id, supplier_code))",
    "CREATE TABLE supplier_doc_profiles (id INTEGER PRIMARY KEY, supplier_id INTEGER NOT NULL UNIQUE "
    "REFERENCES suppliers(id) ON DELETE CASCADE)",
    "CREATE TABLE supplier_doc_samples (id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL "
    "REFERENCES supplier_doc_profiles(id) ON DELETE CASCADE, filename VARCHAR(255) NOT NULL, "
    "stored_path TEXT NOT NULL, created_at DATETIME, last_test JSON NOT NULL DEFAULT '{}', "
    "last_test_at DATETIME)",
    "INSERT INTO companies VALUES (1,'Borealis','BOREALIS'),(2,'Acme','ACME'),(3,'Iberia','PT')",
    # ACME z LFA1 w trzech spółkach (import szedł do każdej) + ręczny nadawca Borealis
    "INSERT INTO suppliers (id, name, company_id, sap_code) VALUES "
    "(1,'ACME',2,'100'),(2,'ACME',3,'100'),(3,'Nadawca T',1,''),(4,'ACME',1,'100')",
    "INSERT INTO materials VALUES (1,'REF1'),(2,'REF2')",
    "INSERT INTO supplier_material_maps (company_id, supplier_id, supplier_code, ref_code) VALUES "
    "(2,1,'A1','REF1'),(3,1,'A0','REF1'),(2,1,'B','REF2'),(2,2,'X','NOPE')",
    "INSERT INTO supplier_doc_profiles VALUES (1,1)",
    "INSERT INTO supplier_doc_samples (profile_id, filename, stored_path) VALUES (1,'a.pdf','x')",
]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), VERSIONS / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _engine(tmp_path, statements):
    eng = create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    with eng.begin() as conn:
        for sql in statements:
            conn.exec_driver_sql(sql)
    return eng


def _apply(eng, mig, fn, monkeypatch):
    with eng.connect() as conn:
        monkeypatch.setattr(mig, "op", Operations(MigrationContext.configure(conn)))
        fn()
        conn.commit()


def test_kartoteka001_upgrade_and_downgrade(tmp_path, monkeypatch):
    mig = _load("kartoteka001_kartoteka_dostawcow.py")
    assert mig.down_revision == "dowoz001"          # wpina się na aktualną głowę
    eng = _engine(tmp_path, PRE_001)

    _apply(eng, mig, mig.upgrade, monkeypatch)
    cols = {c["name"] for c in inspect(eng).get_columns("suppliers")}
    assert "company_id" not in cols
    assert {"client_company_id", "street", "city", "zip", "vat", "sap_status", "lat", "lng",
            "geo_source", "shipping_port_id"} <= cols
    assert "ix_suppliers_sap_code" in {i["name"] for i in inspect(eng).get_indexes("suppliers")}
    assert {"role", "messenger", "is_primary"} <= {
        c["name"] for c in inspect(eng).get_columns("supplier_contacts")}
    assert {"supplier_materials", "supplier_doc_variants", "sap_imports"} <= set(
        inspect(eng).get_table_names())
    with eng.connect() as c:
        # Acme i PT → kartoteka (NULL); Borealis → nadawca Borealis (także jego kopia z LFA1)
        assert c.exec_driver_sql(
            "SELECT id, client_company_id FROM suppliers ORDER BY id").all() == [
            (1, None), (2, None), (3, 1), (4, 1)]
        # mapy → indeksy dostawcy: kolizja (dostawca, materiał) = najmniejszy kod,
        # ref_code spoza master data pominięty, znacznik unconfirmed
        assert c.exec_driver_sql(
            "SELECT supplier_id, material_id, supplier_code, unconfirmed "
            "FROM supplier_materials ORDER BY 1, 2").all() == [(1, 1, "A0", 1), (1, 2, "B", 1)]
        assert c.exec_driver_sql(
            "SELECT status, doc_type, reason FROM supplier_doc_samples").all() == [("ok", "", "")]
        # unique(company_id, name) zniknął razem z kolumną
        c.exec_driver_sql("INSERT INTO suppliers (name) VALUES ('ACME')")
        assert mig.copy_material_maps(c) == 0          # idempotentne
        c.commit()

    _apply(eng, mig, mig.downgrade, monkeypatch)
    insp = inspect(eng)
    assert "supplier_materials" not in insp.get_table_names()
    assert "client_company_id" not in {c["name"] for c in insp.get_columns("suppliers")}
    with eng.connect() as c:
        # stratnie: kartoteka wraca do Acme (id=2), nadawcy — do swojej spółki
        assert c.exec_driver_sql(
            "SELECT id, company_id FROM suppliers WHERE id <= 4 ORDER BY id").all() == [
            (1, 2), (2, 2), (3, 1), (4, 1)]
    eng.dispose()

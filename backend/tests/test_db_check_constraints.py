"""DB-007 — integralność w bazie, nie tylko w aplikacji.

1. CHECK dla słowników tekstowych (VARCHAR) i zakresów: wartość spoza słownika zapisana
   z pominięciem aplikacji (SQL, import, n8n) → IntegrityError zamiast cichego śmiecia.
2. Unikalny klucz biznesowy: numer kontenera wśród NIEZREALIZOWANYCH w spółce (N-20:
   zrealizowany = archiwum, powtórny przyjazd to nowy rekord). Kod SAP dostawcy — dopiero
   po scaleniu kopii w kartotece (supplier_consolidation, etap B): test niżej pilnuje, że
   duplikaty kodu są nadal dozwolone (narzędzie scalania na nich pracuje).
3. Naruszenie klucza przez API → 409 z czytelnym komunikatem, nie 500.
4. Migracja chk001: definicje = modele; SQLite (dev) — indeksy tylko bez duplikatów.
   Gałąź PostgreSQL (naprawa, NOT VALID + VALIDATE) — CI „migracje” i opis w PR.
"""
import importlib.util
import pathlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import CheckConstraint, create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal
from app.models import Company, Container, ContainerStatus, Supplier

from .test_api import VALID_NO, _company_id

_MIG = (pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"
        / "chk001_ograniczenia_check_i_klucze.py")


def _load():
    spec = importlib.util.spec_from_file_location("mig_chk001", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _container(db, **kw) -> Container:
    company = db.scalar(select(Company).where(Company.code == "ACME"))
    c = Container(container_no=kw.pop("container_no", VALID_NO), company_id=company.id, **kw)
    db.add(c)
    db.flush()
    return c


@pytest.mark.parametrize("sql", [
    "UPDATE containers SET consolidation_status = 'pełny' WHERE id = :i",
    "UPDATE containers SET ramp_stage = 'NA_RAMPIE' WHERE id = :i",
    "UPDATE containers SET special_reason = 'bo tak' WHERE id = :i",
    "UPDATE containers SET on_carriage = 'rower' WHERE id = :i",
    "UPDATE containers SET capacity_cbm = 0 WHERE id = :i",
    "UPDATE containers SET pallet_count = -1 WHERE id = :i",
    "UPDATE containers SET unload_started_at = '2026-09-28 12:00:00', "
    "unload_finished_at = '2026-09-28 11:00:00' WHERE id = :i",
])
def test_check_rejects_out_of_dictionary_values(client, sql):
    with SessionLocal() as db:
        cid = _container(db).id
        with pytest.raises(IntegrityError):
            db.execute(text(sql), {"i": cid})
        db.rollback()


def test_check_accepts_valid_values_and_nulls(client):
    with SessionLocal() as db:
        cid = _container(db).id
        db.execute(text(
            "UPDATE containers SET consolidation_status = 'zamkniety', ramp_stage = NULL, "
            "special_reason = 'pilne', on_carriage = 'intermodal', pallet_count = 0, "
            "unload_started_at = '2026-09-28 11:00:00', unload_finished_at = NULL "
            "WHERE id = :i"), {"i": cid})
        db.commit()


EXPECTED_CHECKS = {
    "containers": {"ck_containers_consolidation_status", "ck_containers_ramp_stage",
                   "ck_containers_special_reason", "ck_containers_on_carriage",
                   "ck_containers_capacity_cbm", "ck_containers_pallet_count",
                   "ck_containers_unload_order"},
    "suppliers": {"ck_suppliers_sap_status"},
    "purchase_orders": {"ck_purchase_orders_cart_status"},
    "freight_invoices": {"ck_freight_invoices_status"},
    "sap_orders": {"ck_sap_orders_sap_status"},
    "material_units": {"ck_material_units_sap_status"},
}


def test_check_constraints_declared():
    for table, names in EXPECTED_CHECKS.items():
        got = {c.name for c in Base.metadata.tables[table].constraints
               if isinstance(c, CheckConstraint)}
        assert names <= got, table


def test_check_supplier_sap_status(client):
    with SessionLocal() as db:
        db.add(Supplier(name="X", sap_status="zawieszony"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_active_container_number_unique_per_company(client):
    with SessionLocal() as db:
        first = _container(db)
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                _container(db)                                  # drugi aktywny — nie
        first.status = ContainerStatus.ZREALIZOWANY
        db.flush()
        _container(db)                                          # powtórny przyjazd — tak
        _container(db, container_no="")                         # zlecenie bez numeru ×2
        _container(db, container_no="")
        db.commit()


def test_api_duplicate_active_number_is_409(client, admin_headers):
    acme = _company_id(client, admin_headers, "ACME")
    body = {"container_no": VALID_NO, "company_id": acme}
    assert client.post("/api/containers", headers=admin_headers, json=body).status_code == 201
    dup = client.post("/api/containers", headers=admin_headers, json=body)
    assert dup.status_code == 409, dup.text
    assert "numerze" in dup.json()["detail"]


def test_supplier_sap_code_copies_still_allowed(client):
    """Kopie kodu SAP (sprzed globalnej kartoteki) scala supplier_consolidation — do tego
    czasu baza ich nie odrzuca (unikalność = osobny krok, etap B)."""
    with SessionLocal() as db:
        db.add_all([Supplier(name="A", sap_code="100200"), Supplier(name="A", sap_code="100200")])
        db.commit()


def test_migration_definitions_match_models():
    mig = _load()
    assert mig.down_revision == "tidseq001"
    model_checks = {c.name: (t.name, str(c.sqltext)) for t in Base.metadata.tables.values()
                    for c in t.constraints if isinstance(c, CheckConstraint) and c.name
                    and c.name.startswith("ck_")}
    assert {n: (t, sql) for n, (t, sql, _fix) in mig.CHECKS.items()} == model_checks
    for name, (table, cols, where) in mig.UNIQUES.items():
        ix = next(i for i in Base.metadata.tables[table].indexes if i.name == name)
        assert ix.unique and [c.name for c in ix.columns] == cols
        assert str(ix.dialect_options["postgresql"]["where"]) == where


@pytest.mark.parametrize("duplicate", [False, True])
def test_migration_sqlite_unique_only_without_duplicates(tmp_path, monkeypatch, caplog,
                                                         duplicate):
    mig = _load()
    eng = create_engine(f"sqlite:///{tmp_path / 'c.db'}")
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.exec_driver_sql("DROP INDEX ux_containers_active_no")
    with Session(eng) as db:   # stan sprzed migracji: (opcjonalnie) dwa aktywne z jednym numerem
        company = Company(code="ACME", name="Z")
        db.add(company)
        db.flush()
        numbers = [VALID_NO, VALID_NO] if duplicate else [VALID_NO]
        db.add_all([Container(container_no=n, company_id=company.id) for n in numbers])
        db.commit()

    def run(fn):
        with eng.connect() as conn:
            monkeypatch.setattr(mig, "op", Operations(MigrationContext.configure(conn)))
            fn()
            conn.commit()

    with caplog.at_level("WARNING", logger="alembic"):
        run(mig.upgrade)   # duplikat nie wywraca migracji (deploy) — tylko ostrzeżenie
    names = {i["name"] for i in inspect(eng).get_indexes("containers")}
    assert ("ux_containers_active_no" in names) is not duplicate
    assert (VALID_NO in caplog.text) is duplicate
    run(mig.downgrade)
    assert "ux_containers_active_no" not in {
        i["name"] for i in inspect(eng).get_indexes("containers")}
    eng.dispose()

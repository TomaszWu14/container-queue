"""DB-011 — numeracja transport_id przez licznik w bazie zamiast max+1 w Pythonie.

Weryfikacja z audytu: „dwie sesje tworzące kontener dla tej samej spółki i roku: oba
zapisy przechodzą z różnymi numerami”. Stary kod: obie sesje czytały to samo maksimum →
ten sam numer → IntegrityError na unikalnym ix_containers_transport_id (500 / przerwany
import). Licznik (transport_id_counters, upsert z blokadą wiersza) serializuje nadawanie.
"""
import importlib.util
import pathlib
import threading
import time

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal
from app.models import AuditLog, Company, Container, TransportIdCounter
from app.routers.containers_common import (
    _max_transport_seq,
    next_transport_id,
    reserve_transport_seqs,
)

_MIG = (pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"
        / "tidseq001_licznik_transport_id.py")


def _company(db, code="ACME") -> Company:
    return db.scalar(select(Company).where(Company.code == code))


def test_two_sessions_same_company_year_get_different_numbers(client):
    """Dwa równoległe utworzenia (np. sync SharePoint + ręczne dodanie) — oba przechodzą."""
    with SessionLocal() as db:
        company_id = _company(db).id
    results: dict[str, str] = {}
    errors: list[BaseException] = []

    def create(name: str, delay: float, number: str):
        try:
            time.sleep(delay)
            with SessionLocal() as db:
                tid = next_transport_id(db, db.get(Company, company_id), 2031)
                db.add(Container(container_no=number, company_id=company_id, transport_id=tid))
                time.sleep(0.3)   # transakcja A jeszcze otwarta, gdy B nadaje numer
                db.commit()
                results[name] = tid
        except BaseException as exc:  # noqa: BLE001 — zbieramy do asercji w wątku głównym
            errors.append(exc)

    threads = [threading.Thread(target=create, args=("A", 0.0, "MSCU1234565")),
               threading.Thread(target=create, args=("B", 0.1, "TGHU9876546"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)
    assert not errors, errors
    assert sorted(results.values()) == ["AT-2031-0001", "AT-2031-0002"]


def test_counter_row_and_block_reservation(client):
    with SessionLocal() as db:
        first = reserve_transport_seqs(db, "AT-2032-", 3)
        nxt = next_transport_id(db, _company(db), 2032)
        db.commit()
        row = db.get(TransportIdCounter, "AT-2032-")
    assert (first, nxt, row.last_seq) == (1, "AT-2032-0004", 4)


def test_counter_self_heals_when_behind_existing_numbers(client):
    """Numer nadany poza licznikiem (np. stary proces w trakcie deployu) — bez kolizji."""
    with SessionLocal() as db:
        company = _company(db)
        db.add(Container(container_no="MSCU1234565", company_id=company.id,
                         transport_id="AT-2033-0041"))
        db.commit()
        assert next_transport_id(db, company, 2033) == "AT-2033-0042"
        db.commit()


def test_max_seq_reads_numeric_maximum_not_text_order(client):
    with SessionLocal() as db:
        cid = _company(db).id
        for i, tid in enumerate(("AT-2034-9999", "AT-2034-10000", "AT-2034-abc")):
            db.add(Container(container_no=f"MSCU12345{i}5"[:11], company_id=cid, transport_id=tid))
        db.commit()
        assert _max_transport_seq(db, "AT-2034-") == 10000


def _load():
    spec = importlib.util.spec_from_file_location("mig_tidseq001", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_seeds_counters_and_repairs_duplicates(tmp_path, monkeypatch):
    mig = _load()
    assert mig.down_revision == "loginlim001"
    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.exec_driver_sql("DROP TABLE transport_id_counters")
        # prod bez unikalności (dryf) z duplikatem — migracja ma go naprawić, nie paść
        conn.exec_driver_sql("DROP INDEX ix_containers_transport_id")
    with Session(eng) as db:
        company = Company(code="ACME", name="Z")
        db.add(company)
        db.flush()
        for i, tid in enumerate(("AT-2026-0007", "AT-2026-0007", "AT-2026-0002",
                                 "YT-2025-0010", None), start=1):
            db.add(Container(id=i, container_no=f"MSCU000000{i}", company_id=company.id,
                             transport_id=tid))
        db.commit()

    def run(fn):
        with eng.connect() as conn:
            monkeypatch.setattr(mig, "op", Operations(MigrationContext.configure(conn)))
            fn()
            conn.commit()

    run(mig.upgrade)
    with eng.connect() as conn:
        tids = dict(conn.execute(text("SELECT id, transport_id FROM containers")).all())
        counters = dict(conn.execute(text("SELECT prefix, last_seq FROM transport_id_counters")).all())
        notes = conn.execute(select(AuditLog.entity_id, AuditLog.old_value, AuditLog.new_value)
                             .where(AuditLog.field == "transport_id")).all()
    assert tids[1] == "AT-2026-0007" and tids[2] == "AT-2026-0008"   # starszy zostaje
    assert counters == {"AT-2026-": 8, "YT-2025-": 10}
    assert notes == [(2, "AT-2026-0007", "AT-2026-0008")]
    assert any(ix["name"] == "ix_containers_transport_id" and ix["unique"]
               for ix in inspect(eng).get_indexes("containers"))
    run(mig.downgrade)
    assert not inspect(eng).has_table("transport_id_counters")
    eng.dispose()

"""Sync z Excela nie cofa zmian zrobionych w apce w polach niezapisywalnych do arkusza
(odprawa, magazyn, uwagi…) — dawniej pierwszy sync ustawiał B<-A, a drugi z tym samym
Excelem widział „zmianę w Excelu” i nadpisywał apkę. Status odprawy z arkusza — tylko w przód."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company, Container, CustomsStatus, Warehouse
from app.routers.imports import reconcile_queue
from tests.test_sync import _raw

NO = "MSKU7026492"


def _row(**over):
    return {**_raw(NO, 1), **over}


def _setup(db, **over):
    company = db.scalar(select(Company).where(Company.code == "BOREALIS"))
    reconcile_queue(db, company, [_row(**over)], None); db.flush()
    c = db.scalar(select(Container).where(Container.company_id == company.id,
                                          Container.container_no == NO))
    return company, c


def test_app_changes_survive_repeated_syncs_and_later_excel_change_applies(client):
    db = SessionLocal()
    try:
        company, c = _setup(db)
        dlt = Warehouse(company_id=company.id, name="DLT", country="PL")
        db.add(dlt); db.flush()
        c.customs_status = CustomsStatus.ROZLICZONY
        c.warehouse_id = dlt.id
        c.notes = "uwaga z apki"
        db.flush()
        for _ in range(3):
            reconcile_queue(db, company, [_row()], None); db.flush()
            assert (c.customs_status, c.warehouse_id, c.notes) == \
                (CustomsStatus.ROZLICZONY, dlt.id, "uwaga z apki")
        # arkusz naprawdę się zmienia: magazyn ACME → przechodzi; odprawa „zlecona” to krok wstecz
        reconcile_queue(db, company, [_row(warehouse="ACME", customs="zlecona")], None); db.flush()
        assert db.get(Warehouse, c.warehouse_id).name == "ACME"
        assert c.customs_status == CustomsStatus.ROZLICZONY
    finally:
        db.rollback(); db.close()


def test_customs_forward_from_excel_still_applies(client):
    db = SessionLocal()
    try:
        company, c = _setup(db, customs="zlecona")
        assert c.customs_status == CustomsStatus.ZLECONA
        reconcile_queue(db, company, [_row(customs="odprawiony")], None); db.flush()
        assert c.customs_status == CustomsStatus.ODPRAWIONY
    finally:
        db.rollback(); db.close()

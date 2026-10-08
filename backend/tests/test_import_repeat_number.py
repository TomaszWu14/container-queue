"""N-20 (DATA-001): import i sync dopasowują numer kontenera tylko wśród niezrealizowanych
rekordów spółki. Numer tylko z archiwum (ZREALIZOWANY) = nowy kontener z notatką
„powtórny numer — poprzednia dostawa: dd.mm.rrrr”; stary rekord nietknięty."""
import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company, Container, ContainerStatus
from app.routers.imports import reconcile_queue
from tests.test_sync import _raw, _xlsx

NO = "MSKU7026492"
NOTE = "powtórny numer — poprzednia dostawa: 03.09.2026"


def _rows(db, company):
    return db.scalars(select(Container).where(Container.company_id == company.id,
                                              Container.container_no == NO)
                      .order_by(Container.id)).all()


def _finished(db):
    company = db.scalar(select(Company).where(Company.code == "BOREALIS"))
    reconcile_queue(db, company, [_raw(NO, 1, notify_day=3)], None)
    db.flush()
    old = _rows(db, company)[0]
    old.status = ContainerStatus.ZREALIZOWANY
    db.flush()
    return company, old


def test_sync_repeat_number_of_finished_creates_new_container(client):
    db = SessionLocal()
    try:
        company, old = _finished(db)
        before = (old.eta, old.notify_date, old.status, old.notes)
        reconcile_queue(db, company, [_raw(NO, 20, notify_day=25)], None)
        db.flush()
        rows = _rows(db, company)
        assert len(rows) == 2
        assert (old.eta, old.notify_date, old.status, old.notes) == before
        new = rows[1]
        assert new.eta == datetime.date(2026, 9, 20) and new.notes == NOTE
        # kolejny sync (Excel autorytatywny dla uwag) nie kasuje notatki ani nie dubluje rekordu
        reconcile_queue(db, company, [_raw(NO, 21, notify_day=25)], None)
        db.flush()
        assert len(_rows(db, company)) == 2
        assert new.notes == NOTE and new.eta == datetime.date(2026, 9, 21)
    finally:
        db.rollback(); db.close()


def test_sync_finished_delivery_left_in_excel_is_skipped(client):
    """Ta sama (zrealizowana) dostawa zostaje w arkuszu — sync nie tworzy co raz nowego rekordu."""
    db = SessionLocal()
    try:
        company, old = _finished(db)
        for _ in range(2):
            assert reconcile_queue(db, company, [_raw(NO, 1, notify_day=3)], None) == []
            db.flush()
        rows = _rows(db, company)
        assert len(rows) == 1 and rows[0].status == ContainerStatus.ZREALIZOWANY
    finally:
        db.rollback(); db.close()


def test_sync_active_container_still_updated_without_duplicate(client):
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.code == "BOREALIS"))
        reconcile_queue(db, company, [_raw(NO, 1)], None); db.flush()
        reconcile_queue(db, company, [_raw(NO, 5)], None); db.flush()
        rows = _rows(db, company)
        assert len(rows) == 1 and rows[0].eta == datetime.date(2026, 9, 5)
        assert rows[0].notes == ""
    finally:
        db.rollback(); db.close()


def test_import_repeat_number_of_finished_creates_new_container(client, admin_headers):
    db = SessionLocal()
    try:
        company, old = _finished(db)
        db.commit()
        old_id = old.id
    finally:
        db.close()
    f = _xlsx([["ACME", "MAERSK", datetime.datetime(2026, 9, 20), "kolej", NO, "", ""]])
    url = "/api/import/containers?company_code=BOREALIS&dry_run="
    prev = client.post(url + "true", headers=admin_headers, files={"file": ("q.xlsx", f)}).json()
    assert prev["counts"]["new"] == 1 and prev["rows"][0]["note"] == NOTE
    r = client.post(url + "false", headers=admin_headers, files={"file": ("q.xlsx", f)})
    assert r.status_code == 200 and r.json()["imported"] == 1, r.text
    db = SessionLocal()
    try:
        rows = _rows(db, company)
        assert [c.id for c in rows][0] == old_id and len(rows) == 2
        assert rows[0].status == ContainerStatus.ZREALIZOWANY
        assert rows[0].eta == datetime.date(2026, 9, 1)
        assert rows[1].notes == NOTE and rows[1].eta == datetime.date(2026, 9, 20)
        # aktywny rekord z tym numerem → ponowny import go pomija (bez duplikatu)
        again = client.post(url + "false", headers=admin_headers,
                            files={"file": ("q.xlsx", f)}).json()
        assert again["counts"]["exists"] == 1 and again["imported"] == 0
    finally:
        db.close()

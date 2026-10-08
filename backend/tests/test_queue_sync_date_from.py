import datetime
import io

from openpyxl import Workbook

from app.database import SessionLocal
from app.models import Company


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["DOSTAWCA", "STATEK", "ETA", "KOLEJ/KOŁA", "NR KONTENERA",
               "STATUS ODPRAWY", "DATA ROZŁADUNKU"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_row_older_than_date_from_is_skipped(client, admin_headers):
    hdr = admin_headers
    no = "MSKU5000009"
    f = _xlsx([["ACME", "MAERSK", datetime.datetime(2026, 9, 1), "kolej", no, "",
                datetime.datetime(2026, 9, 1)]])
    r = client.post(
        "/api/import/queue-sync?company_code=BOREALIS&dry_run=true&date_from=2026-09-05",
        headers=hdr, files={"file": ("q.xlsx", f)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skipped_old"] == 1
    assert body["changed"] == 0

    db = SessionLocal()
    try:
        company = db.scalar(__import__("sqlalchemy").select(Company).where(Company.code == "BOREALIS"))
        from app.models import Container
        assert db.scalar(__import__("sqlalchemy").select(Container).where(
            Container.company_id == company.id, Container.container_no == no)) is None
    finally:
        db.close()


def test_row_from_date_from_onward_is_kept(client, admin_headers):
    hdr = admin_headers
    no = "MSKU5000014"
    f = _xlsx([["ACME", "MAERSK", datetime.datetime(2026, 9, 1), "kolej", no, "",
                datetime.datetime(2026, 9, 5)]])
    r = client.post(
        "/api/import/queue-sync?company_code=BOREALIS&dry_run=true&date_from=2026-09-05",
        headers=hdr, files={"file": ("q.xlsx", f)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skipped_old"] == 0
    assert body["changed"] == 1


def test_row_without_notify_date_is_kept_regardless_of_date_from(client, admin_headers):
    hdr = admin_headers
    no = "MSKU5000035"
    f = _xlsx([["ACME", "MAERSK", datetime.datetime(2026, 9, 1), "kolej", no, "", ""]])
    r = client.post(
        "/api/import/queue-sync?company_code=BOREALIS&dry_run=true&date_from=2026-09-05",
        headers=hdr, files={"file": ("q.xlsx", f)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skipped_old"] == 0
    assert body["changed"] == 1


def test_real_import_with_date_from_saves_setting_and_get_returns_it(client, admin_headers):
    hdr = admin_headers
    no = "MSKU5000040"
    f = _xlsx([["ACME", "MAERSK", datetime.datetime(2026, 9, 1), "kolej", no, "",
                datetime.datetime(2026, 9, 10)]])
    r = client.post(
        "/api/import/queue-sync?company_code=BOREALIS&dry_run=false&date_from=2026-09-05",
        headers=hdr, files={"file": ("q.xlsx", f)})
    assert r.status_code == 200, r.text
    assert r.json()["skipped_old"] == 0

    r2 = client.get("/api/import/queue-sync-date-from?company_code=BOREALIS", headers=hdr)
    assert r2.status_code == 200, r2.text
    assert r2.json()["date_from"] == "2026-09-05"


def test_without_date_from_behaves_as_before(client, admin_headers):
    hdr = admin_headers
    no = "MSKU5000056"
    f = _xlsx([["ACME", "MAERSK", datetime.datetime(2026, 9, 1), "kolej", no, "",
                datetime.datetime(2020, 1, 1)]])
    r = client.post(
        "/api/import/queue-sync?company_code=BOREALIS&dry_run=true",
        headers=hdr, files={"file": ("q.xlsx", f)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skipped_old"] == 0
    assert body["changed"] == 1

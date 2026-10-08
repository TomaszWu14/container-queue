"""API importu podglądów SAD (WinSAD): /api/sad-import/check i /report — pliki w pamięci,
błąd per plik (reszta sprawdzona), limit plików, raport Excel, zakres spółek
(deps.check_container_access) i ślad audytu `sad_import` na kontenerze."""
import datetime
import io
import pathlib

import openpyxl
from pypdf import PdfWriter
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import AuditLog
from tests.conftest import login
from tests.test_invoices_api import _container

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "sad"
SADS = ["SAD7100001.pdf", "SAD7100002.pdf", "SAD7100003.pdf", "SAD7100004.pdf"]
CHECK, REPORT = "/api/sad-import/check", "/api/sad-import/report"


def _files(*names, extra=()):
    return [("files", (n, (FIXTURES / n).read_bytes(), "application/pdf")) for n in names] \
        + [("files", f) for f in extra]


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _user(client, headers, name, role, company_id):
    r = client.post("/api/users", headers=headers, json={
        "login": name, "password": "haslo123", "role": role, "company_id": company_id,
        "view_all_companies": False})
    assert r.status_code == 201, r.text
    return r.json()["id"], login(client, name, "haslo123")


def _audit(container_id):
    with SessionLocal() as db:
        return db.scalars(select(AuditLog).where(
            AuditLog.entity_type == "containers", AuditLog.entity_id == container_id,
            AuditLog.field == "sad_import")).all()


def test_check_four_fixtures(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    r = client.post(CHECK, headers=admin_headers, files=_files(*SADS))
    assert r.status_code == 200, r.text
    files = r.json()["files"]
    assert [f["plik"] for f in files] == SADS
    assert all(f["ok"] and f["blad"] is None for f in files)
    assert [f["zgloszenie"]["status"] for f in files] == ["WARN"] * 4
    by_name = {f["plik"]: f for f in files}
    multi = by_name["SAD7100003.pdf"]
    assert len(multi["pozycje"]) == 2
    head = multi["zgloszenie"]
    assert head["numer"] == "7100003" and head["kontenery"] == ["TSTU3000039"]
    assert head["waluta"] == "USD" and head["wartosc_faktur"] == "20382.9"   # Decimal → str
    assert head["kurs"] == "3.7306" and head["data_zgloszenia"] == "2026-09-24"
    assert head["data_wydruku"] == "2026-09-23T16:05:00"
    assert head["suma_cla"] == "0" and head["suma_vat"] == "7211"
    item = by_name["SAD7100001.pdf"]["pozycje"][0]
    assert item["a00"]["kwota_nalezna"] == "12847" and item["b00"] is not None
    warn = [w for w in multi["wyniki"] if w["status"] != "OK"]
    assert len(warn) == 1 and warn[0]["status"] == "WARN" and "AIS" in warn[0]["regula"]
    assert not any(tmp_path.iterdir())            # upload nie ląduje na dysku


def test_bad_files_are_per_file_errors(client, admin_headers):
    extra = [("notatka.txt", b"hello", "text/plain"),
             ("udaje.pdf", b"not a pdf at all", "application/pdf"),
             ("pusty.pdf", _blank_pdf(), "application/pdf")]
    r = client.post(CHECK, headers=admin_headers, files=_files("SAD7100001.pdf", extra=extra))
    assert r.status_code == 200, r.text
    ok, txt, fake, blank = r.json()["files"]
    assert ok["ok"] and ok["zgloszenie"]["numer"] == "7100001"
    for bad in (txt, fake, blank):
        assert bad["ok"] is False and bad["blad"] and bad["zgloszenie"] is None
        assert bad["pozycje"] == [] and bad["wyniki"] == []
    assert txt["blad"] == fake["blad"] == "To nie jest plik PDF."
    assert "WinSAD" in blank["blad"]


def test_file_count_limits(client, admin_headers):
    many = [("files", (f"s{i}.pdf", b"%PDF-1.4", "application/pdf")) for i in range(21)]
    assert client.post(CHECK, headers=admin_headers, files=many).status_code == 422
    assert client.post(REPORT, headers=admin_headers, files=many).status_code == 422
    assert client.post(CHECK, headers=admin_headers).status_code == 422   # brak plików


def test_report_xlsx(client, admin_headers):
    extra = [("notatka.txt", b"hello", "text/plain")]
    r = client.post(REPORT, headers=admin_headers, files=_files(*SADS, extra=extra))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    today = datetime.date.today().isoformat()
    assert r.headers["content-disposition"] == f'attachment; filename="sad_raport_{today}.xlsx"'
    workbook = openpyxl.load_workbook(io.BytesIO(r.content))
    assert {"Zgłoszenia", "Pozycje", "Walidacja", "Dokumenty"} <= set(workbook.sheetnames)
    only_bad = [("files", ("notatka.txt", b"hello", "text/plain"))]
    assert client.post(REPORT, headers=admin_headers, files=only_bad).status_code == 422


def test_company_scoping_and_audit(client, admin_headers):
    companies = client.get("/api/companies", headers=admin_headers).json()
    company_a, company_b = companies[0]["id"], companies[1]["id"]
    container_a = _container(client, admin_headers, company_id=company_a, no="DEMU1000010")
    _container(client, admin_headers, company_id=company_b, no="QAXU2000028")
    _, outsider = _user(client, admin_headers, "log.b.sad", "logistics", company_b)
    buyer_id, buyer = _user(client, admin_headers, "zak.a.sad", "purchasing", company_a)

    # spółka B: kontener z SAD należy do A → błąd pliku bez żadnych danych zgłoszenia
    r = client.post(CHECK, headers=outsider, files=_files("SAD7100001.pdf", "SAD7100003.pdf"))
    assert r.status_code == 200, r.text
    for f in r.json()["files"]:          # SAD7100003: kontenera nie ma w TIMPORYE
        assert f["ok"] is False and f["blad"].startswith("Brak dostępu")
        assert f["zgloszenie"] is None and f["pozycje"] == [] and f["wyniki"] == []
    assert "26SEPDEMO1" not in r.text and "Fictiva" not in r.text   # LRN, nadawca
    assert client.post(REPORT, headers=outsider,
                       files=_files("SAD7100001.pdf")).status_code == 422
    assert _audit(container_a) == []

    # spółka A: SAD widoczny, ślad audytu na kontenerze
    r = client.post(CHECK, headers=buyer, files=_files("SAD7100001.pdf"))
    f = r.json()["files"][0]
    assert f["ok"] and f["zgloszenie"]["lrn"] == "26SEPDEMO1" and f["zgloszenie"]["status"] == "WARN"
    rows = _audit(container_a)
    assert len(rows) == 1
    assert rows[0].new_value == "SAD 7100001: WARN" and rows[0].user_id == buyer_id
    assert client.post(REPORT, headers=buyer, files=_files("SAD7100001.pdf")).status_code == 200
    assert len(_audit(container_a)) == 2

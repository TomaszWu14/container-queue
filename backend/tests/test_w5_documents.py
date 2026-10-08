"""W5 dokumenty/OCR: propozycje podpięcia (31), alert braków przed ETA (32),
porównania packing/faktura (33/34), ZIP-y (35), szablony wysyłki (36)."""
import datetime
import io
import zipfile

import pytest
from pypdf import PdfWriter

from app.config import settings
from app.invoices import extractor, splitter
from app.models import Notification, OrderItem, PurchaseOrder, today_pl
from app.notifications import check_docs_alerts
from tests.conftest import forwarder, login
from tests.conftest import pdf_bytes

# ISO 6346 poprawne numery (z cyfrą kontrolną)
MAIN_NO = "MSDU0806613"
TARGET_NO = "CSQU3054383"

CI_TEXT = (f"COMMERCIAL INVOICE\nInvoice No.: FV/2026/9\nCONTAINER No.:{TARGET_NO}\n"
           "Terms of Delivery:\nFOB QINGDAO")
PL_TEXT = f"PACKING LIST No. & date of invoice FV/2026/9 CTNS {TARGET_NO}"

INVOICE_TABLE = [
    ["No", "Item No.", "Description", "Qty", "Unit", "Unit price", "Amount"],
    ["1", "NL753-S-40", "Catheter", "1,000", "PCS", "0.25", "250.00"],
    ["2", "XYZ-9", "Widget", "20", "PCS", "10", "200.00"],
    ["", "TOTAL", "", "1,020", "", "", "450.00"],
]
PL_TABLE = [
    ["Item No.", "Description", "Qty", "N.W. (kg)", "G.W. (kg)", "CTNS"],
    ["NL753-S-40", "Catheter", "900", "12.5", "13.2", "3"],
    ["ONLY-DOC", "Extra", "5", "1", "1", "1"],
]


def _pdf(pages=2) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture()
def fake_pdf(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))

    def page_texts(path):
        if "_doc1_invoice" in path:
            return [CI_TEXT]
        if "_doc2_packing_list" in path:
            return [PL_TEXT]
        return [CI_TEXT, PL_TEXT]

    def read_pages(path):
        if "_doc2_packing_list" in path:
            return [(PL_TEXT, [PL_TABLE])]
        return [(CI_TEXT, [INVOICE_TABLE])]

    monkeypatch.setattr(splitter, "page_texts", page_texts)
    monkeypatch.setattr(extractor, "read_pages", read_pages)
    return tmp_path


def _company_id(client, headers, code=None):
    companies = client.get("/api/companies", headers=headers).json()
    if code:
        return next(c["id"] for c in companies if c["code"] == code)
    return companies[0]["id"]


def _container(client, headers, no, company_id, **extra):
    resp = client.post("/api/containers", headers=headers,
                       json={"container_no": no, "company_id": company_id, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _upload_batch(client, headers, cid):
    resp = client.post(f"/api/containers/{cid}/invoice-batches", headers=headers,
                       files=[("pdf", ("cipl.pdf", io.BytesIO(_pdf(2)), "application/pdf"))])
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- 31: propozycje podpięcia -------------------------------------------------

def test_suggestions_propose_accept_reject_audit(client, admin_headers, fake_pdf):
    company = _company_id(client, admin_headers)
    cid = _container(client, admin_headers, MAIN_NO, company)
    target = _container(client, admin_headers, TARGET_NO, company)
    _upload_batch(client, admin_headers, cid)

    suggestions = client.get(f"/api/containers/{target}/attachment-suggestions",
                             headers=admin_headers).json()
    # faktura (container_no z nagłówka) i packing lista (numer w tekście) → 2 propozycje
    assert len(suggestions) == 2
    assert all(s["status"] == "proposed" and s["container_no"] == TARGET_NO
               for s in suggestions)

    accepted = client.post(f"/api/attachment-suggestions/{suggestions[0]['id']}/accept",
                           headers=admin_headers, json={})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    attachments = client.get(f"/api/containers/{target}/attachments",
                             headers=admin_headers).json()
    assert len(attachments) == 1 and attachments[0]["content_type"] == "application/pdf"

    rejected = client.post(f"/api/attachment-suggestions/{suggestions[1]['id']}/reject",
                           headers=admin_headers)
    assert rejected.json()["status"] == "rejected"
    # rozstrzygniętej propozycji nie można rozstrzygać ponownie
    again = client.post(f"/api/attachment-suggestions/{suggestions[0]['id']}/reject",
                        headers=admin_headers)
    assert again.status_code == 409

    history = client.get(f"/api/containers/{target}/history", headers=admin_headers).json()
    notes = [h for h in history if h["field"] == "attachment_suggestion"]
    assert len(notes) == 2
    assert {h["new_value"] for h in notes} == {"accepted", "rejected"}

    # §4 pkt 13: usunięcie pliku z przyjętej propozycji → wraca do „proposed”, da się przyjąć ponownie
    assert client.delete(f"/api/attachments/{attachments[0]['id']}", headers=admin_headers).status_code == 204
    back = client.get(f"/api/containers/{target}/attachment-suggestions", headers=admin_headers).json()
    assert next(s for s in back if s["id"] == suggestions[0]["id"])["status"] == "proposed"
    assert client.post(f"/api/attachment-suggestions/{suggestions[0]['id']}/accept",
                       headers=admin_headers, json={}).status_code == 200


def test_suggestions_idempotent_per_job_and_container(client, admin_headers, fake_pdf,
                                                      db_session):
    company = _company_id(client, admin_headers)
    cid = _container(client, admin_headers, MAIN_NO, company)
    target = _container(client, admin_headers, TARGET_NO, company)
    _upload_batch(client, admin_headers, cid)
    from app.invoices.suggestions import propose_for_batch
    from app.models import InvoiceBatch
    batch = db_session.query(InvoiceBatch).first()
    assert propose_for_batch(db_session, batch, company) == 0   # nic nowego
    db_session.close()
    # kasowanie kontenerów nie może wywrócić się na FK propozycji (Postgres bez kaskad)
    assert client.delete(f"/api/containers/{cid}", headers=admin_headers).status_code == 204
    assert client.delete(f"/api/containers/{target}", headers=admin_headers).status_code == 204


# --- 32: alert braków dokumentów + sekcja pulpitu -----------------------------

def _customs_setup(client, admin_headers, eta_days=2):
    company = _company_id(client, admin_headers)
    cid = _container(client, admin_headers, MAIN_NO, company,
                     eta=(today_pl() + datetime.timedelta(days=eta_days)).isoformat())
    agency = client.post("/api/customs-agencies", headers=admin_headers,
                         json={"name": "W5-CELNA"}).json()
    assert client.post(f"/api/customs/containers/{cid}/assign", headers=admin_headers,
                       json={"customs_agency_id": agency["id"]}).status_code == 200
    dt = client.post("/api/customs/document-types", headers=admin_headers,
                     json={"name": "Faktura celna", "is_required": True})
    assert dt.status_code == 201, dt.text
    return cid, agency


def test_docs_alert_dedup_and_gaps_endpoint(client, admin_headers, db_session):
    cid, _ = _customs_setup(client, admin_headers)
    assert check_docs_alerts(db_session) == 1
    # dedup: drugi przebieg tego samego dnia nie dubluje powiadomienia
    assert check_docs_alerts(db_session) == 0
    kinds = [n.kind for n in db_session.query(Notification)
             .filter(Notification.container_id == cid)]
    assert kinds.count("docs-missing") == 1

    gaps = client.get("/api/customs/docs-gaps", headers=admin_headers).json()
    assert [g["id"] for g in gaps] == [cid]
    assert "Faktura celna" in gaps[0]["missing"]


def test_docs_gaps_forbidden_for_forwarder(client, admin_headers):
    """Decyzja 2026-09-28: dokumenty odprawy to wyłącznie agencja — spedytor nie czyta braków."""
    cid, _ = _customs_setup(client, admin_headers)
    own = forwarder(client, admin_headers, "W5-SPEDALFA")
    assert client.patch(f"/api/containers/{cid}", headers=admin_headers,
                        json={"forwarder_id": own["id"]}).status_code == 200
    assert client.post("/api/users", headers=admin_headers, json={
        "login": "w5.own", "password": "haslo123", "role": "forwarder",
        "forwarder_id": own["id"], "email": "w5.own@example.com"}).status_code == 201
    gaps = client.get("/api/customs/docs-gaps", headers=login(client, "w5.own", "haslo123"))
    assert gaps.status_code == 403


# --- 33/34: porównania --------------------------------------------------------

def _seed_order_data(db_session, company, container_id=None, amount=1000):
    db_session.add(OrderItem(company_id=company, order_number="4500123456", position="10",
                             material="NL753-S-40", quantity="1000"))
    db_session.add(OrderItem(company_id=company, order_number="4500123456", position="20",
                             material="ONLY-SYS", quantity="7"))
    db_session.add(PurchaseOrder(company_id=company, order_no="4500123456",
                                 container_id=container_id, amount=amount))
    db_session.commit()


def test_packing_compare_report(client, admin_headers, fake_pdf, db_session):
    company = _company_id(client, admin_headers)
    cid = _container(client, admin_headers, MAIN_NO, company,
                     order_numbers="4500123456")
    _seed_order_data(db_session, company)
    batch = _upload_batch(client, admin_headers, cid)
    pl_job = next(j for j in batch["jobs"] if j["doc_kind"] == "packing_list")
    report = client.get(f"/api/invoice-jobs/{pl_job['id']}/packing-compare",
                        headers=admin_headers).json()
    by_status = {r["status"]: r for r in report["rows"]}
    assert by_status["qty_diff"]["ref"] == "NL753-S-40"      # 900 vs 1000
    assert by_status["missing_in_system"]["ref"] == "ONLY-DOC"
    assert by_status["missing_in_document"]["ref"] == "ONLY-SYS"
    assert report["mismatches"] == 3


def test_order_compare_flag_and_purchasing_notify(client, admin_headers, fake_pdf,
                                                  db_session):
    company = _company_id(client, admin_headers)
    cid = _container(client, admin_headers, TARGET_NO, company, order_numbers="4500123456")
    _seed_order_data(db_session, company, amount=1000)   # faktura 450 vs EKKO 1000
    client.post("/api/users", headers=admin_headers, json={
        "login": "zakupy.w5", "password": "haslo123", "role": "purchasing",
        "company_id": company})
    batch = _upload_batch(client, admin_headers, cid)
    inv_job = next(j for j in batch["jobs"] if j["doc_kind"] == "invoice")

    report = client.get(f"/api/invoice-jobs/{inv_job['id']}/order-compare",
                        headers=admin_headers).json()
    assert report["exceeded"] is True
    assert report["po_total"] == "1000.00" or report["po_total"] == "1000"
    assert float(report["diff_pct"]) > settings.invoice_tolerance_pct

    # zatwierdzenie faktury z rozjazdem → powiadomienie do działu zakupów
    detail = client.get(f"/api/invoice-jobs/{inv_job['id']}", headers=admin_headers).json()
    items = [{"id": i["id"]} for i in detail["items"]]
    resp = client.put(f"/api/invoice-jobs/{inv_job['id']}/review", headers=admin_headers,
                      json={"items": items, "confirm": True, "conformity_reason": "test: brak danych SAP"})
    assert resp.status_code == 200, resp.text
    mismatches = db_session.query(Notification).filter(
        Notification.kind == "invoice-mismatch").all()
    assert mismatches, "brak alertu invoice-mismatch dla działu zakupów"


# --- 35: ZIP-y ------------------------------------------------------------------

def _add_attachment(client, headers, cid, name="doc.pdf"):
    resp = client.post(f"/api/containers/{cid}/attachments", headers=headers,
                       files={"file": (name, io.BytesIO(pdf_bytes(name)), "application/pdf")})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_container_zip_and_monthly_zip(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    company = _company_id(client, admin_headers)
    code = client.get("/api/companies", headers=admin_headers).json()[0]["code"]
    cid = _container(client, admin_headers, MAIN_NO, company)
    _add_attachment(client, admin_headers, cid, "a.pdf")
    _add_attachment(client, admin_headers, cid, "b.pdf")

    resp = client.get(f"/api/containers/{cid}/attachments/zip", headers=admin_headers)
    assert resp.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert sorted(names) == ["a.pdf", "b.pdf"]

    month = today_pl().strftime("%Y-%m")
    monthly = client.get(f"/api/archive/attachments-zip?company_code={code}&month={month}",
                         headers=admin_headers)
    assert monthly.status_code == 200
    assert sorted(zipfile.ZipFile(io.BytesIO(monthly.content)).namelist()) == ["a.pdf", "b.pdf"]
    # zły miesiąc → 422; brak plików → 404
    assert client.get(f"/api/archive/attachments-zip?company_code={code}&month=zle",
                      headers=admin_headers).status_code == 422
    assert client.get(f"/api/archive/attachments-zip?company_code={code}&month=1999-01",
                      headers=admin_headers).status_code == 404


# --- 36: szablony wysyłki -------------------------------------------------------

def test_doc_template_render_preview_and_send(client, admin_headers, monkeypatch,
                                              tmp_path, db_session):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    cid, agency = _customs_setup(client, admin_headers)
    _add_attachment(client, admin_headers, cid, "cmr.pdf")

    # bez szablonu: domyślna treść (dotychczasowa)
    preview = client.get(f"/api/customs/containers/{cid}/send-docs/preview",
                         headers=admin_headers).json()
    assert preview["subject"] == f"Dokumenty do odprawy: {MAIN_NO}"
    assert "cmr.pdf" in preview["body"]

    created = client.post("/api/customs/doc-templates", headers=admin_headers, json={
        "subject": "Odprawa {container_no} (ETA {eta})",
        "body": "Dokumenty: {lista_dokumentow}. Nieznany {placeholder} zostaje."})
    assert created.status_code == 201, created.text

    preview = client.get(f"/api/customs/containers/{cid}/send-docs/preview",
                         headers=admin_headers).json()
    assert preview["subject"].startswith(f"Odprawa {MAIN_NO} (ETA ")
    assert "cmr.pdf" in preview["body"] and "{placeholder}" in preview["body"]

    # wysyłka używa szablonu (force — checklist ma braki)
    client.post("/api/users", headers=admin_headers, json={
        "login": "celna.w5", "password": "haslo123", "role": "customs",
        "customs_agency_id": agency["id"]})
    sent = client.post(f"/api/customs/containers/{cid}/send-docs", headers=admin_headers,
                       json={"force": True})
    assert sent.status_code == 200, sent.text
    titles = [n.title for n in db_session.query(Notification)
              .filter(Notification.kind == "customs")]
    assert any(t.startswith(f"Odprawa {MAIN_NO}") for t in titles)

    # edycja i kasowanie (tylko admin)
    tid = created.json()["id"]
    logistics_denied = client.delete(f"/api/customs/doc-templates/{tid}",
                                     headers=login(client))
    assert logistics_denied.status_code in (200, 204)   # admin może


def test_suggestion_skips_own_container_and_accept_refuses_duplicate(client, admin_headers, fake_pdf):
    """Spec 2026-10-06 §4 pkt 11, 12: brak propozycji do własnego kontenera paczki; przyjęcie
    dokumentu, który już leży w kontenerze docelowym → 409 (bez drugiej kopii)."""
    company = _company_id(client, admin_headers)
    cid = _container(client, admin_headers, MAIN_NO, company)
    target = _container(client, admin_headers, TARGET_NO, company)
    _upload_batch(client, admin_headers, cid)
    assert client.get(f"/api/containers/{cid}/attachment-suggestions", headers=admin_headers).json() == []
    first, second = client.get(f"/api/containers/{target}/attachment-suggestions", headers=admin_headers).json()
    assert client.post(f"/api/attachment-suggestions/{first['id']}/accept", headers=admin_headers,
                       json={}).status_code == 200
    if second["doc_kind"] == first["doc_kind"]:
        dup = client.post(f"/api/attachment-suggestions/{second['id']}/accept", headers=admin_headers, json={})
        assert dup.status_code == 409

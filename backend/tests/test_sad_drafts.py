"""Agencja celna — PR 1 (spec 2026-09-29-agencja-draft-sad): potwierdzenie odbioru, wersje
draftu SAD (duplikat pliku bez nowej wersji), decyzja z blokadą starej wersji, audyt."""
import io

from pypdf import PdfWriter
from sqlalchemy import select

from app.config import settings
from app.invoices import extractor
from app.invoices.extractor import PageData
from app.models import AuditLog, InvoiceBatch, SadDraft
from tests.test_invoices_api import _container
from tests.test_sad_parse import SAD


def _pdf(marker: str = "v1") -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": marker})          # inna treść = inny sha256
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _batch(client, headers, db_session, no="MSDU0806613") -> tuple[int, int]:
    cid = _container(client, headers, no=no)
    batch = InvoiceBatch(container_id=cid)
    db_session.add(batch)
    db_session.commit()
    return cid, batch.id


def _upload(client, headers, bid, content, name="SAD.pdf"):
    return client.post(f"/api/invoice-batches/{bid}/sad-drafts", headers=headers,
                       files={"file": (name, io.BytesIO(content), "application/pdf")})


def test_ack_then_versions_dedupe_and_state(client, admin_headers, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    cid, bid = _batch(client, admin_headers, db_session)
    state = client.get(f"/api/invoice-batches/{bid}/sad-drafts", headers=admin_headers).json()
    assert state == {"ack": None, "drafts": []}

    assert client.post(f"/api/invoice-batches/{bid}/agency-ack", headers=admin_headers).status_code == 200
    first = client.post(f"/api/invoice-batches/{bid}/agency-ack", headers=admin_headers).json()
    assert first["ack"]["source"] == "manual"                       # idempotentne

    r1 = _upload(client, admin_headers, bid, _pdf("v1"))
    assert r1.status_code == 201 and r1.json()["created"] is True
    dup = _upload(client, admin_headers, bid, _pdf("v1"), name="kopia.pdf")
    assert dup.status_code == 200 and dup.json()["created"] is False  # ten sam plik
    r2 = _upload(client, admin_headers, bid, _pdf("v2"))
    state = r2.json()["state"]
    assert [d["version"] for d in state["drafts"]] == [2, 1]
    assert state["drafts"][0]["decision"] == "pending" and state["drafts"][0]["attachment_id"]
    logs = db_session.scalars(select(AuditLog).where(AuditLog.field == "sad_draft")).all()
    assert len(logs) == 2 and all(log.entity_id == cid for log in logs)


def test_decision_rules(client, admin_headers, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    _, bid = _batch(client, admin_headers, db_session)
    v1 = _upload(client, admin_headers, bid, _pdf("v1")).json()["draft"]["id"]
    url = f"/api/invoice-batches/{bid}/sad-drafts/{v1}/decision"
    bad = client.post(url, headers=admin_headers, json={"decision": "rejected", "comment": " "})
    assert bad.status_code == 422                                    # „do poprawy” wymaga uwag
    ok = client.post(url, headers=admin_headers,
                     json={"decision": "rejected", "comment": "CN 62101092 zamiast 62101098"})
    assert ok.status_code == 200 and ok.json()["drafts"][0]["decision"] == "rejected"

    _upload(client, admin_headers, bid, _pdf("v2"))
    stale = client.post(url, headers=admin_headers, json={"decision": "accepted", "comment": ""})
    assert stale.status_code == 409                                  # jest nowsza wersja
    v2 = db_session.scalar(select(SadDraft).where(SadDraft.version == 2)).id
    done = client.post(f"/api/invoice-batches/{bid}/sad-drafts/{v2}/decision",
                       headers=admin_headers, json={"decision": "accepted", "comment": ""})
    assert done.status_code == 200 and done.json()["drafts"][0]["decision"] == "accepted"


def test_upload_rejects_non_pdf_and_foreign_draft(client, admin_headers, db_session,
                                                  monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    _, bid = _batch(client, admin_headers, db_session)
    r = client.post(f"/api/invoice-batches/{bid}/sad-drafts", headers=admin_headers,
                    files={"file": ("sad.xlsx", io.BytesIO(b"x"), "application/octet-stream")})
    assert r.status_code == 422
    _, other = _batch(client, admin_headers, db_session, no="TGBU6784203")
    v1 = _upload(client, admin_headers, other, _pdf("v1")).json()["draft"]["id"]
    r = client.post(f"/api/invoice-batches/{bid}/sad-drafts/{v1}/decision",
                    headers=admin_headers, json={"decision": "accepted", "comment": ""})
    assert r.status_code == 404


def test_compare_parses_once_and_keeps_summary(client, admin_headers, db_session,
                                               monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    calls = []
    monkeypatch.setattr(extractor, "read_pages",
                        lambda path: calls.append(path) or [PageData(text=SAD)])
    _, bid = _batch(client, admin_headers, db_session)
    v1 = _upload(client, admin_headers, bid, _pdf("v1")).json()["draft"]["id"]
    url = f"/api/invoice-batches/{bid}/sad-drafts/{v1}/compare"
    first = client.post(url, headers=admin_headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["pages"] == 1 and body["version"] == 1 and body["at"]
    assert {g["status"] for g in body["groups"]} == {"extra_in_sad"}   # paczka bez faktur
    assert client.post(url, headers=admin_headers).status_code == 200
    assert len(calls) == 1                                              # odczyt PDF raz (cache)
    logs = db_session.scalars(select(AuditLog).where(AuditLog.field == "sad_compare")).all()
    assert len(logs) == 1 and logs[0].old_value is None             # audyt tylko zmiany wyniku
    state =client.get(f"/api/invoice-batches/{bid}/sad-drafts", headers=admin_headers).json()
    assert state["drafts"][0]["summary"]["groups"] == 2
    assert client.post(f"/api/invoice-batches/{bid}/sad-drafts/999999/compare",
                       headers=admin_headers).status_code == 404


def test_page_preview_png_and_bounds(client, admin_headers, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    _, bid = _batch(client, admin_headers, db_session)
    v1 = _upload(client, admin_headers, bid, _pdf("v1")).json()["draft"]["id"]
    page = client.get(f"/api/invoice-batches/{bid}/sad-drafts/{v1}/pages/1", headers=admin_headers)
    assert page.status_code == 200 and page.headers["content-type"] == "image/png"
    assert page.content.startswith(b"\x89PNG")
    assert client.get(f"/api/invoice-batches/{bid}/sad-drafts/{v1}/pages/2",
                      headers=admin_headers).status_code == 404


def test_batch_with_agency_answer_cannot_be_deleted(client, admin_headers, db_session, monkeypatch, tmp_path):
    """Spec 2026-10-06 §4 pkt 7: usunięcie paczki kasowało kaskadą drafty SAD i potwierdzenie agencji."""
    from app.config import settings
    from tests.test_invoice_conformity import CI, OWN, _container
    from tests.test_invoice_conformity import _upload as _upload_batch
    from tests.test_invoices_checks import _setup
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    batch_id, _ = _upload_batch(client, admin_headers, monkeypatch, cid, f"{CI}\nCONTAINER No.: {OWN}")
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    assert client.post(f"/api/invoice-batches/{batch_id}/agency-ack", headers=admin_headers).status_code == 200
    resp = client.delete(f"/api/invoice-batches/{batch_id}", headers=admin_headers)
    assert resp.status_code == 409 and "agencji" in resp.json()["detail"]

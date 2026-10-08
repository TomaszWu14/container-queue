"""Drafty SAD — spec dokumenty-dostaw §4 pkt 19–22: bramka PDF przy ręcznym wgraniu, dzwonek
o nowej wersji, numer kontenera w dwóch spółkach w skrzynce automatu, „Draft SAD” z kafelka
w obiegu wersji."""
import io

from sqlalchemy import select

from app.config import settings
from app.invoices import sad_drafts
from app.models import Container, Company, InvoiceBatch, SadDraft
from tests.test_document_gate import OTHER, _text_pdf
from tests.test_sad_drafts import _batch, _pdf, _upload
from tests.test_sad_inbox import _pdf_reads, _send


def test_manual_draft_gate_and_notification(client, admin_headers, db_session, monkeypatch, tmp_path):
    """19: uszkodzony PDF → 422, draft innego kontenera → 409; 20: nowa wersja = dzwonek."""
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    calls = []
    monkeypatch.setattr(sad_drafts, "notify", lambda db, users, **kw: calls.append(kw) or 0)
    _, bid = _batch(client, admin_headers, db_session)
    assert _upload(client, admin_headers, bid, b"%PDF-1.4 atrapa").status_code == 422
    wrong = _upload(client, admin_headers, bid, _text_pdf(tmp_path, f"JEDNOLITY DOKUMENT ADMINISTRACYJNY DRAFT\n{OTHER} 40HQ"))
    assert wrong.status_code == 409 and OTHER in wrong.json()["detail"]
    assert calls == []
    assert _upload(client, admin_headers, bid, _pdf("v1")).status_code == 201
    assert len(calls) == 1 and calls[0]["title"].startswith("Draft SAD v1 przy MSDU0806613")


def test_inbox_refuses_container_number_in_two_companies(client, admin_headers, db_session,
                                                         monkeypatch, tmp_path):
    """21: ten sam numer kontenera w dwóch spółkach — automat nie zgaduje paczki."""
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    _pdf_reads(monkeypatch, "MSDU0806613")
    first_cid, _ = _batch(client, admin_headers, db_session)
    own = db_session.get(Container, first_cid).company_id
    other_company = next(c.id for c in db_session.scalars(select(Company)) if c.id != own)
    cid = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MSDU0806613", "company_id": other_company}).json()["id"]
    db_session.add(InvoiceBatch(container_id=cid))
    db_session.commit()
    r = _send(client, admin_headers, _pdf("x"), "SAD.pdf")
    assert r.status_code == 409 and "kilku spółkach" in r.json()["detail"]


def test_sad_draft_tile_upload_becomes_draft_version(client, admin_headers, db_session,
                                                     monkeypatch, tmp_path):
    """22: plik z typem „Draft SAD” przy kontenerze z paczką faktur = wersja draftu."""
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    cid, bid = _batch(client, admin_headers, db_session)
    type_id = sad_drafts._doc_type(db_session).id
    db_session.commit()
    resp = client.post(f"/api/containers/{cid}/attachments", headers=admin_headers,
                       data={"document_type_id": str(type_id)},
                       files={"file": ("SAD.pdf", io.BytesIO(_pdf("kafelek")), "application/pdf")})
    assert resp.status_code == 201, resp.text
    draft = db_session.scalar(select(SadDraft).where(SadDraft.batch_id == bid))
    assert draft is not None and draft.version == 1 and draft.attachment_id == resp.json()["id"]

"""Poczta → poczekalnia (spec 2026-10-06-dokumenty-dostaw, decyzja 27): n8n wysyła cały mail bez
kontekstu kontenera — wgranie na każdy kontener z treści, reszta „bez dopasowania” dla logistyki
spółki; ponowne wysłanie tego samego maila nie tworzy dubli."""
import io
from email.message import EmailMessage

from sqlalchemy import select

from app.config import settings
from app.models import Attachment, IntakeBatch, Notification, Role
from app.security import AUTOMATION_HEADER, create_access_token
from tests.test_document_gate import OWN, _text_pdf
from tests.test_idor_scoping import _mk
from tests.test_intake import _start
from tests.test_invoice_conformity import _container

B = "CSQU3054383"
TOKEN = "test-automation-token-at-least-32-chars"
BODY = "BILL OF LADING SHIPPED ON BOARD 40HQ said to contain"


def _mail(tmp_path, *pdfs: tuple[str, str], subject="Dokumenty") -> bytes:
    msg = EmailMessage()
    msg["Subject"], msg["From"] = subject, "agent@example.com"
    msg.set_content("W załączeniu.")
    for name, text in pdfs:
        msg.add_attachment(_text_pdf(tmp_path, text), "application", "pdf", filename=name)
    return msg.as_bytes()


def _inbox(client, headers, data: bytes, subject="Dokumenty"):
    return client.post("/api/intake/inbox", headers=headers, data={"subject": subject, "sender": "agent@x"},
                       files={"file": ("poczta.eml", io.BytesIO(data))})


def _hdr(db, login, role, **extra) -> dict:
    user = _mk(db, "users", login=login, role=role, **extra)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _service(client, db, monkeypatch, company) -> dict:
    """Konto automatu „n8n” (logistyka spółki) — żądanie wyłącznie z tokenem, bez sesji."""
    _mk(db, "users", login="n8n", role=Role.logistics, company_id=company.id)
    db.commit()
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    monkeypatch.setattr(settings, "automation_actor_login", "n8n")
    client.cookies.clear()
    return {AUTOMATION_HEADER: TOKEN}


def test_mail_split_per_container_and_idempotent(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    b_id = _container(client, admin_headers, company, sup, no=B)
    mail = _mail(tmp_path, ("bl_a.pdf", f"{BODY}\n{OWN}"), ("bl_b.pdf", f"{BODY}\n{B}"))
    headers = _service(client, db_session, monkeypatch, company)
    resp = _inbox(client, headers, mail)
    assert resp.status_code == 201, resp.text
    out = resp.json()
    got = {b["container_no"]: b["items"] for b in out["batches"]}
    assert got == {OWN: 2, B: 1}   # sam mail (korespondencja) idzie do pierwszego kontenera
    batch = db_session.get(IntakeBatch, out["batches"][0]["batch_id"])
    assert (batch.source, batch.note, batch.company_id) == ("mail", "agent@x · Dokumenty", company.id)
    titles = set(db_session.scalars(select(Notification.title)))
    assert f"Poczta: 1 dokumentów do sprawdzenia w poczekalni {B}" in titles
    # ten sam mail ponownie → 200, te same wgrania
    again = _inbox(client, headers, mail)
    assert again.status_code == 200 and again.json()["batches"] == out["batches"]
    assert len(db_session.scalars(select(IntakeBatch)).all()) == 2
    # zwykła lista poczekalni kontenera widzi wgranie z poczty
    pending = client.get(f"/api/containers/{b_id}/intake", headers=admin_headers).json()
    assert [p["source"] for p in pending] == ["mail"]


def test_unmatched_visible_to_company_retarget_confirm(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, _, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    headers = _service(client, db_session, monkeypatch, company)
    out = _inbox(client, headers, _mail(tmp_path, ("nic.pdf", f"{BODY} bez numeru"))).json()
    assert [b["container_no"] for b in out["batches"]] == [None]
    batch_id = out["batches"][0]["batch_id"]
    own = _hdr(db_session, "log_a", Role.logistics, company_id=company.id)
    stranger = _mk(db_session, "companies", name="Obca", code="OBC")
    other = _hdr(db_session, "log_b", Role.logistics, company_id=stranger.id)
    assert [b["id"] for b in client.get("/api/intake/unmatched", headers=own).json()] == [batch_id]
    assert client.get("/api/intake/unmatched", headers=other).json() == []
    assert client.get(f"/api/intake/{batch_id}", headers=other).status_code == 404
    items = client.get(f"/api/intake/{batch_id}", headers=own).json()["items"]
    assert {i["gate_status"] for i in items} == {"uncertain"}
    # potwierdzenie wymaga kontenera dla każdej nieodrzuconej części
    assert client.post(f"/api/intake/{batch_id}/confirm", headers=own).status_code == 409
    for item in items:
        r = client.patch(f"/api/intake/items/{item['id']}", headers=own, json={"target_container_id": cid})
        assert r.status_code == 200, r.text
    summary = client.post(f"/api/intake/{batch_id}/confirm", headers=own)
    assert summary.status_code == 200, summary.text
    assert summary.json()["containers"] == {OWN: {"invoices": 0, "attachments": 2}}
    assert db_session.scalar(select(Attachment.id).where(Attachment.container_id == cid,
                                                         Attachment.filename == "nic.pdf"))
    assert client.get("/api/intake/unmatched", headers=own).json() == []


def test_inbox_roles(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, _, _ = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    fwd = _mk(db_session, "forwarders", name="Spedytor X")
    wh = _mk(db_session, "warehouses", name="Magazyn X", company_id=company.id)
    for login, role, extra in (("sped", Role.forwarder, {"forwarder_id": fwd.id}),
                               ("mag", Role.warehouse, {"warehouse_id": wh.id})):
        headers = _hdr(db_session, login, role, **extra)
        assert _inbox(client, headers, b"x").status_code == 403
        assert client.get("/api/intake/unmatched", headers=headers).status_code == 403

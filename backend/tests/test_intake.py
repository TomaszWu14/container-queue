"""Poczekalnia dokumentów (spec 2026-10-06-dokumenty-dostaw §2–§3): wgranie tnie i typuje części,
bramki (dubel, inny kontener) działają przed przypisaniem, nic nie trafia do dostawy przed
„Potwierdź”; potwierdzenie = paczka faktur + załączniki z typem, odrzucenie sprząta pliki."""
import io
import pathlib
import zipfile

import pdfplumber
from sqlalchemy import select

from app.invoices import splitter
from app.models import (Attachment, Container, DocumentStatus, DocumentType, IntakeBatch,
                        InvoiceBatch, Role)
from app.security import create_access_token
from tests.test_document_gate import OTHER, OWN, _text_pdf
from tests.test_idor_scoping import _mk
from tests.test_invoice_conformity import _container
from tests.test_invoices_checks import CI, PL, _setup
from tests.test_sad_parse import _pdf_with_text


def _texts(path) -> list[str]:
    """Warstwa tekstowa stron bez OCR (pdfplumber) — splitter tnie po prawdziwej treści."""
    with pdfplumber.open(path) as pdf:
        return [p.extract_text() or "" for p in pdf.pages]


def _cipl(tmp_path) -> bytes:
    """Zestaw CI + PL (dwie strony z tekstem) — części różnią się treścią, nie tylko numerem."""
    path = tmp_path / "cipl_src.pdf"
    _pdf_with_text(path, [[(40, 800, CI)], [(40, 800, PL)]])
    return path.read_bytes()


def _start(client, headers, db, monkeypatch, tmp_path):
    company, sup = _setup(db, monkeypatch, tmp_path)
    monkeypatch.setattr(splitter, "page_texts", _texts)
    if db.scalar(select(DocumentType).where(DocumentType.tile_code == "BL")) is None:
        db.add(DocumentType(name="Konosament", is_active=True, tile_code="BL"))
        db.commit()
    return company, sup, _container(client, headers, company, sup)


def _post(client, headers, cid, files: dict[str, bytes]):
    return client.post(f"/api/containers/{cid}/intake", headers=headers,
                       files=[("files", (n, io.BytesIO(d))) for n, d in files.items()])


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buf.getvalue()


def _by_type(body) -> dict[str, dict]:
    return {i["doc_type"]: i for i in body["items"]}


def _intake_files(tmp_path) -> list[str]:
    return [p.name for p in pathlib.Path(tmp_path).iterdir() if p.name.startswith("intake_")]


def test_upload_splits_types_and_waits(client, admin_headers, db_session, monkeypatch, tmp_path):
    _, _, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    bl = _text_pdf(tmp_path, f"BILL OF LADING SHIPPED ON BOARD\n{OWN} 40HQ")
    resp = _post(client, admin_headers, cid, {
        "cipl.pdf": _cipl(tmp_path), "kalk.xlsx": b"x1",
        "folder.zip": _zip({"4500/bl.pdf": bl, "4500/skrypt.exe": b"MZ"})})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    items = _by_type(body)
    assert set(items) == {"CI", "PL", "OTHER", "BL"}
    assert (items["CI"]["page_from"], items["PL"]["page_to"], items["PL"]["pages"]) == (1, 2, 2)
    assert items["CI"]["gate_status"] == items["PL"]["gate_status"] == "uncertain"   # bez numeru
    assert items["BL"]["gate_status"] == "ok" and items["OTHER"]["gate_status"] == "ok"
    assert all(i["target_container_no"] == OWN and i["decision"] == "pending" for i in body["items"])
    assert body["skipped"] == ["skrypt.exe (niedozwolony typ)"]
    # nic w dostawie przed „Potwierdź” (decyzja 11)
    assert db_session.scalar(select(Attachment).where(Attachment.container_id == cid)) is None
    assert db_session.scalar(select(InvoiceBatch).where(InvoiceBatch.container_id == cid)) is None
    assert len(_intake_files(tmp_path)) == 4                  # części, bez całego zestawu
    preview = client.get(f"/api/intake/items/{items['BL']['id']}/file", headers=admin_headers)
    assert preview.status_code == 200 and preview.content == bl
    pending = client.get(f"/api/containers/{cid}/intake", headers=admin_headers).json()
    assert [b["id"] for b in pending] == [body["id"]]


def test_duplicates_in_batch_and_in_container(client, admin_headers, db_session, monkeypatch, tmp_path):
    _, _, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    assert client.post(f"/api/containers/{cid}/attachments", headers=admin_headers,
                       files={"file": ("stary.xlsx", io.BytesIO(b"old"))}).status_code == 201
    body = _post(client, admin_headers, cid, {"a.xlsx": b"same", "b.xlsx": b"same",
                                              "kopia.xlsx": b"old"}).json()
    gates = {i["original_name"]: (i["gate_status"], i["gate_message"]) for i in body["items"]}
    assert gates["a.xlsx"] == ("ok", "")
    assert gates["b.xlsx"] == ("duplicate", "powtórzony w tym wgraniu")
    assert gates["kopia.xlsx"][0] == "duplicate" and "stary.xlsx" in gates["kopia.xlsx"][1]
    summary = client.post(f"/api/intake/{body['id']}/confirm", headers=admin_headers).json()
    assert summary["containers"] == {OWN: {"invoices": 0, "attachments": 1}}
    assert len(summary["skipped"]) == 2


def test_conflict_needs_retarget(client, admin_headers, db_session, monkeypatch, tmp_path):
    _, _, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    # kontener innej spółki — bez auto-rozdziału (decyzja 13 dotyczy tylko kontenerów tej spółki)
    stranger = _mk(db_session, "companies", name="Obca B/L", code="OBL")
    other_id = _mk(db_session, "containers", container_no=OTHER, company_id=stranger.id).id
    db_session.commit()
    bl = _text_pdf(tmp_path, f"BILL OF LADING SHIPPED ON BOARD\n{OTHER} 40HQ")
    first = _post(client, admin_headers, cid, {"bl.pdf": bl}).json()
    item = first["items"][0]
    assert item["gate_status"] == "conflict"
    assert item["found_containers"] == [{"container_no": OTHER, "container_id": other_id}]
    # bez „Przenieś do …” / „Odrzuć” konflikt blokuje potwierdzenie — część czeka (decyzja 12)
    blocked = client.post(f"/api/intake/{first['id']}/confirm", headers=admin_headers)
    assert blocked.status_code == 409 and "bl.pdf" in blocked.json()["detail"]
    second = first
    item_id = item["id"]
    resp = client.patch(f"/api/intake/items/{item_id}", headers=admin_headers,
                        json={"target_container_id": other_id})
    assert resp.status_code == 200 and resp.json()["target_container_no"] == OTHER
    summary = client.post(f"/api/intake/{second['id']}/confirm", headers=admin_headers).json()
    assert summary["containers"] == {OTHER: {"invoices": 0, "attachments": 1}}
    att = db_session.scalar(select(Attachment).where(Attachment.container_id == other_id))
    assert att.document_type.tile_code == "BL" and att.stored_name.startswith(f"{other_id}_")


def test_patch_and_confirm_writes_to_delivery(client, admin_headers, db_session, monkeypatch, tmp_path):
    _, _, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    body = _post(client, admin_headers, cid, {"cipl.pdf": _cipl(tmp_path), "note.xlsx": b"n1",
                                              "zbedny.xlsx": b"n2"}).json()
    items = {i["original_name"]: i for i in body["items"]}
    resp = client.patch(f"/api/intake/items/{items['note.xlsx']['id']}", headers=admin_headers,
                        json={"doc_type": "BL"})
    assert resp.status_code == 200 and resp.json()["doc_type"] == "BL"
    assert client.patch(f"/api/intake/items/{items['zbedny.xlsx']['id']}", headers=admin_headers,
                        json={"decision": "rejected"}).status_code == 200
    assert client.patch(f"/api/intake/items/{items['note.xlsx']['id']}", headers=admin_headers,
                        json={"doc_type": "XX"}).status_code == 422
    summary = client.post(f"/api/intake/{body['id']}/confirm", headers=admin_headers).json()
    assert summary["containers"] == {OWN: {"invoices": 2, "attachments": 1}}
    assert summary["skipped"] == ["zbedny.xlsx (odrzucony)"]
    db_session.expire_all()
    assert db_session.scalar(select(InvoiceBatch).where(InvoiceBatch.container_id == cid)) is not None
    att = db_session.scalar(select(Attachment).where(Attachment.container_id == cid))
    assert att.filename == "note.xlsx" and att.document_type.tile_code == "BL" and att.sha256
    assert db_session.get(Container, cid).document_status == DocumentStatus.ZALACZONE
    assert db_session.get(IntakeBatch, body["id"]).status == "confirmed"
    assert _intake_files(tmp_path) == []
    # zamknięte wgranie: bez ponownego potwierdzenia i edycji
    assert client.post(f"/api/intake/{body['id']}/confirm", headers=admin_headers).status_code == 409
    assert client.patch(f"/api/intake/items/{items['note.xlsx']['id']}", headers=admin_headers,
                        json={"doc_type": "OTHER"}).status_code == 409
    assert client.get(f"/api/containers/{cid}/intake", headers=admin_headers).json() == []


def test_discard_removes_files(client, admin_headers, db_session, monkeypatch, tmp_path):
    _, _, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    keep = _post(client, admin_headers, cid, {"a.xlsx": b"a"}).json()
    drop = _post(client, admin_headers, cid, {"b.xlsx": b"b"}).json()
    assert client.post(f"/api/intake/{drop['id']}/discard", headers=admin_headers).status_code == 204
    assert db_session.get(IntakeBatch, drop["id"]).status == "discarded"
    assert len(_intake_files(tmp_path)) == 1
    pending = client.get(f"/api/containers/{cid}/intake", headers=admin_headers).json()
    assert [b["id"] for b in pending] == [keep["id"]]
    assert client.get(f"/api/containers/{cid}/intake?status=discarded",
                      headers=admin_headers).json()[0]["id"] == drop["id"]


def test_other_company_and_forwarder_scope(client, admin_headers, db_session, monkeypatch, tmp_path):
    _, _, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    body = _post(client, admin_headers, cid, {"a.xlsx": b"a"}).json()
    item_id = body["items"][0]["id"]
    stranger = _mk(db_session, "companies", name="Obca", code="OBC")
    db_session.commit()
    for role, extra in ((Role.logistics, {"company_id": stranger.id}), (Role.forwarder, {})):
        if role == Role.forwarder:   # spedytor kontenera — ale wgranie nie jego
            fwd = _mk(db_session, "forwarders", name="Spedytor X")
            db_session.get(Container, cid).forwarder_id = fwd.id
            extra = {"forwarder_id": fwd.id}
        user = _mk(db_session, "users", login=f"obcy_{role.value}", role=role, **extra)
        db_session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(user)}"}
        assert client.get(f"/api/intake/{body['id']}", headers=headers).status_code == 404
        assert client.patch(f"/api/intake/items/{item_id}", headers=headers,
                            json={"decision": "rejected"}).status_code == 404
        assert client.get(f"/api/intake/items/{item_id}/file", headers=headers).status_code == 404
        assert client.post(f"/api/intake/{body['id']}/confirm", headers=headers).status_code == 404
        listed = client.get(f"/api/containers/{cid}/intake", headers=headers)
        assert listed.status_code == 404 or listed.json() == []
    # retarget do kontenera spoza zakresu — 404, a nie cichy zapis
    assert client.patch(f"/api/intake/items/{item_id}", headers=admin_headers,
                        json={"target_container_id": 999999}).status_code == 404

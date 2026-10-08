"""Poczekalnia — maile i zdjęcia (spec 2026-10-06-dokumenty-dostaw, decyzje 8 i 19): .eml/.msg
rozpakowane jak ZIP (wiadomość zostaje jako korespondencja MAIL), JPG/PNG/HEIC → PDF jak skan."""
import io
from email.message import EmailMessage

import pytest
from PIL import Image
from sqlalchemy import select

from app.models import Attachment, DocumentType
from app.routers.intake_unpack import expand
from tests.conftest import pdf_bytes
from tests.test_document_gate import OWN
from tests.test_intake import _post, _start


def _png(size=(60, 40), fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, format=fmt)
    return buf.getvalue()


def _eml(inner: EmailMessage | None = None) -> bytes:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = "Dokumenty MSKU", "agent@example.com", "biuro@example.com"
    msg.set_content("W załączeniu dokumenty.")
    msg.add_alternative('<p>Dokumenty <img src="cid:logo"></p>', subtype="html")
    msg.get_payload()[1].add_related(_png((10, 10)), "image", "png", cid="logo", filename="logo.png",
                                     disposition="inline")
    msg.add_attachment(pdf_bytes("mail"), "application", "pdf", filename="faktura.pdf")
    msg.add_attachment(b"PK-xlsx", "application", "octet-stream", filename="kalkulacja.xlsx")
    if inner is not None:
        msg.add_attachment(inner)
    return msg.as_bytes()


def test_eml_unpacked_mail_kept_logo_skipped(client, admin_headers, db_session, monkeypatch, tmp_path):
    _, _, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    db_session.add(DocumentType(name="Korespondencja", is_active=True))
    db_session.commit()
    resp = _post(client, admin_headers, cid, {"wiadomosc.eml": _eml()})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    items = {i["original_name"]: i for i in body["items"]}
    assert set(items) == {"wiadomosc.eml", "faktura.pdf", "kalkulacja.xlsx"}
    assert items["wiadomosc.eml"]["doc_type"] == "MAIL" and items["wiadomosc.eml"]["gate_status"] == "ok"
    assert items["kalkulacja.xlsx"]["doc_type"] == "OTHER"
    assert items["faktura.pdf"]["gate_status"] == "uncertain"
    assert body["skipped"] == ["logo.png (obraz w treści maila)"]
    summary = client.post(f"/api/intake/{body['id']}/confirm", headers=admin_headers).json()
    assert summary["containers"] == {OWN: {"invoices": 0, "attachments": 3}}
    mail = db_session.scalar(select(Attachment).where(Attachment.container_id == cid,
                                                      Attachment.filename == "wiadomosc.eml"))
    assert mail.document_type.name == "Korespondencja"


def test_nested_eml_and_depth_limit(client, admin_headers, db_session, monkeypatch, tmp_path):
    _, _, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    inner = EmailMessage()
    inner["Subject"] = "fwd"
    inner.set_content("x")
    inner.add_attachment(b"inner-xlsx", "application", "octet-stream", filename="wewn.xlsx")
    body = _post(client, admin_headers, cid, {"m.eml": _eml(inner)}).json()
    names = {i["original_name"]: i["doc_type"] for i in body["items"]}
    assert names["fwd.eml"] == "MAIL" and names["wewn.xlsx"] == "OTHER"


def test_depth_limit():
    deepest = EmailMessage()
    deepest["Subject"] = "d3"
    deepest.set_content("x")
    msg = deepest
    for level in (2, 1, 0):
        outer = EmailMessage()
        outer["Subject"] = f"d{level}"
        outer.set_content("x")
        outer.add_attachment(msg)
        msg = outer
    entries, skipped = expand([("d0.eml", msg.as_bytes())])
    assert [n for n, _ in entries] == ["d0.eml", "d1.eml", "d2.eml"]
    assert skipped == ["d3.eml (zbyt głębokie zagnieżdżenie)"]


@pytest.mark.parametrize("fmt,name", [("JPEG", "zdjecie.jpg"), ("PNG", "skan.png")])
def test_photo_becomes_scanned_pdf(client, admin_headers, db_session, monkeypatch, tmp_path, fmt, name):
    _, _, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    body = _post(client, admin_headers, cid, {name: _png(fmt=fmt)}).json()
    [item] = body["items"]
    assert item["original_name"] == name.rsplit(".", 1)[0] + ".pdf"
    assert item["gate_status"] == "uncertain" and item["pages"] == 1


def test_heic_photo(client, admin_headers, db_session, monkeypatch, tmp_path):
    pillow_heif = pytest.importorskip("pillow_heif")
    pillow_heif.register_heif_opener()
    buf = io.BytesIO()
    try:
        Image.new("RGB", (64, 64), (0, 90, 200)).save(buf, format="HEIF")
    except (KeyError, OSError, ValueError) as exc:
        pytest.skip(f"pillow-heif nie zapisuje HEIC w tym środowisku: {exc}")
    _, _, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    body = _post(client, admin_headers, cid, {"IMG_0001.HEIC": buf.getvalue()}).json()
    assert [(i["original_name"], i["gate_status"]) for i in body["items"]] == [("IMG_0001.pdf", "uncertain")]


class _FakeAtt:
    def __init__(self, name, data, hidden=False):
        self.longFilename, self.shortFilename, self.displayName = name, None, name
        self.data, self.hidden, self.contentId = data, hidden, None


class _FakeMsg:
    def __init__(self, attachments):
        self.attachments = attachments

    def close(self):
        pass


def test_msg_attachments_via_extract_msg(client, admin_headers, db_session, monkeypatch, tmp_path):
    import extract_msg

    _, _, cid = _start(client, admin_headers, db_session, monkeypatch, tmp_path)
    nested = _FakeMsg([_FakeAtt("z_fwd.xlsx", b"fwd")])
    fake = _FakeMsg([_FakeAtt("bl.pdf", pdf_bytes("msg")), _FakeAtt("logo.png", b"tiny", hidden=True),
                     _FakeAtt("fwd.msg", nested)])
    monkeypatch.setattr(extract_msg, "openMsg", lambda data: fake)
    body = _post(client, admin_headers, cid, {"outlook.msg": b"OLE-bytes"}).json()
    names = {i["original_name"]: i["doc_type"] for i in body["items"]}
    assert names == {"outlook.msg": "MAIL", "bl.pdf": "OTHER", "z_fwd.xlsx": "OTHER"}
    assert body["skipped"] == ["logo.png (obraz w treści maila)"]

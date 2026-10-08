"""Skrzynka draftów SAD dla automatu (n8n ← Outlook): kontener rozpoznany z pliku, PDF zakłada
wersję, XML dołącza do niej; token automatu działa jak konto serwisowe (te same reguły zakresu)."""
import io

from sqlalchemy import select

from app.config import settings
from app.invoices import extractor
from app.invoices.extractor import PageData
from app.models import InvoiceBatch, SadDraft
from app.security import AUTOMATION_HEADER
from tests.test_automation import TOKEN, service_account  # noqa: F401 — fixture konta „n8n”
from tests.test_sad_drafts import _batch, _pdf
from tests.test_sad_parse import SAD
from tests.test_sad_xml import XML

URL = "/api/sad-drafts/inbox"


def _send(client, headers, content, name):
    return client.post(URL, headers=headers,
                       files={"file": (name, io.BytesIO(content), "application/octet-stream")})


def _pdf_reads(monkeypatch, container: str) -> None:
    text = SAD.replace("MSDU0806613", container)
    monkeypatch.setattr(extractor, "read_pages", lambda path: [PageData(text=text)])


def test_n8n_token_pdf_then_xml_land_in_one_version(client, service_account, db_session,  # noqa: F811
                                                    monkeypatch, tmp_path, admin_headers):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    _pdf_reads(monkeypatch, "DEMU5000050")
    _, bid = _batch(client, admin_headers, db_session, no="DEMU5000050")
    client.cookies.clear()                                   # jak z n8n: tylko token, bez sesji
    n8n = {AUTOMATION_HEADER: TOKEN}

    pdf = _send(client, n8n, _pdf("v1"), "SAD7100005.pdf")
    assert pdf.status_code == 201, pdf.text
    body = pdf.json()
    assert (body["kind"], body["container"], body["batch_id"], body["version"]) == (
        "pdf", "DEMU5000050", bid, 1)
    assert body["summary"] is not None                       # od razu porównane z fakturami
    assert _send(client, n8n, _pdf("v1"), "kopia.pdf").json()["created"] is False   # ponowienie

    xml = _send(client, n8n, XML, "SAD7100005.xml")
    assert xml.status_code == 201, xml.text
    assert (xml.json()["kind"], xml.json()["version"], xml.json()["sad_no"]) == ("xml", 1, "7100005")
    draft = db_session.scalar(select(SadDraft).where(SadDraft.batch_id == bid))
    db_session.refresh(draft)
    assert draft.source == "automation" and draft.xml_attachment_id is not None
    assert draft.parsed["layout"] == "winsad-xml"


def test_unknown_container_xml_first_and_garbage(client, admin_headers, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    _pdf_reads(monkeypatch, "TGBU8339125")
    r = _send(client, admin_headers, _pdf("x"), "SAD.pdf")         # brak paczki faktur
    assert r.status_code == 409 and "TGBU8339125" in r.json()["detail"]
    _, bid = _batch(client, admin_headers, db_session, no="DEMU5000050")
    first = _send(client, admin_headers, XML, "SAD7100005.xml")     # XML zanim przyszedł PDF
    assert first.status_code == 409 and "PDF" in first.json()["detail"]
    assert _send(client, admin_headers, b"hello", "SAD.txt").status_code == 422
    assert _send(client, admin_headers, b"<Faktura/>", "x.xml").status_code == 422
    assert db_session.scalars(select(SadDraft)).all() == []
    assert db_session.get(InvoiceBatch, bid) is not None

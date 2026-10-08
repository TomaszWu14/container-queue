"""Draft SAD jako XML z WinSAD (eksport SADUE) dosyłany po PDF: odczyt pól jak z PDF, dołączenie
do istniejącej wersji draftu (zastępuje odczyt PDF), odrzucenie obcych/niebezpiecznych plików."""
import io
import pathlib

from sqlalchemy import select

from app.config import settings
from app.invoices import extractor, sad_parse
from app.invoices.extractor import PageData
from app.models import AuditLog
from tests.test_sad_drafts import _batch, _pdf, _upload
from tests.test_sad_parse import SAD

# syntetyczny eksport SADUE (tests/fixtures/sad/generate_synthetic.py)
XML = (pathlib.Path(__file__).parent / "fixtures" / "sad" / "SAD7100005.xml").read_bytes()


def test_parse_xml_reads_same_fields_as_pdf_printout():
    out = sad_parse.parse_xml(XML)
    assert out["layout"] == sad_parse.XML_LAYOUT and out["sad_no"] == "7100005"
    assert (out["currency"], out["total"], out["country_dispatch"]) == ("USD", "19450.7", "CN")
    assert out["container"] == "DEMU5000050" and out["country_origin"] == "CN"
    # te same liczby co odczyt PDF tego zgłoszenia (sad_winsad) — XML nie zaokrągla
    assert [(i["cn"], i["value"], i["net_mass"]) for i in out["items"]] == [
        ("30059050", "9800.4", "1500.2"), ("30059099", "9650.3", "1440.1")]
    assert out["unread"] == [] and out["error"] is None
    assert "DEMOS2607E01" in out["text"]               # faktura N935 do szukania w porównaniu


def test_parse_xml_rejects_foreign_broken_and_dtd():
    assert sad_parse.parse_xml(b"<?xml version='1.0'?><Faktura/>") is None
    assert sad_parse.parse_xml(b"%PDF-1.7 not xml") is None
    bomb = b'<?xml version="1.0"?><!DOCTYPE SADUE [<!ENTITY a "aaaa">]><SADUE>&a;</SADUE>'
    assert sad_parse.parse_xml(bomb) is None             # DTD/encje odrzucane przed parserem


def test_parse_xml_rejects_dtd_in_utf16():
    """`<!DOCTYPE` w UTF-16 to inne bajty — sprawdzenie bajtowe go nie widziało, a ET parsował
    encje. Poprawny XML w UTF-16 bez DTD nadal jest czytany."""
    bomb = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE SADUE [<!ENTITY a "aaaa">]>'
            '<SADUE P22WalutaSADu="&a;"/>').encode("utf-16")
    assert sad_parse.parse_xml(bomb) is None
    plain = '<?xml version="1.0" encoding="UTF-16"?><SADUE P22WalutaSADu="EUR"/>'.encode("utf-16")
    assert sad_parse.parse_xml(plain) is not None


def _xml(client, headers, bid, did, content=XML, name="SAD7100005.xml"):
    return client.post(f"/api/invoice-batches/{bid}/sad-drafts/{did}/xml", headers=headers,
                       files={"file": (name, io.BytesIO(content), "application/xml")})


def _pdf_reads(monkeypatch, container: str) -> None:
    text = SAD.replace("MSDU0806613", container)
    monkeypatch.setattr(extractor, "read_pages", lambda path: [PageData(text=text)])


def test_xml_joins_version_and_replaces_pdf_reading(client, admin_headers, db_session,
                                                    monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    _pdf_reads(monkeypatch, "DEMU5000050")
    cid, bid = _batch(client, admin_headers, db_session)
    did = _upload(client, admin_headers, bid, _pdf("v1")).json()["draft"]["id"]
    client.post(f"/api/invoice-batches/{bid}/sad-drafts/{did}/compare", headers=admin_headers)
    before = client.get(f"/api/invoice-batches/{bid}/sad-drafts", headers=admin_headers).json()
    assert before["drafts"][0]["data_from"] == "pdf" and before["drafts"][0]["xml_filename"] is None

    r = _xml(client, admin_headers, bid, did)
    assert r.status_code == 201, r.text
    draft = r.json()["state"]["drafts"][0]
    assert draft["version"] == 1 and len(r.json()["state"]["drafts"]) == 1   # ta sama wersja
    assert draft["data_from"] == "xml" and draft["xml_filename"] == "SAD7100005.xml"
    assert draft["summary"]["groups"] == 2                  # porównanie przeliczone z XML
    body = client.post(f"/api/invoice-batches/{bid}/sad-drafts/{did}/compare",
                       headers=admin_headers).json()
    assert {g["cn"] for g in body["groups"]} == {"30059050", "30059099"} and body["pages"] == 1
    log = db_session.scalar(select(AuditLog).where(AuditLog.field == "sad_draft_xml"))
    assert log.entity_id == cid and "7100005" in log.note

    again = _xml(client, admin_headers, bid, did, name="kopia.xml")
    assert again.status_code == 200 and again.json()["created"] is False    # ponowienie = bez zmian
    other = XML.replace(b"9800.40", b"9800.41")
    assert _xml(client, admin_headers, bid, did, other).status_code == 409  # poprawka = nowa wersja


def test_xml_rejects_wrong_file_and_other_container(client, admin_headers, db_session,
                                                    monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    _pdf_reads(monkeypatch, "MSDU0806613")
    _, bid = _batch(client, admin_headers, db_session)
    did = _upload(client, admin_headers, bid, _pdf("v1")).json()["draft"]["id"]
    assert _xml(client, admin_headers, bid, did, name="sad.pdf").status_code == 422
    assert _xml(client, admin_headers, bid, did, b"<Faktura/>").status_code == 422
    wrong = _xml(client, admin_headers, bid, did)            # XML od kontenera DEMU5000050
    assert wrong.status_code == 422 and "DEMU5000050" in wrong.json()["detail"]
    assert _xml(client, admin_headers, bid, 999999).status_code == 404
    state = client.get(f"/api/invoice-batches/{bid}/sad-drafts", headers=admin_headers).json()
    assert state["drafts"][0]["xml_attachment_id"] is None

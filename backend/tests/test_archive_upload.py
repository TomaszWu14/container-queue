"""ZIP wgrany do kontenera = folder zamówienia: PDF-y do paczki faktur, reszta do załączników,
archiwum w archiwum i niedozwolone typy pominięte (z powodem), sam ZIP nie jest przechowywany."""
import io
import zipfile

from app.models import Attachment, InvoiceBatch
from tests.test_invoice_conformity import _container
from tests.test_invoices_checks import _pdf, _setup


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buf.getvalue()


def _post(client, headers, cid, data, name="4500626277.zip"):
    return client.post(f"/api/containers/{cid}/archive", headers=headers,
                       files={"file": (name, io.BytesIO(data), "application/zip")})


def test_zip_unpacked_like_order_folder(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    data = _zip({"4500626277/DOC CI+BL.pdf": _pdf(2), "4500626277/kalkulacja.xlsx": b"x",
                 "4500626277/stare.zip": b"PK", "4500626277/skrypt.exe": b"MZ",
                 "__MACOSX/4500626277/._DOC.pdf": b"", "4500626277/Thumbs.db": b""})
    resp = _post(client, admin_headers, cid, data)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["folder"], body["pdfs"], body["attachments"]) == ("4500626277", 1, 1)
    assert body["skipped"] == ["stare.zip (archiwum w archiwum)", "skrypt.exe (niedozwolony typ)"]
    assert db_session.get(InvoiceBatch, body["batch_id"]).container_id == cid
    names = [a.filename for a in db_session.query(Attachment).filter_by(container_id=cid)]
    assert names == ["kalkulacja.xlsx"]                     # bez samego ZIP-a


def test_zip_guards(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    assert _post(client, admin_headers, cid, b"not a zip").status_code == 422
    assert _post(client, admin_headers, cid, _zip({"a.exe": b"MZ"})).status_code == 422
    monkeypatch.setattr("app.routers.archive_upload.MAX_UNCOMPRESSED_MB", 0)
    assert _post(client, admin_headers, cid, _zip({"a.pdf": _pdf(1)})).status_code == 413
    # zwykły upload załącznika nie przyjmuje ZIP-a (czarna skrzynka bez kafelków)
    resp = client.post(f"/api/containers/{cid}/attachments", headers=admin_headers,
                       files={"file": ("x.zip", io.BytesIO(b"PK"), "application/zip")})
    assert resp.status_code == 422


def test_zip_skips_files_already_in_container(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    assert _post(client, admin_headers, cid, _zip({"kalkulacja.xlsx": b"x1"})).status_code == 201
    body = _post(client, admin_headers, cid, _zip({"kopia.xlsx": b"x1", "nowy.xlsx": b"x2"})).json()
    assert body["attachments"] == 1 and len(body["skipped"]) == 1
    assert body["skipped"][0].startswith("kopia.xlsx (już jest w kontenerze jako „kalkulacja.xlsx”, wgrany ")



def test_zip_broken_entry_duplicates_and_bad_pdf_do_not_fail_whole_archive(client, admin_headers, db_session,
                                                                         monkeypatch, tmp_path):
    """Spec 2026-10-06 §4 pkt 5, 15, 43, 44: uszkodzony wpis (zła suma CRC) → pominięty, nie 500;
    ten sam plik dwa razy w archiwum → raz; zły PDF faktury → pominięty, reszta wgrana."""
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("uszkodzony.xlsx", b"AAAA-oryginal")
        archive.writestr("a.xlsx", b"same")
        archive.writestr("kopia.xlsx", b"same")
        archive.writestr("zly.pdf", b"%PDF-1.4 to nie jest pdf")
        archive.writestr("~$lock.xlsx", b"x")
    data = buf.getvalue().replace(b"AAAA-oryginal", b"BBBB-oryginal")   # treść ≠ CRC z nagłówka
    resp = _post(client, admin_headers, cid, data)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["attachments"] == 1 and body["pdfs"] == 0
    skipped = " | ".join(body["skipped"])
    for expected in ("uszkodzony.xlsx (zaszyfrowany albo uszkodzony", "kopia.xlsx (powtórzony w archiwum)",
                     "zly.pdf (", "~$lock.xlsx (plik tymczasowy"):
        assert expected in skipped, skipped

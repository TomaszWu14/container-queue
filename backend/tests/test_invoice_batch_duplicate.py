"""Audyt 2026-10-06 #2: ten sam zestaw PDF drugi raz do kontenera = odmowa, nie druga paczka.
Spec dokumenty-dostaw §4 pkt 14–17, 40: dubel po skrócie sha256 w obu kanałach (załączniki +
paczka faktur), pomijany per plik, także po przeniesieniu dokumentu; unikalność w bazie."""
import io
import pathlib

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.document_gate import digest, find_batch_duplicate
from app.models import Attachment, InvoiceJob

from tests.test_invoices_api import _container, _pdf, fake_pdf  # noqa: F401 — fake_pdf to fixture


def test_same_pdf_twice_is_refused_not_a_second_batch(client, admin_headers, fake_pdf):
    """Audyt 2026-10-06 #2: ten sam zestaw drugi raz = 409 ze wskazaniem paczki (nie druga
    paczka, drugi OCR, Excel i mail); po usunięciu paczki można wgrać ponownie."""
    cid = _container(client, admin_headers)
    data = _pdf(2)
    first = client.post(f"/api/containers/{cid}/invoice-batches", headers=admin_headers,
                        files=[("pdf", ("cipl.pdf", io.BytesIO(data), "application/pdf"))])
    assert first.status_code in (201, 202), first.text
    again = client.post(f"/api/containers/{cid}/invoice-batches", headers=admin_headers,
                        files=[("pdf", ("cipl (1).pdf", io.BytesIO(data), "application/pdf"))])
    assert again.status_code == 409 and "już jest w paczce" in again.json()["detail"]
    assert len(client.get(f"/api/containers/{cid}/invoice-batches", headers=admin_headers).json()) == 1
    assert client.delete(f"/api/invoice-batches/{first.json()['id']}", headers=admin_headers).status_code == 204
    retry = client.post(f"/api/containers/{cid}/invoice-batches", headers=admin_headers,
                        files=[("pdf", ("cipl.pdf", io.BytesIO(data), "application/pdf"))])
    assert retry.status_code in (201, 202)


def _upload(client, headers, cid, *files):
    return client.post(f"/api/containers/{cid}/invoice-batches", headers=headers,
                       files=[("pdf", (name, io.BytesIO(data), "application/pdf")) for name, data in files])


def test_duplicates_are_skipped_per_file_not_the_whole_upload(client, admin_headers, fake_pdf):
    """§4 pkt 15–16: dubel (wcześniejszy i w tym samym wgraniu) pomija TEN plik, reszta wchodzi."""
    cid = _container(client, admin_headers)
    a, b = _pdf(2), _pdf(2)
    assert _upload(client, admin_headers, cid, ("a.pdf", a)).status_code in (201, 202)
    resp = _upload(client, admin_headers, cid, ("a2.pdf", a), ("b.pdf", b), ("b2.pdf", b))
    assert resp.status_code in (201, 202), resp.text
    skipped = resp.json()["skipped"]
    assert len(skipped) == 2 and skipped[0].startswith("a2.pdf (już jest w paczce")
    assert skipped[1] == "b2.pdf (powtórzony w tym wgraniu)"
    assert resp.json()["jobs"] and all(j["filename"].startswith("b") for j in resp.json()["jobs"])


def test_duplicate_across_channels(client, admin_headers, fake_pdf, db_session):
    """§4 pkt 14: ten sam PDF jako załącznik i jako faktura = jeden dokument (w obie strony)."""
    cid = _container(client, admin_headers)
    invoice, loose = _pdf(2), _pdf(1)
    assert _upload(client, admin_headers, cid, ("cipl.pdf", invoice)).status_code in (201, 202)
    as_file = client.post(f"/api/containers/{cid}/attachments", headers=admin_headers,
                          files={"file": ("cipl.pdf", io.BytesIO(invoice), "application/pdf")})
    assert as_file.status_code == 409 and "paczce faktur" in as_file.json()["detail"]

    assert client.post(f"/api/containers/{cid}/attachments", headers=admin_headers,
                       files={"file": ("ci.pdf", io.BytesIO(loose), "application/pdf")}).status_code == 201
    as_invoice = _upload(client, admin_headers, cid, ("ci.pdf", loose))
    assert as_invoice.status_code == 409 and "„ci.pdf”" in as_invoice.json()["detail"]
    assert db_session.query(Attachment).filter_by(container_id=cid).one().sha256 == digest(loose)


def test_moved_document_keeps_its_hash(client, admin_headers, fake_pdf, db_session):
    """§4 pkt 17: przeniesienie/kopia zeruje source_name — skrót zostaje i bramka widzi dubel."""
    cid = _container(client, admin_headers)
    data = _pdf(2)
    assert _upload(client, admin_headers, cid, ("cipl.pdf", data)).status_code in (201, 202)
    jobs = db_session.query(InvoiceJob).all()
    assert jobs and all(j.sha256 == digest(data) for j in jobs)
    for job in jobs:
        job.source_name = ""   # jak relocate.move_job / copy_job
    db_session.commit()
    assert find_batch_duplicate(db_session, cid, data, pathlib.Path(settings.uploads_dir)) is not None


def test_same_hash_twice_in_container_is_refused_by_db(db_session, client, admin_headers):
    """§4 pkt 40: wyścig dwóch równoległych wgrań — drugi wiersz odrzuca baza."""
    cid = _container(client, admin_headers)
    for n in (1, 2):
        db_session.add(Attachment(container_id=cid, filename=f"{n}.pdf", stored_name=f"s{n}",
                                  size=1, sha256="ab" * 32))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

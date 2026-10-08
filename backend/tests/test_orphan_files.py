"""Pliki i baza razem (spec dokumenty-dostaw §4 pkt 33–37): sprzątacz przenosi do kwarantanny
tylko stare pliki dokumentów bez wiersza w bazie; inne pliki i świeże wgrania zostają."""
import datetime
import os

from app.database import SessionLocal
from app.models import Attachment, Company, Container
from app.orphan_files import QUARANTINE, quarantine_orphans
from tests.test_invoices_api import fake_pdf  # noqa: F401 — fixture


def _touch(path, hours_ago: float) -> None:
    path.write_bytes(b"x")
    stamp = (datetime.datetime.now() - datetime.timedelta(hours=hours_ago)).timestamp()
    os.utime(path, (stamp, stamp))


def test_quarantine_only_old_unreferenced_document_files(client, tmp_path):
    with SessionLocal() as db:
        company = db.query(Company).first()
        c = Container(container_no="MSDU0806613", company_id=company.id)
        db.add(c)
        db.flush()
        used = f"{c.id}_{'a' * 16}_bl.pdf"
        db.add(Attachment(container_id=c.id, filename="bl.pdf", stored_name=used))
        db.commit()
        _touch(tmp_path / used, 48)                                    # w użyciu
        _touch(tmp_path / f"{c.id}_{'b' * 16}_sierota.pdf", 48)       # sierota — do kwarantanny
        _touch(tmp_path / f"inv_{c.id}_{'c' * 16}_cipl_doc1_invoice.pdf", 48)  # część faktury bez wiersza
        _touch(tmp_path / f"bl_{'d' * 16}_fracht.pdf", 1)             # świeża — może być w toku
        _touch(tmp_path / "u1_avatar.png", 48)                        # nie dokument — nie ruszamy

        assert quarantine_orphans(db, uploads=tmp_path) == 2
    left = sorted(p.name for p in tmp_path.iterdir() if p.is_file())
    assert left == sorted([used, f"bl_{'d' * 16}_fracht.pdf", "u1_avatar.png"])
    assert sorted(p.name for p in (tmp_path / QUARANTINE).iterdir()) == sorted(
        [f"{c.id}_{'b' * 16}_sierota.pdf", f"inv_{c.id}_{'c' * 16}_cipl_doc1_invoice.pdf"])


def test_reexport_writes_new_file_and_drops_old_after_commit(client, admin_headers, fake_pdf):  # noqa: F811
    """§4 pkt 35: ponowny eksport Excela — nowa nazwa pliku, stary znika dopiero po commicie."""
    from app.routers.forwarding import uploads_dir
    from tests.test_invoice_agency_mail import _ready_batch
    _, bid = _ready_batch(client, admin_headers)
    with SessionLocal() as db:
        from app.models import InvoiceBatch
        att_id = db.get(InvoiceBatch, bid).attachment_id
        first = db.get(Attachment, att_id).stored_name
    assert client.post(f"/api/invoice-batches/{bid}/export", headers=admin_headers).status_code == 200
    with SessionLocal() as db:
        second = db.get(Attachment, att_id).stored_name
    assert second != first and (uploads_dir() / second).is_file()
    assert not (uploads_dir() / first).exists()

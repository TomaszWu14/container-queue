"""DB-012: kasowanie kontenera usuwa pliki z dysku dopiero po udanym commicie.

Wcześniej `_purge_containers` robił `unlink` w trakcie budowania transakcji — rollback
(błąd FK, zerwane połączenie) przywracał wiersze, ale plików już nie było (410/404)."""
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import (
    Attachment,
    Company,
    Complaint,
    ComplaintPhoto,
    Container,
    InvoiceBatch,
    InvoiceJob,
    UnloadPhoto,
)
from app.routers.containers_purge import _purge_containers
from tests.conftest import login

# RODO: także załączniki (CMR/SAD) i zdjęcia reklamacji — wcześniej zostawały na dysku
FILES = ("inv-part.pdf", "inv-source.pdf", "unl-photo.jpg", "att-cmr.pdf", "rek-photo.jpg")


def _seed_with_files(tmp_path, monkeypatch) -> int:
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    for name in FILES:
        (tmp_path / name).write_bytes(b"x")
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        c = Container(company_id=company.id, container_no="MSKU7026499")
        db.add(c)
        db.flush()
        batch = InvoiceBatch(container_id=c.id)
        db.add(batch)
        db.flush()
        db.add(InvoiceJob(batch_id=batch.id, filename="f.pdf", stored_name="inv-part.pdf",
                          source_name="inv-source.pdf"))
        db.add(UnloadPhoto(container_id=c.id, filename="a.jpg", stored_name="unl-photo.jpg"))
        db.add(Attachment(container_id=c.id, filename="cmr.pdf", stored_name="att-cmr.pdf"))
        complaint = Complaint(number="REK-PURGE-1", container_id=c.id, company_id=company.id)
        db.add(complaint)
        db.flush()
        db.add(ComplaintPhoto(complaint_id=complaint.id, filename="r.jpg",
                              stored_name="rek-photo.jpg"))
        db.commit()
        return c.id
    finally:
        db.close()


def test_rollback_after_purge_keeps_files(client, tmp_path, monkeypatch):
    """Błąd przed commitem (rollback) — wiersze wracają, więc pliki muszą zostać."""
    cid = _seed_with_files(tmp_path, monkeypatch)
    db = SessionLocal()
    try:
        assert _purge_containers(db, [cid]) == 1
        db.rollback()
        assert db.get(Container, cid) is not None
    finally:
        db.close()
    for name in FILES:
        assert (tmp_path / name).exists(), name
    # po rollbacku kolejny, niezwiązany commit tej sesji też nie kasuje plików
    db = SessionLocal()
    try:
        _purge_containers(db, [cid])
        db.rollback()
        db.commit()
    finally:
        db.close()
    for name in FILES:
        assert (tmp_path / name).exists(), name


def test_commit_after_purge_removes_files(client, tmp_path, monkeypatch):
    cid = _seed_with_files(tmp_path, monkeypatch)
    db = SessionLocal()
    try:
        _purge_containers(db, [cid])
        # do commitu pliki leżą na dysku
        for name in FILES:
            assert (tmp_path / name).exists(), name
        db.commit()
    finally:
        db.close()
    for name in FILES:
        assert not (tmp_path / name).exists(), name


def test_delete_endpoint_removes_files(client, tmp_path, monkeypatch):
    hdr = login(client)
    cid = _seed_with_files(tmp_path, monkeypatch)
    assert client.delete(f"/api/containers/{cid}", headers=hdr).status_code == 204
    for name in FILES:
        assert not (tmp_path / name).exists(), name


def test_clear_queue_removes_files(client, tmp_path, monkeypatch):
    hdr = login(client)
    _seed_with_files(tmp_path, monkeypatch)
    resp = client.delete("/api/containers?company_code=ACME&confirm=true", headers=hdr)
    assert resp.status_code == 200, resp.text
    for name in FILES:
        assert not (tmp_path / name).exists(), name

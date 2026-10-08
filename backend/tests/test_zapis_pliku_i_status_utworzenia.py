"""Spójność danych przy tworzeniu: plik załącznika zapisywany dopiero przy commicie
(rollback nie zostawia sieroty na dysku) i utworzenie od razu jako ZREALIZOWANY ustawia
completed_at (inaczej retencja RODO, liczona od completed_at, nigdy go nie obejmie)."""
import io

import pytest

from app.config import settings
from app.models import Container
from tests.conftest import login, pdf_bytes


def _acme_id(client, headers) -> int:
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == "ACME")


def test_upload_attachment_failure_before_commit_leaves_no_file(client, tmp_path, monkeypatch):
    hdr = login(client)
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    cid = client.post("/api/containers", headers=hdr, json={
        "container_no": "TGBU6784203", "company_id": _acme_id(client, hdr)}).json()["id"]

    def boom(*_a, **_k):
        raise RuntimeError("awaria po zapisie wiersza")

    # błąd po dodaniu wiersza, a przed commitem (np. powiadomienia) = rollback
    monkeypatch.setattr("app.routers.forwarding_files.notify", boom)
    with pytest.raises(RuntimeError):
        client.post(f"/api/containers/{cid}/attachments", headers=hdr,
                    files={"file": ("cmr.pdf", io.BytesIO(pdf_bytes("cmr.pdf")), "application/pdf")})
    assert list(tmp_path.iterdir()) == []


def test_create_container_as_completed_sets_completed_at(client, db_session):
    hdr = login(client)
    resp = client.post("/api/containers", headers=hdr, json={
        "container_no": "TGBU6784203", "company_id": _acme_id(client, hdr),
        "status": "ZREALIZOWANY"})
    assert resp.status_code == 201, resp.text
    assert db_session.get(Container, resp.json()["id"]).completed_at is not None

"""Usuwanie załącznika (pomyłka przy wgraniu; „Podmień” = upload + usunięcie): plik znika
z dysku i listy, wpis w historii; Excel paczki faktur i pliki draftu SAD chronione (409)."""
import io
import pathlib

from app.config import settings
from app.models import AuditLog, InvoiceBatch
from tests.test_invoice_conformity import _container
from tests.test_invoices_checks import _setup
from tests.conftest import pdf_bytes


def _attach(client, headers, cid, name="zly.pdf"):
    resp = client.post(f"/api/containers/{cid}/attachments", headers=headers,
                       files={"file": (name, io.BytesIO(pdf_bytes(name)), "application/pdf")})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_delete_attachment_removes_file_and_logs(client, admin_headers, db_session, monkeypatch,
                                                 tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    aid = _attach(client, admin_headers, cid)
    files = list(pathlib.Path(settings.uploads_dir).glob(f"{cid}_*_zly.pdf"))
    assert len(files) == 1

    assert client.delete(f"/api/attachments/{aid}", headers=admin_headers).status_code == 204
    assert not files[0].exists()
    assert client.get(f"/api/containers/{cid}/attachments", headers=admin_headers).json() == []
    assert db_session.query(AuditLog).filter_by(field="attachment_delete", old_value="zly.pdf").count() == 1
    assert client.delete(f"/api/attachments/{aid}", headers=admin_headers).status_code == 404


def test_batch_excel_is_protected(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    aid = _attach(client, admin_headers, cid, "faktury.xlsx")
    db_session.add(InvoiceBatch(container_id=cid, attachment_id=aid))
    db_session.commit()
    resp = client.delete(f"/api/attachments/{aid}", headers=admin_headers)
    assert resp.status_code == 409 and "paczki faktur" in resp.json()["detail"]

"""OBS-003 cz. 2: PAZ, mapy indeksów dostawcy, próbki profilu dostawcy i szablony
dokumentów celnych — każdy zapis zostawia wpis audytu z autorem."""
import io

import openpyxl
import pytest
from sqlalchemy import select

from app.models import AuditLog, User

from .test_supplier_maps import _seed as _seed_map
from .test_supplier_samples import _upload, lab_env  # noqa: F401 — fixture


def _paz_upsert(client, hdr, db):
    assert client.post("/api/paz", headers=hdr,
                       json={"produkt": "P-1", "sztuk_na_palete": 10}).status_code == 201
    assert client.post("/api/paz", headers=hdr,
                       json={"produkt": "P-1", "sztuk_na_palete": 20}).status_code == 201
    return [("product_paz", "created", "P-1: 10.0"), ("product_paz", "sztuk_na_palete", "20.0")]


def _paz_delete(client, hdr, db):
    pid = client.post("/api/paz", headers=hdr,
                      json={"produkt": "P-2", "sztuk_na_palete": 5}).json()["id"]
    assert client.delete(f"/api/paz/{pid}", headers=hdr).status_code == 204
    return [("product_paz", "delete", None)]


def _paz_import(client, hdr, db):
    wb = openpyxl.Workbook()
    wb.active.append(["produkt", "sztuk_na_palete"])
    wb.active.append(["ABC-1", 250])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    r = client.post("/api/paz/import", headers=hdr, files={"file": ("paz.xlsx", buf, "application/octet-stream")})
    assert r.status_code == 200 and r.json()["imported"] == 1
    return [("product_paz", "created", "ABC-1: 250.0")]


def _maps(client, hdr, db):
    company, supplier = _seed_map(db)
    db.commit()
    base = {"company_code": company.code, "supplier_id": supplier.id, "supplier_code": "X-99"}
    mid = client.post("/api/supplier-material-maps", headers=hdr,
                      json={**base, "ref_code": "ABC1"}).json()["id"]
    assert client.post("/api/supplier-material-maps", headers=hdr,
                       json={**base, "ref_code": "ABC2"}).status_code == 201
    assert client.patch(f"/api/supplier-material-maps/{mid}", headers=hdr,
                        json={**base, "ref_code": "ABC3"}).status_code == 200
    assert client.delete(f"/api/supplier-material-maps/{mid}", headers=hdr).status_code == 204
    return [("supplier_material_maps", "created", "X-99 → ABC1"),
            ("supplier_material_maps", "ref_code", "ABC2"),
            ("supplier_material_maps", "ref_code", "ABC3"),
            ("supplier_material_maps", "delete", None)]


def _templates(client, hdr, db):
    tid = client.post("/api/customs/doc-templates", headers=hdr,
                      json={"subject": "S1", "body": "B1"}).json()["id"]
    assert client.patch(f"/api/customs/doc-templates/{tid}", headers=hdr,
                        json={"subject": "S2", "body": "B1"}).status_code == 200
    assert client.delete(f"/api/customs/doc-templates/{tid}", headers=hdr).status_code == 204
    return [("doc_send_templates", "created", "domyślny"),
            ("doc_send_templates", "subject", "S2"),
            ("doc_send_templates", "delete", None)]


def _assert_entries(db, expected):
    db.expire_all()
    admin = db.scalar(select(User).where(User.login == "admin"))
    for entity_type, field, new_value in expected:
        rows = db.scalars(select(AuditLog).where(
            AuditLog.entity_type == entity_type, AuditLog.field == field,
            AuditLog.new_value.is_(None) if new_value is None
            else AuditLog.new_value == new_value)).all()
        assert rows, f"brak wpisu audytu {entity_type}.{field}={new_value!r}"
        assert rows[-1].user_id == admin.id


@pytest.mark.parametrize("action", [_paz_upsert, _paz_delete, _paz_import, _maps, _templates])
def test_write_leaves_audit_entry(client, db_session, admin_headers, action):
    _assert_entries(db_session, action(client, admin_headers, db_session))


def test_paz_same_value_no_audit_noise(client, db_session, admin_headers):
    for _ in range(2):
        client.post("/api/paz", headers=admin_headers, json={"produkt": "P-3", "sztuk_na_palete": 7})
    assert len(db_session.scalars(select(AuditLog).where(
        AuditLog.entity_type == "product_paz")).all()) == 1


def test_samples_upload_test_delete_audited(client, db_session, admin_headers, lab_env):  # noqa: F811
    sid, _ = lab_env
    sample_id = _upload(client, admin_headers, sid).json()["id"]
    body = {"ci_map": {"ref": ["Art. Code"], "qty": ["Pieces"], "net": ["Line total"]},
            "pl_map": {"ref": ["Art. Code"], "qty": ["Pieces"]}, "tol_amount_pct": 0.5}
    assert client.post(f"/api/suppliers/{sid}/doc-profile/test", headers=admin_headers,
                       json=body).status_code == 200
    assert client.delete(f"/api/suppliers/{sid}/doc-profile/samples/{sample_id}",
                         headers=admin_headers).status_code == 204
    _assert_entries(db_session, [("supplier_doc_samples", "created", "ci.pdf"),
                                 ("supplier_doc_samples", "last_test", "ok"),
                                 ("supplier_doc_samples", "delete", None)])

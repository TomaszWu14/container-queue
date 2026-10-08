"""Audyt ACL-003: dane WSPÓLNE grupy (PAZ, cele zapasu, stany DLT, MARM, porty kontenerowe)
zmienia admin, logistyka grupowa (view_all) albo logistyka spółki-właściciela materiałów
(SUPPLIER_COMPANY_CODES, np. Acme). Logistyk jednej spółki-klienta — tylko odczyt (403)."""
import pytest

from tests.test_import_autodetect import CPORTS, MARM
from tests.test_isolation import _company_id

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _logistics(client, admin_headers, login, company_code=None, view_all=False):
    body = {"login": login, "password": "haslo1234", "role": "logistics",
            "view_all_companies": view_all}
    if company_code:
        body["company_id"] = _company_id(client, admin_headers, company_code)
    assert client.post("/api/users", headers=admin_headers, json=body).status_code == 201
    token = client.post("/api/auth/login", data={"username": login, "password": "haslo1234"})
    return {"Authorization": f"Bearer {token.json()['access_token']}"}


@pytest.fixture()
def paz_id(client, admin_headers):
    r = client.post("/api/paz", headers=admin_headers,
                    json={"produkt": "DEMO-SKU-X", "sztuk_na_palete": 40})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_single_company_logistics_cannot_change_global_data(client, admin_headers, paz_id):
    h = _logistics(client, admin_headers, "log.borealis", "BOREALIS")
    assert client.get("/api/paz", headers=h).status_code == 200             # odczyt zostaje
    assert client.delete(f"/api/paz/{paz_id}", headers=h).status_code == 403
    assert client.post("/api/paz", headers=h,
                       json={"produkt": "X", "sztuk_na_palete": 1}).status_code == 403
    assert client.post("/api/stock-targets", headers=h,
                       json={"material_no": "M1", "days": 5}).status_code == 403
    files = {"file": ("m.xlsx", MARM, XLSX)}
    assert client.post("/api/import/material-units", headers=h, files=files).status_code == 403
    assert client.post("/api/import/dlt-stock", headers=h, files=files).status_code == 403
    assert client.post("/api/import/container-ports", headers=h,
                       files={"file": ("p.tsv", CPORTS, "text/plain")}).status_code == 403
    # wspólny dropzone rozpoznaje MARM/porty — ta sama reguła
    assert client.post("/api/import/master-data", headers=h, files=files).status_code == 403
    assert client.post("/api/import/master-data", headers=h,
                       files={"file": ("p.tsv", CPORTS, "text/plain")}).status_code == 403


def test_group_and_material_owner_logistics_can_change(client, admin_headers, paz_id):
    group = _logistics(client, admin_headers, "log.grupa", view_all=True)
    owner = _logistics(client, admin_headers, "log.acme", "ACME")
    assert client.post("/api/paz", headers=group,
                       json={"produkt": "A", "sztuk_na_palete": 2}).status_code == 201
    assert client.post("/api/stock-targets", headers=owner,
                       json={"material_no": "M1", "days": 5}).status_code == 200
    assert client.post("/api/import/material-units", headers=owner,
                       files={"file": ("m.xlsx", MARM, XLSX)}).status_code == 200
    assert client.delete(f"/api/paz/{paz_id}", headers=owner).status_code == 204

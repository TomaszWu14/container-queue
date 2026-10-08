"""Auto-rozpoznanie pliku master data (#18) + endpoint LFA1 + API dla automatyzacji (#21)."""
import io

import pytest
from openpyxl import Workbook

from app.config import settings
from app.routers.imports import detect_master_type
from app.security import AUTOMATION_HEADER
from tests.conftest import login

TOKEN = "test-automation-token-at-least-32-chars"


def xlsx(header, rows=()):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


MARM = xlsx(['Materiał', 'Jedn. miary', 'Licznik', 'Mianownik'],
            [['100200', 'PAL', 40, 1]])
EKKO = xlsx(['Dok.zaopatrz.', 'Dostawca', 'Waluta', 'Wart.całk.'],
            [['4500625519', '30001', 'USD', 1000]])
LFA1 = xlsx(['Dostawca', 'Kraj', 'Nazwa 1', 'Nazwa 2', 'Miasto', 'Kod pocztowy', 'Ulica'],
            [['30001', 'CN', 'Shanghai', 'Tools Co.', 'Shanghai', '200000', 'Nanjing Rd 1']])
CPORTS = b"CODE\tPORT NAME\tCOUNTRY\nCNSHA\tShanghai\tCN\n"


@pytest.mark.parametrize("content,filename,expected", [
    (MARM, "marm.xlsx", "marm"),
    (EKKO, "ekko.xlsx", "ekko"),
    (LFA1, "lfa1.xlsx", "lfa1"),
    (CPORTS, "porty.tsv", "cports"),
], ids=["marm", "ekko", "lfa1", "cports"])   # id z bajtów xlsx (znacznik czasu) różnił się między workerami xdist
def test_detect_master_type(content, filename, expected):
    detected, _ = detect_master_type(content, filename)
    assert detected == expected


def test_detect_unknown_gives_candidates():
    detected, candidates = detect_master_type(
        xlsx(['Kolumna A', 'Kolumna B']), "cos.xlsx")
    assert detected is None
    assert candidates == []


def test_master_data_upload_routes_marm(client, admin_headers):
    response = client.post("/api/import/master-data?dry_run=false", headers=admin_headers,
                           files={"file": ("marm.xlsx", MARM, "application/vnd.ms-excel")})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["detected"] == "marm" and payload["counts"]["new"] == 1


def test_master_data_upload_ekko_requires_company(client, admin_headers):
    response = client.post("/api/import/master-data", headers=admin_headers,
                           files={"file": ("ekko.xlsx", EKKO, "application/vnd.ms-excel")})
    assert response.status_code == 422
    assert "EKKO" in response.json()["detail"]


def test_master_data_upload_unknown_422(client, admin_headers):
    response = client.post("/api/import/master-data", headers=admin_headers,
                           files={"file": ("x.xlsx", xlsx(['A', 'B']), "application/x")})
    assert response.status_code == 422
    assert "Nie rozpoznano" in response.json()["detail"]


def test_lfa1_endpoint_imports_to_global_catalog(client, admin_headers):
    response = client.post("/api/import/suppliers-lfa1?dry_run=false", headers=admin_headers,
                           files={"file": ("lfa1.xlsx", LFA1, "application/vnd.ms-excel")})
    assert response.status_code == 200, response.text
    assert response.json()["counts"]["new"] == 1
    suppliers = client.get("/api/suppliers?include_inactive=true",
                           headers=admin_headers).json()
    match = [s for s in suppliers if s["sap_code"] == "30001"]
    assert len(match) == 1 and match[0]["client_company_id"] is None
    assert match[0]["country"] == "CN" and match[0]["name"] == "Shanghai Tools Co."


# --- #21: importy działają z tokenem automatyzacji (rola konta serwisowego = logistics) ---

@pytest.fixture()
def automation_client(client, admin_headers, monkeypatch):
    response = client.post("/api/users", headers=admin_headers, json={
        "login": "n8n", "password": "haslo-serwisowe-123", "role": "logistics",
        "view_all_companies": True})
    assert response.status_code == 201, response.text
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    client.cookies.clear()   # bez sesji admina — liczy się wyłącznie token
    return client


def test_automation_token_can_import_marm(automation_client):
    response = automation_client.post(
        "/api/import/material-units?dry_run=false",
        headers={AUTOMATION_HEADER: TOKEN},
        files={"file": ("marm.xlsx", MARM, "application/vnd.ms-excel")})
    assert response.status_code == 200, response.text
    assert response.json()["counts"]["new"] == 1


def test_automation_token_can_import_lfa1_ekko_cports(automation_client):
    headers = {AUTOMATION_HEADER: TOKEN}
    assert automation_client.post("/api/import/suppliers-lfa1", headers=headers,
                                  files={"file": ("lfa1.xlsx", LFA1, "application/x")}
                                  ).status_code == 200
    assert automation_client.post("/api/import/sap-orders?company_code=ACME",
                                  headers=headers,
                                  files={"file": ("ekko.xlsx", EKKO, "application/x")}
                                  ).status_code == 200
    assert automation_client.post("/api/import/container-ports", headers=headers,
                                  files={"file": ("porty.tsv", CPORTS, "text/plain")}
                                  ).status_code == 200


# --- Dostęp do katalogiem dostawców: Test 403 dla użytkownika bez dostępu ---

def test_lfa1_import_403_without_catalog_access(client, admin_headers):
    """POST /api/import/suppliers-lfa1 zwraca 403 dla użytkownika bez dostępu do katalogiem."""
    from sqlalchemy import select
    from app.models import Company
    from app.database import SessionLocal

    # Prepare: get non-material company (BOREALIS jest w default bez dostępu do katalogiem)
    with SessionLocal() as db:
        borealis = db.scalar(select(Company).where(Company.code == "BOREALIS"))

    # Create a logistics user from non-material company (no catalog access)
    resp = client.post("/api/users", headers=admin_headers, json={
        "login": "no_catalog_user", "password": "haslo12345", "role": "logistics",
        "company_id": borealis.id})
    assert resp.status_code == 201, resp.text

    user_headers = login(client, "no_catalog_user", "haslo12345")

    # Count suppliers before
    suppliers_before = client.get("/api/suppliers?include_inactive=true",
                                  headers=admin_headers).json()
    count_before = len([s for s in suppliers_before if s["sap_code"] == "30001"])
    assert count_before == 0

    # Attempt import should return 403
    response = client.post("/api/import/suppliers-lfa1?dry_run=false", headers=user_headers,
                           files={"file": ("lfa1.xlsx", LFA1, "application/vnd.ms-excel")})
    assert response.status_code == 403, response.text
    assert "kartoteki" in response.json()["detail"]

    # Verify no supplier was created
    suppliers_after = client.get("/api/suppliers?include_inactive=true",
                                 headers=admin_headers).json()
    count_after = len([s for s in suppliers_after if s["sap_code"] == "30001"])
    assert count_after == count_before == 0

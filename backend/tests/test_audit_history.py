"""GET /api/audit/{entity_type}/{entity_id} — historia wiersza master data.

Guard roli (Editors), izolacja spółek dla encji per spółka, wpisy audytu z PATCH-a.
"""
import pytest

from tests.conftest import login


@pytest.fixture()
def two_companies(client, admin_headers):
    companies = client.get("/api/companies", headers=admin_headers).json()
    if len(companies) < 2:
        r = client.post("/api/companies", headers=admin_headers,
                        json={"name": "Druga Spółka", "code": "DRUGA"})
        assert r.status_code == 201, r.text
        companies.append(r.json())
    return companies[0], companies[1]


def test_history_returns_patch_changes(client, admin_headers):
    port = client.post("/api/ports", headers=admin_headers,
                       json={"name": "Port Historia", "transit_time_days": 30}).json()
    r = client.patch(f"/api/ports/{port['id']}", headers=admin_headers,
                     json={"name": "Port Historia", "country": "CN", "category": "OUT",
                           "transit_time_days": 33, "is_active": True})
    assert r.status_code == 200, r.text

    hist = client.get(f"/api/audit/ports/{port['id']}", headers=admin_headers)
    assert hist.status_code == 200
    entries = hist.json()
    change = next(e for e in entries if e["field"] == "transit_time_days")
    assert change["old_value"] == "30" and change["new_value"] == "33"
    assert change["user_login"] == "admin"


def test_history_unknown_entity_type_404(client, admin_headers):
    assert client.get("/api/audit/nie_ma_takiej/1", headers=admin_headers).status_code == 404


def test_history_guard_roles(client, admin_headers, two_companies):
    """Editors (admin+logistyka) czytają historię; spedytor — nie."""
    c1, _ = two_companies
    fwd = client.post("/api/forwarders", headers=admin_headers,
                      json={"name": "Spedytor Audyt"}).json()
    client.post("/api/users", headers=admin_headers, json={
        "login": "fwd.audyt", "password": "haslo123", "role": "forwarder",
        "forwarder_id": fwd["id"]})
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.audyt", "password": "haslo123", "role": "logistics",
        "company_id": c1["id"], "view_all_companies": False})
    fwd_headers = login(client, "fwd.audyt", "haslo123")
    log_headers = login(client, "log.audyt", "haslo123")

    port = client.post("/api/ports", headers=admin_headers,
                       json={"name": "Port Guard"}).json()
    assert client.get(f"/api/audit/ports/{port['id']}", headers=fwd_headers).status_code == 403
    assert client.get(f"/api/audit/ports/{port['id']}", headers=log_headers).status_code == 200


def test_history_company_isolation(client, admin_headers, two_companies):
    """Logistyk spółki A nie czyta historii dostawcy spółki B.

    404, nie 403 — spójnie z check_company_access (nie zdradzamy istnienia rekordu).
    """
    c1, c2 = two_companies
    supplier = client.post("/api/suppliers", headers=admin_headers,
                           json={"name": "Dostawca B-Audyt", "company_id": c2["id"]}).json()
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.a.audyt", "password": "haslo123", "role": "logistics",
        "company_id": c1["id"], "view_all_companies": False})
    log_a = login(client, "log.a.audyt", "haslo123")

    assert client.get(f"/api/audit/suppliers/{supplier['id']}",
                      headers=log_a).status_code == 404
    # rekord skasowany → fail-closed dla konta z zawężeniem spółek…
    del_r = client.delete(f"/api/suppliers/{supplier['id']}", headers=admin_headers)
    assert del_r.status_code == 204
    assert client.get(f"/api/audit/suppliers/{supplier['id']}",
                      headers=log_a).status_code == 404
    # …a admin nadal widzi wpis o usunięciu
    hist = client.get(f"/api/audit/suppliers/{supplier['id']}",
                      headers=admin_headers).json()
    assert any(e["field"] == "delete" for e in hist)


def test_history_catalog_isolation(client, admin_headers):
    """Kartoteka (Supplier.client_company_id IS NULL): dostęp jak w deps.supplier_catalog_access
    — Acme/PT (spółki materiałowe) czytają, spółka bez materiałów (BOREALIS) — nie."""
    companies = client.get("/api/companies", headers=admin_headers).json()
    acme = next(c for c in companies if c["code"] == "ACME")
    borealis = next(c for c in companies if c["code"] == "BOREALIS")
    # company_id=ACME → is_material_company → trafia do globalnej kartoteki (client_company_id NULL)
    supplier = client.post("/api/suppliers", headers=admin_headers,
                           json={"name": "Dostawca Kartoteka Audyt",
                                 "company_id": acme["id"]}).json()
    client.patch(f"/api/suppliers/{supplier['id']}", headers=admin_headers,
                json={"name": "Dostawca Kartoteka Audyt", "is_active": False})
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.acme.audyt", "password": "haslo123", "role": "logistics",
        "company_id": acme["id"], "view_all_companies": False})
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.borealis.audyt", "password": "haslo123", "role": "logistics",
        "company_id": borealis["id"], "view_all_companies": False})
    log_acme = login(client, "log.acme.audyt", "haslo123")
    log_borealis = login(client, "log.borealis.audyt", "haslo123")

    assert client.get(f"/api/audit/suppliers/{supplier['id']}",
                      headers=log_acme).status_code == 200
    assert client.get(f"/api/audit/suppliers/{supplier['id']}",
                      headers=log_borealis).status_code == 404

    listing_acme = client.get("/api/audit/suppliers", headers=log_acme).json()
    listing_borealis = client.get("/api/audit/suppliers", headers=log_borealis).json()
    assert any(e["entity_id"] == supplier["id"] for e in listing_acme)
    assert listing_borealis == []

    listing_admin = client.get("/api/audit/suppliers", headers=admin_headers).json()
    assert any(e["entity_id"] == supplier["id"] for e in listing_admin)

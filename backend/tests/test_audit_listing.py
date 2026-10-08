"""Listing historii słownika (#19): GET /api/audit/{entity_type} bez id."""
from tests.conftest import login


def _make_history(client, admin_headers):
    companies = client.get("/api/companies", headers=admin_headers).json()
    acme = next(c for c in companies if c["code"] == "ACME")
    s = client.post("/api/suppliers", headers=admin_headers,
                    json={"name": "Alfa", "company_id": acme["id"]}).json()
    client.patch(f"/api/suppliers/{s['id']}", headers=admin_headers,
                 json={"name": "Alfa Nowa", "is_active": True})
    client.patch(f"/api/suppliers/{s['id']}", headers=admin_headers,
                 json={"name": "Alfa Nowa", "is_active": False})
    return companies, s


def test_listing_pagination_and_field_filter(client, admin_headers):
    _make_history(client, admin_headers)
    entries = client.get("/api/audit/suppliers", headers=admin_headers).json()
    assert len(entries) >= 2
    only_name = client.get("/api/audit/suppliers?field=name", headers=admin_headers).json()
    assert only_name and all(e["field"] == "name" for e in only_name)
    page2 = client.get("/api/audit/suppliers?limit=1&offset=1", headers=admin_headers).json()
    assert len(page2) == 1 and page2[0]["id"] != entries[0]["id"]


def test_listing_unknown_entity_404(client, admin_headers):
    assert client.get("/api/audit/nope", headers=admin_headers).status_code == 404


def test_listing_company_isolation(client, admin_headers):
    """Logistyk spółki B nie widzi historii dostawców spółki A."""
    companies, _ = _make_history(client, admin_headers)
    other = next(c for c in companies if c["code"] == "BOREALIS")
    client.post("/api/users", headers=admin_headers, json={
        "login": "log-b", "password": "haslo-logistyka-123", "role": "logistics",
        "company_id": other["id"]})
    headers = login(client, "log-b", "haslo-logistyka-123")
    entries = client.get("/api/audit/suppliers", headers=headers).json()
    assert entries == []


def test_company_history_isolation(client, admin_headers):
    """Company nie ma company_id — spółką jest sam rekord. Logistyk spółki B nie widzi
    historii spółki A (ani per id, ani w listingu), a swoją widzi."""
    companies = client.get("/api/companies", headers=admin_headers).json()
    acme = next(c for c in companies if c["code"] == "ACME")
    other = next(c for c in companies if c["code"] == "BOREALIS")
    for c in (acme, other):
        body = {"name": c["name"] + " X", "code": c["code"]}
        assert client.patch(f"/api/companies/{c['id']}", headers=admin_headers,
                            json=body).status_code == 200
    client.post("/api/users", headers=admin_headers, json={
        "login": "log-b2", "password": "haslo-logistyka-123", "role": "logistics",
        "company_id": other["id"]})
    headers = login(client, "log-b2", "haslo-logistyka-123")
    assert client.get(f"/api/audit/companies/{acme['id']}",
                      headers=headers).status_code == 404
    assert client.get(f"/api/audit/companies/{other['id']}", headers=headers).json()
    entries = client.get("/api/audit/companies", headers=headers).json()
    assert entries and {e["entity_id"] for e in entries} == {other["id"]}

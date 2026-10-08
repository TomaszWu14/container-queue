"""Dane kontaktowe spedytorów są wewnętrzne: agencja celna, spedytor (konkurencja)
i sprzedaż dostają z /api/forwarders tylko id + nazwę (+ is_active), logistyka pełny rekord."""
import pytest

from tests.conftest import login

CONTACT = {"email": "biuro@fwd.example", "contact_person": "Jan Kowalski",
           "contact_phone": "+48 600 000 000", "address": "ul. Portowa 1", "note": "stawki X"}


def _setup(client, admin_headers):
    r = client.post("/api/forwarders", headers=admin_headers,
                    json={"name": "ZZ-KONTAKT", **CONTACT})
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    company = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    agency = client.post("/api/customs-agencies", headers=admin_headers,
                         json={"name": "ZZ-AGENCJA"}).json()["id"]
    users = {"forwarder": {"forwarder_id": fid}, "customs": {"customs_agency_id": agency},
             "sales": {"company_id": company}, "logistics": {"company_id": company}}
    for role, link in users.items():
        r = client.post("/api/users", headers=admin_headers, json={
            "login": f"k.{role}", "password": "haslo123", "role": role, **link})
        assert r.status_code == 201, r.text
    return fid


@pytest.mark.parametrize("role", ["forwarder", "customs", "sales"])
def test_external_and_sales_get_names_only(client, admin_headers, role):
    fid = _setup(client, admin_headers)
    rows = client.get("/api/forwarders", headers=login(client, f"k.{role}", "haslo123")).json()
    row = next(f for f in rows if f["id"] == fid)
    assert row["name"] == "ZZ-KONTAKT"
    assert all(not row.get(k) for k in CONTACT), row


def test_logistics_gets_full_record(client, admin_headers):
    fid = _setup(client, admin_headers)
    rows = client.get("/api/forwarders", headers=login(client, "k.logistics", "haslo123")).json()
    row = next(f for f in rows if f["id"] == fid)
    assert {k: row[k] for k in CONTACT} == CONTACT

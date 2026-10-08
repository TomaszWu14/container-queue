"""Partnerzy zewnętrzni (spedytor, agencja celna) nie mają osi spółki.

Bug: konto partnera z ustawionym company_id (+ view_all_companies) dostawało 200 na dane
wewnętrzne spółki/grupy (wywołania DLT, PAZ, cele zapasu, mapy dostawców, zamówienia,
obsada magazynu, kontakty dostawców). Fix: deps.own_company_id ignoruje spółkę partnera,
can_view_all = False, wewnętrzne trasy za StaffReaders/PurchasingReaders, a panel admina
czyści company_id/view_all przy zapisie konta partnera. Stare dane (company_id w bazie)
są bezpieczne bez migracji — sprawdza to odczyt.
"""
import pytest

from app.models import User
from tests.conftest import forwarder, login

INTERNAL = [
    "/api/pallet-calls", "/api/pallet-calls/analysis", "/api/pallet-calls/hu-inventory",
    "/api/stock-targets", "/api/paz",
    "/api/supplier-material-maps", "/api/supplier-material-maps?company_code=ACME",
    "/api/orders", "/api/warehouse/staffing", "/api/supplier-contacts",
]


def _agency(client, headers, name):
    r = client.post("/api/customs-agencies", headers=headers, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _setup(client, admin_headers, db_session):
    company_id = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    fwd = forwarder(client, admin_headers, "PARTNER-FWD")
    ag = _agency(client, admin_headers, "PARTNER-AGENCJA")
    cont = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "TCNU0000011", "company_id": company_id,
        "forwarder_id": fwd["id"]})
    assert cont.status_code in (200, 201), cont.text
    assert client.post(f"/api/customs/containers/{cont.json()['id']}/assign",
                       headers=admin_headers,
                       json={"customs_agency_id": ag["id"]}).status_code == 200
    for login_, role, link in (("p.sped", "forwarder", {"forwarder_id": fwd["id"]}),
                               ("p.celna", "customs", {"customs_agency_id": ag["id"]})):
        r = client.post("/api/users", headers=admin_headers, json={
            "login": login_, "password": "haslo123", "role": role, **link})
        assert r.status_code == 201, r.text
    # stare dane na produkcji: partner ze spółką i „wszystkie spółki" ustawionymi w bazie
    for u in db_session.query(User).filter(User.login.in_(("p.sped", "p.celna"))):
        u.company_id, u.view_all_companies = company_id, True
    db_session.commit()
    return cont.json()["id"]


@pytest.mark.parametrize("who", ["p.sped", "p.celna"])
def test_partner_with_company_and_view_all_denied_internal_data(client, admin_headers,
                                                                db_session, who):
    _setup(client, admin_headers, db_session)
    hdr = login(client, who, "haslo123")
    leaked = {url: r.status_code for url in INTERNAL
              if (r := client.get(url, headers=hdr)).status_code not in (403, 404)}
    assert not leaked, leaked


def test_partner_facing_endpoints_still_work(client, admin_headers, db_session):
    cid = _setup(client, admin_headers, db_session)
    sped = login(client, "p.sped", "haslo123")
    celna = login(client, "p.celna", "haslo123")
    assert [c["id"] for c in client.get("/api/containers", headers=sped).json()] == [cid]
    assert client.get(f"/api/containers/{cid}", headers=sped).status_code == 200
    assert client.get(f"/api/containers/{cid}/cmr", headers=sped).status_code == 200
    assert client.get("/api/stats/dashboard", headers=sped).status_code == 200
    assert client.get("/api/complaints", headers=sped).status_code == 200
    assert [c["id"] for c in client.get("/api/customs/board", headers=celna).json()] == [cid]
    assert client.get(f"/api/containers/{cid}", headers=celna).status_code == 200
    # licznik spółek kolejki: partner nie dostaje „swojej" spółki z company_id
    counts = client.get("/api/containers/counts", headers=sped)
    assert counts.status_code == 200


def test_admin_clears_company_scope_for_partner(client, admin_headers):
    company_id = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    fwd = forwarder(client, admin_headers, "PARTNER-FWD2")
    r = client.post("/api/users", headers=admin_headers, json={
        "login": "p.sped2", "password": "haslo123", "role": "forwarder",
        "forwarder_id": fwd["id"], "company_id": company_id, "view_all_companies": True})
    assert r.status_code == 201, r.text
    assert r.json()["company_id"] is None and r.json()["view_all_companies"] is False
    # zmiana roli wewnętrznej na partnera też czyści spółkę
    r = client.post("/api/users", headers=admin_headers, json={
        "login": "p.log", "password": "haslo123", "role": "logistics",
        "company_id": company_id, "view_all_companies": True})
    uid = r.json()["id"]
    r = client.patch(f"/api/users/{uid}", headers=admin_headers, json={
        "role": "forwarder", "forwarder_id": fwd["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["company_id"] is None and r.json()["view_all_companies"] is False

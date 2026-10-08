"""Zakładanie zlecenia (Borealis/Cobalt): jedno zamówienie → N rekordów kontenerów,
master data portów/typów kontenerów, kontakty dostawcy, przewalutowanie NBP."""
from app.nbp import convert
from tests.conftest import forwarder, login


def _company_id(client, headers, code):
    companies = client.get("/api/companies", headers=headers).json()
    return next(c["id"] for c in companies if c["code"] == code)


def test_ports_and_container_types_seeded(client, admin_headers):
    ports = client.get("/api/ports", headers=admin_headers).json()
    shanghai = next(p for p in ports if p["name"] == "Shanghai")
    assert shanghai["category"] == "GLOWNY_CN"
    assert shanghai["transit_time_days"] == 32 and shanghai["transit_time_long_days"] == 42

    types = client.get("/api/container-types", headers=admin_headers).json()
    hc = next(t for t in types if t["name"] == "40'HC")
    # kubatura liczona z wymiarów wewnętrznych 12.03 × 2.35 × 2.70
    assert abs(hc["volume_m3"] - 76.33) < 0.5


def test_found_order_splits_into_n_records(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    ports = client.get("/api/ports", headers=admin_headers).json()
    port = next(p for p in ports if p["name"] == "Ningbo")
    ctype = next(t for t in client.get("/api/container-types", headers=admin_headers).json()
                 if t["name"] == "40'HC")

    resp = client.post("/api/zlecenia", headers=admin_headers, json={
        "number": "ZL-1001", "company_id": borealis, "supplier_name": "ACME Ltd",
        "departure_port_id": port["id"], "container_type_id": ctype["id"],
        "main_mode": "SEA", "sea_service": "STANDARD", "container_count": 3,
        "goods_type": "meble", "is_adr": False, "goods_value": "50000.00",
        "goods_currency": "USD", "goods_weight": "12 t", "readiness_date": "2026-08-01"})
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["number"] == "ZL-1001"
    assert order["container_count"] == 3
    assert order["planned_container_count"] == 3   # zaplanowane = faktyczne przy zakładaniu
    assert len(order["containers"]) == 3
    assert order["departure_port_name"] == "Ningbo"
    assert order["container_type_name"] == "40'HC"
    assert order["main_mode"] == "SEA" and order["sea_service"] == "STANDARD"
    assert order["supplier_name"] == "ACME Ltd"
    # kontenery bez numeru, dziedziczą dostawcę i rozmiar ze zlecenia
    for container in order["containers"]:
        assert container["container_no"] == ""
        assert container["container_size"] == "40'HC"
        assert container["supplier_name"] == "ACME Ltd"
        assert container["transport_id"]  # nadany automatycznie

    # rekordy trafiają do kolejki spółki
    listed = client.get("/api/containers?company_code=BOREALIS", headers=admin_headers).json()
    assert sum(1 for c in listed if c["order_number"] == "ZL-1001") == 3

    # powiadomienie o nowym zleceniu
    notes = client.get("/api/notifications", headers=admin_headers).json()
    assert any("ZL-1001" in n["title"] for n in notes)


def test_new_order_notifies_acme_team(client, admin_headers):
    # centralny team Acme (logistyka ACME, bez view_all) musi dostać powiadomienie
    acme = _company_id(client, admin_headers, "ACME")
    borealis = _company_id(client, admin_headers, "BOREALIS")
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.acme", "password": "haslo123", "role": "logistics",
        "company_id": acme, "email": "log.acme@example.com"})
    acme_h = login(client, "log.acme", "haslo123")

    # zlecenie zakładane pod Borealis
    resp = client.post("/api/zlecenia", headers=admin_headers, json={
        "number": "ZL-Z-1", "company_id": borealis, "container_count": 1})
    assert resp.status_code == 201

    # team Acme widzi dzwoneczek o nowym zleceniu Borealis
    notes = client.get("/api/notifications", headers=acme_h).json()
    assert any("ZL-Z-1" in n["title"] and "Borealis" in n["title"] for n in notes)


def test_found_order_rail_and_duplicate_number(client, admin_headers):
    cobalt = _company_id(client, admin_headers, "COBALT")
    r1 = client.post("/api/zlecenia", headers=admin_headers, json={
        "number": "ZL-2002", "company_id": cobalt, "container_count": 2, "main_mode": "RAIL"})
    assert r1.status_code == 201
    assert all(c["transport_type"] == "kolej" for c in r1.json()["containers"])
    # ten sam numer w tej samej spółce → konflikt
    dup = client.post("/api/zlecenia", headers=admin_headers, json={
        "number": "ZL-2002", "company_id": cobalt, "container_count": 1})
    assert dup.status_code == 409


def test_supplier_contacts_dictionary(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    supplier = client.post("/api/suppliers", headers=admin_headers,
                           json={"name": "Contact Co", "company_id": borealis}).json()
    contact = client.post("/api/supplier-contacts", headers=admin_headers, json={
        "supplier_id": supplier["id"], "full_name": "Li Wei",
        "email": "li@contact.example", "phone": "+86 100"}).json()
    assert contact["full_name"] == "Li Wei"
    listed = client.get(f"/api/supplier-contacts?supplier_id={supplier['id']}",
                        headers=admin_headers).json()
    assert [c["id"] for c in listed] == [contact["id"]]

    # zlecenie z kontaktem spoza dostawcy → 422
    bad = client.post("/api/zlecenia", headers=admin_headers, json={
        "number": "ZL-3003", "company_id": borealis, "supplier_id": supplier["id"],
        "supplier_contact_id": contact["id"] + 999, "container_count": 1})
    assert bad.status_code in (404, 422)


def test_found_order_via_company_code(client, admin_headers):
    # admin bez company_id: spółkę ustala company_code (fallback, gdy klient nie zdążył
    # załadować listy spółek) — zlecenie ma trafić do Borealis, nie do spółki admina
    resp = client.post("/api/zlecenia", headers=admin_headers, json={
        "number": "ZL-CODE-1", "company_code": "BOREALIS", "container_count": 1})
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["company_name"] == "Borealis"
    # numer zamówienia jest widoczny w kolejce Borealis
    listed = client.get("/api/containers?company_code=BOREALIS", headers=admin_headers).json()
    assert any(c["order_number"] == "ZL-CODE-1" for c in listed)


def test_supplier_contacts_isolated_from_forwarder(client, admin_headers):
    # spedytor (konto zewnętrzne) NIE może czytać kontaktów dostawców i nie widzi e-maili konkurencji
    borealis = _company_id(client, admin_headers, "BOREALIS")
    supplier = client.post("/api/suppliers", headers=admin_headers,
                           json={"name": "Iso Co", "company_id": borealis}).json()
    client.post("/api/supplier-contacts", headers=admin_headers, json={
        "supplier_id": supplier["id"], "full_name": "Secret Person",
        "email": "secret@x.example", "phone": "+48 1"})
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.iso", "password": "haslo123", "role": "forwarder",
        "forwarder_id": spedalfa, "email": "sped.iso@example.com"})
    fwd = login(client, "sped.iso", "haslo123")

    assert client.get("/api/supplier-contacts", headers=fwd).status_code == 403
    # /forwarders bez e-maili dla spedytora
    fwd_list = client.get("/api/forwarders", headers=fwd).json()
    assert all(f["email"] == "" for f in fwd_list)


def test_nbp_conversion_math():
    # kursy wstrzyknięte (bez sieci): 1 USD = 4.00 PLN, 1 EUR = 4.40 PLN
    rates = {"USD": 4.0, "EUR": 4.4, "PLN": 1.0}
    out = convert(1000.0, "USD", rates=rates, as_of="2026-07-09")
    assert out["available"] is True
    assert out["converted"]["PLN"] == 4000.0
    assert out["converted"]["USD"] == 1000.0
    assert abs(out["converted"]["EUR"] - 909.09) < 0.01
    # brak kursów → fallback, bez wyjątku
    empty = convert(1000.0, "USD", rates={})
    assert empty["available"] is False and empty["converted"] == {}

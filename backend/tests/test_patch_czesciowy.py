"""PATCH z częściowym ciałem nie kasuje pól, których klient nie przysłał.

Regresja: edycja w słownikach (DictionariesTab) nie wysyła avizo_cc spółki ani slotów
magazynu — backend nadpisywał je wartościami domyślnymi schematu (pełny model_dump)."""


def _company(client, headers, code="BOREALIS"):
    return next(c for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def test_company_rename_keeps_avizo_cc(client, admin_headers):
    co = _company(client, admin_headers)
    r = client.patch(f"/api/companies/{co['id']}", headers=admin_headers, json={
        "name": co["name"], "code": co["code"], "avizo_cc": "a@x.pl,b@x.pl"})
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/companies/{co['id']}", headers=admin_headers, json={
        "name": co["name"] + " SA", "code": co["code"], "is_active": True})
    assert r.status_code == 200, r.text
    assert r.json()["avizo_cc"] == "a@x.pl,b@x.pl"


def test_warehouse_edit_keeps_slots(client, admin_headers):
    co = _company(client, admin_headers)
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "WH-PATCH", "company_id": co["id"],
        "slot_windows": "07:00, 09:00", "slot_capacity": 3}).json()
    r = client.patch(f"/api/warehouses/{wh['id']}", headers=admin_headers, json={
        "name": "WH-PATCH", "email": "", "country": "PL", "default_daily_limit": 5})
    assert r.status_code == 200, r.text
    assert (r.json()["slot_windows"], r.json()["slot_capacity"]) == ("07:00,09:00", 3)
    assert r.json()["default_daily_limit"] == 5


def test_port_edit_without_monthly_keeps_profile(client, admin_headers):
    port = next(p for p in client.get("/api/ports", headers=admin_headers).json()
                if p["name"] == "Shanghai")
    client.patch(f"/api/ports/{port['id']}", headers=admin_headers,
                 json={"name": port["name"], "monthly_transit": {"1": 50}})
    r = client.patch(f"/api/ports/{port['id']}", headers=admin_headers,
                     json={"name": port["name"], "is_active": True})
    assert r.status_code == 200, r.text
    assert r.json()["monthly_transit"] == {"1": 50}


def test_forwarder_toggle_keeps_contact(client, admin_headers):
    fw = client.post("/api/forwarders", headers=admin_headers, json={
        "name": "Spedytor PATCH", "email": "sped@x.pl", "note": "ważne"}).json()
    r = client.patch(f"/api/forwarders/{fw['id']}", headers=admin_headers,
                     json={"name": "Spedytor PATCH", "is_active": False})
    assert r.status_code == 200, r.text
    assert (r.json()["email"], r.json()["note"], r.json()["is_active"]) == ("sped@x.pl", "ważne", False)


def test_driver_partial_keeps_other_fields(client, admin_headers):
    co = _company(client, admin_headers)
    cid = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MSDU0806613", "company_id": co["id"]}).json()["id"]
    client.patch(f"/api/containers/{cid}/driver", headers=admin_headers,
                 json={"driver_name": "Jan", "truck_no": "WX123"})
    r = client.patch(f"/api/containers/{cid}/driver", headers=admin_headers,
                     json={"driver_phone": "600100200"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["driver_name"], body["truck_no"], body["driver_phone"]) == ("Jan", "WX123", "600100200")


def test_complaint_explicit_null_clears_amount(client, admin_headers):
    co = _company(client, admin_headers)
    cid = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MSKU0000006", "company_id": co["id"]}).json()["id"]
    complaint = client.post("/api/complaints", headers=admin_headers, json={
        "container_id": cid, "kind": "REKLAMACJA", "report_to_warehouse": False}).json()
    url = f"/api/complaints/{complaint['id']}"
    client.patch(url, headers=admin_headers, json={"claim_amount": 1000, "recovered_amount": 250})
    # pominięte pole — bez zmian
    r = client.patch(url, headers=admin_headers, json={"claim_currency": "EUR"})
    assert float(r.json()["claim_amount"]) == 1000
    # jawny null — czyści
    r = client.patch(url, headers=admin_headers, json={"claim_amount": None, "recovered_amount": None})
    assert r.status_code == 200, r.text
    assert r.json()["claim_amount"] is None and r.json()["recovered_amount"] is None

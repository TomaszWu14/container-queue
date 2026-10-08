"""Pola kontaktowe słowników master: spedytorzy, agencje celne, dostawcy."""


def test_forwarder_contact_fields_roundtrip(client, admin_headers):
    body = {"name": "SPEDALFA Test", "email": "biuro@spedalfa.pl", "contact_person": "Jan Kowalski",
            "contact_phone": "600100200", "address": "Hutnicza 1, Gdynia", "note": "kontakt 24/7"}
    created = client.post("/api/forwarders", headers=admin_headers, json=body)
    assert created.status_code == 201, created.text
    fid = created.json()["id"]

    got = next(f for f in client.get("/api/forwarders", headers=admin_headers).json()
               if f["id"] == fid)
    assert got["contact_person"] == "Jan Kowalski"
    assert got["contact_phone"] == "600100200"
    assert got["address"] == "Hutnicza 1, Gdynia"
    assert got["note"] == "kontakt 24/7"

    upd = client.patch(f"/api/forwarders/{fid}", headers=admin_headers,
                       json={**body, "contact_person": "Anna Nowak"})
    assert upd.status_code == 200 and upd.json()["contact_person"] == "Anna Nowak"


def test_customs_agency_contact_fields(client, admin_headers):
    body = {"name": "AC Test", "email": "ac@x.pl", "is_active": True,
            "contact_person": "Piotr", "contact_phone": "500", "address": "Adr", "note": "n"}
    created = client.post("/api/customs-agencies", headers=admin_headers, json=body)
    assert created.status_code == 201, created.text
    assert created.json()["contact_person"] == "Piotr"
    aid = created.json()["id"]
    upd = client.patch(f"/api/customs-agencies/{aid}", headers=admin_headers,
                       json={**body, "address": "Nowy adres"})
    assert upd.status_code == 200 and upd.json()["address"] == "Nowy adres"


def test_supplier_org_fields(client, admin_headers):
    companies = client.get("/api/companies", headers=admin_headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    body = {"name": "Dost Test", "company_id": borealis,
            "address": "Shanghai Rd 1", "note": "MOQ 100"}
    created = client.post("/api/suppliers", headers=admin_headers, json=body)
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    got = next(s for s in client.get("/api/suppliers", headers=admin_headers).json()
               if s["id"] == sid)
    assert got["address"] == "Shanghai Rd 1" and got["note"] == "MOQ 100"

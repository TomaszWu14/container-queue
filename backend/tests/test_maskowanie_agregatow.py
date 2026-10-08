"""Agregaty i widoki boczne nie omijają maskowania ról (2026-10-05): sygnały „Co dziś”,
pulpit, analityka, statystyki/pisma reklamacji i oś czasu podlegają tym samym regułom
co karta kontenera (containers_common.hidden_fields / mask_row). Kwoty reklamacji widzą
tylko role kosztowe (complaints_common.COST_ROLES)."""
import datetime

from app.models import Container, PurchaseOrder

from .conftest import forwarder, login
from .test_api import VALID_NO, _company_id, _make_user

SUPPLIER = "Tajny Dostawca SA"
PO = "PO-SEKRET-77"
DRIVER = "Jan Kierowcowski"
TRUCK = "WX12345"
AMOUNT = "98765.43"

# rola → znaczniki, których nie wolno jej zobaczyć w żadnym z endpointów
HIDDEN = {
    "celna.m": (SUPPLIER, PO, DRIVER, TRUCK, AMOUNT),
    "mag.m": (SUPPLIER, PO, AMOUNT),
    "sprz.m": (DRIVER, TRUCK, AMOUNT),
    "sped.m": (AMOUNT,),
}


def _setup(client, admin_headers, db_session):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "DLT", "company_id": borealis, "country": "PL"}).json()
    agency = client.post("/api/customs-agencies", headers=admin_headers,
                         json={"name": "CELNA-M"}).json()
    fwd = forwarder(client, admin_headers, "SPED-M")
    supplier = client.post("/api/suppliers", headers=admin_headers, json={
        "name": SUPPLIER, "company_id": borealis}).json()
    r = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis, "warehouse_id": wh["id"],
        "supplier_id": supplier["id"], "forwarder_id": fwd["id"], "status": "W_TRANSPORCIE",
        "eta": (datetime.date.today() - datetime.timedelta(days=10)).isoformat()})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert client.post(f"/api/customs/containers/{cid}/assign", headers=admin_headers,
                       json={"customs_agency_id": agency["id"]}).status_code == 200
    c = db_session.get(Container, cid)
    c.driver_name, c.truck_no = DRIVER, TRUCK
    db_session.add(PurchaseOrder(company_id=borealis, order_no=PO, container_id=cid,
                                 etd=datetime.date(2025, 12, 1)))
    db_session.commit()
    comp = client.post("/api/complaints", headers=admin_headers, json={
        "container_id": cid, "kind": "REKLAMACJA", "report_to_warehouse": False}).json()
    assert client.patch(f"/api/complaints/{comp['id']}", headers=admin_headers,
                        json={"claim_amount": float(AMOUNT),
                              "recovered_amount": 10}).status_code == 200
    _make_user(client, admin_headers, "mag.m", "warehouse", borealis, warehouse_id=wh["id"])
    _make_user(client, admin_headers, "sprz.m", "sales", borealis)
    assert client.post("/api/users", headers=admin_headers, json={
        "login": "celna.m", "password": "haslo123", "role": "customs",
        "customs_agency_id": agency["id"]}).status_code == 201
    assert client.post("/api/users", headers=admin_headers, json={
        "login": "sped.m", "password": "haslo123", "role": "forwarder",
        "forwarder_id": fwd["id"], "email": "sped.m@example.com"}).status_code == 201
    return [
        "/api/inbox", "/api/stats/dashboard", "/api/analytics/operational",
        "/api/complaints", f"/api/complaints/{comp['id']}", "/api/complaints/stats",
        f"/api/complaints/{comp['id']}/letter", f"/api/containers/{cid}/timeline",
        f"/api/containers/{cid}",
    ], comp["id"]


def test_aggregates_respect_role_masking(client, admin_headers, db_session):
    urls, _ = _setup(client, admin_headers, db_session)
    # kontrola: admin widzi każdy znacznik gdzieś — inaczej test niczego nie sprawdza
    admin_text = "".join(client.get(u, headers=admin_headers).text for u in urls)
    for marker in (SUPPLIER, PO, DRIVER, TRUCK, AMOUNT):
        assert marker in admin_text, marker
    for who, markers in HIDDEN.items():
        h = login(client, who, "haslo123")
        for url in urls:
            r = client.get(url, headers=h)
            if r.status_code != 200:   # brak dostępu = brak wycieku
                continue
            for marker in markers:
                assert marker not in r.text, (who, url, marker)


def test_warehouse_cannot_patch_complaint_amounts(client, admin_headers, db_session):
    _, comp_id = _setup(client, admin_headers, db_session)
    h = login(client, "mag.m", "haslo123")
    r = client.patch(f"/api/complaints/{comp_id}", headers=h, json={"claim_amount": None})
    assert r.status_code == 403, r.text
    # opis magazyn nadal może poprawić
    assert client.patch(f"/api/complaints/{comp_id}", headers=h,
                        json={"description": "uszkodzona paleta"}).status_code == 200
    assert client.get(f"/api/complaints/{comp_id}",
                      headers=admin_headers).json()["claim_amount"] == float(AMOUNT)

"""Usuwanie rekordów master data: 204 + audyt dla wolnych, 409 przy referencjach
(żadnych kaskad), 403 dla ról nie-admin. Porty/dostawcy/armatorzy mają własne testy
w test_dictionaries.py — tu nowe encje: PurchaseOrder, MaterialUnit, magazyny,
agencje celne, typy dokumentów, statusy spraw."""
import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog, Company, MaterialUnit, PurchaseOrder
from tests.conftest import login


def _company_id(client, headers, code):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _logistics(client, admin_headers, company_id, name="log_del"):
    r = client.post("/api/users", headers=admin_headers, json={
        "login": name, "password": "haslo123", "role": "logistics",
        "company_id": company_id, "view_all_companies": False, "warehouse_id": None})
    assert r.status_code == 201, r.text
    return login(client, name, "haslo123")


def _audit_entries(entity_type, entity_id):
    db = SessionLocal()
    try:
        return db.scalars(select(AuditLog).where(
            AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id,
            AuditLog.field == "delete")).all()
    finally:
        db.close()


def _seed_po(client, admin_headers, order_no, container_id=None):
    db = SessionLocal()
    try:
        acme = db.scalar(select(Company).where(Company.code == "ACME"))
        po = PurchaseOrder(company_id=acme.id, order_no=order_no, supplier="Fushide",
                           etd=datetime.date(2026, 9, 1), container_id=container_id)
        db.add(po)
        db.commit()
        return po.id, acme.id
    finally:
        db.close()


# --- zamówienia zakupowe (PurchaseOrder) ---

def test_delete_purchase_order_free_and_linked(client, admin_headers):
    free_id, acme_id = _seed_po(client, admin_headers, "PO-FREE")
    ports = client.get("/api/ports", headers=admin_headers).json()
    resp = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MEDU1234562", "company_id": acme_id, "port_id": ports[0]["id"]})
    assert resp.status_code in (200, 201), resp.text
    container = resp.json()
    linked_id, _ = _seed_po(client, admin_headers, "PO-LINKED",
                            container_id=container["id"])

    # powiązane z kontenerem → 409, bez kaskady
    blocked = client.delete(f"/api/purchase-orders/{linked_id}", headers=admin_headers)
    assert blocked.status_code == 409
    assert "Nie można usunąć" in blocked.json()["detail"]

    # wolne → 204 + wpis audytu z opisem rekordu
    assert client.delete(f"/api/purchase-orders/{free_id}",
                         headers=admin_headers).status_code == 204
    logs = _audit_entries("purchase_orders", free_id)
    assert logs and "PO-FREE" in logs[0].old_value

    assert client.delete(f"/api/purchase-orders/{free_id}",
                         headers=admin_headers).status_code == 404


def test_delete_purchase_order_requires_admin(client, admin_headers):
    po_id, acme_id = _seed_po(client, admin_headers, "PO-ROLE")
    log_hdr = _logistics(client, admin_headers, acme_id)
    assert client.delete(f"/api/purchase-orders/{po_id}",
                         headers=log_hdr).status_code == 403


# --- jednostki materiałów (MARM) ---

def test_delete_material_unit(client, admin_headers):
    db = SessionLocal()
    try:
        unit = MaterialUnit(material_no="100200", unit="KAR", numerator=24, denominator=1)
        db.add(unit)
        db.commit()
        unit_id = unit.id
    finally:
        db.close()

    acme_id = _company_id(client, admin_headers, "ACME")
    log_hdr = _logistics(client, admin_headers, acme_id, name="log_marm")
    assert client.delete(f"/api/material-units/{unit_id}",
                         headers=log_hdr).status_code == 403

    assert client.delete(f"/api/material-units/{unit_id}",
                         headers=admin_headers).status_code == 204
    logs = _audit_entries("material_units", unit_id)
    assert logs and "100200 KAR" in logs[0].old_value


# --- magazyny ---

def test_delete_warehouse_free_and_referenced(client, admin_headers):
    acme_id = _company_id(client, admin_headers, "ACME")
    free = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "Magazyn do kasacji", "company_id": acme_id}).json()
    used = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "Magazyn w użyciu", "company_id": acme_id}).json()
    # referencja: konto magazynowe przypięte do magazynu
    r = client.post("/api/users", headers=admin_headers, json={
        "login": "wh_del", "password": "haslo123", "role": "warehouse",
        "company_id": acme_id, "view_all_companies": False, "warehouse_id": used["id"]})
    assert r.status_code == 201, r.text

    blocked = client.delete(f"/api/warehouses/{used['id']}", headers=admin_headers)
    assert blocked.status_code == 409
    assert "używany przez" in blocked.json()["detail"]

    assert client.delete(f"/api/warehouses/{free['id']}",
                         headers=admin_headers).status_code == 204
    assert _audit_entries("warehouses", free["id"])


# --- słowniki celne: agencje, typy dokumentów, statusy spraw ---

def test_delete_customs_dictionaries(client, admin_headers):
    agency = client.post("/api/customs-agencies", headers=admin_headers, json={
        "name": "Agencja do kasacji", "email": "a@a.pl"}).json()
    doc_type = client.post("/api/customs/document-types", headers=admin_headers,
                           json={"name": "Typ do kasacji"}).json()
    case_status = client.post("/api/customs/case-statuses", headers=admin_headers,
                              json={"name": "Status do kasacji"}).json()

    for path, row, table in (
            ("/api/customs-agencies", agency, "customs_agencies"),
            ("/api/customs/document-types", doc_type, "document_types"),
            ("/api/customs/case-statuses", case_status, "customs_case_statuses")):
        assert client.delete(f"{path}/{row['id']}",
                             headers=admin_headers).status_code == 204, path
        assert _audit_entries(table, row["id"]), table


def test_delete_customs_agency_blocked_by_user_account(client, admin_headers):
    agency = client.post("/api/customs-agencies", headers=admin_headers, json={
        "name": "Agencja z kontem", "email": "b@b.pl"}).json()
    r = client.post("/api/users", headers=admin_headers, json={
        "login": "customs_del", "password": "haslo123", "role": "customs",
        "company_id": None, "view_all_companies": False, "warehouse_id": None,
        "customs_agency_id": agency["id"]})
    assert r.status_code == 201, r.text
    blocked = client.delete(f"/api/customs-agencies/{agency['id']}", headers=admin_headers)
    assert blocked.status_code == 409
    assert "używany przez" in blocked.json()["detail"]


def test_edit_and_delete_customer(client, admin_headers):
    acme_id = _company_id(client, admin_headers, "ACME")
    cust = client.post("/api/customers", headers=admin_headers, json={
        "name": "Klient A", "contact": "a@a.pl", "company_id": acme_id}).json()
    # edycja nazwy + kontaktu (spółka bez zmian)
    edited = client.patch(f"/api/customers/{cust['id']}", headers=admin_headers,
                          json={"name": "Klient A2", "contact": "nowy@a.pl"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Klient A2"
    assert edited.json()["company_id"] == acme_id
    # blokada usunięcia: klient przypięty do kontenera → 409
    ports = client.get("/api/ports", headers=admin_headers).json()
    cont = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MEDU1234562", "company_id": acme_id, "port_id": ports[0]["id"]}).json()
    assert client.put(f"/api/containers/{cont['id']}/customer", headers=admin_headers,
                      json={"customer_id": cust["id"]}).status_code == 200
    blocked = client.delete(f"/api/customers/{cust['id']}", headers=admin_headers)
    assert blocked.status_code == 409
    # odepnij → usunięcie przechodzi (204)
    client.put(f"/api/containers/{cont['id']}/customer", headers=admin_headers,
               json={"customer_id": None})
    assert client.delete(f"/api/customers/{cust['id']}", headers=admin_headers).status_code == 204
    assert client.delete(f"/api/customers/{cust['id']}", headers=admin_headers).status_code == 404

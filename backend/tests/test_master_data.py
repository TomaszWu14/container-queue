"""Przeglądarka master data: rozszerzenia list (PO z filtrami, spółki dla logistyki,
sap_code/country dostawcy) + izolacja spółek."""
import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company, PurchaseOrder, today_pl
from tests.conftest import login


def _company_id(client, headers, code):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _logistics(client, admin_headers, company_id, name="log_md"):
    r = client.post("/api/users", headers=admin_headers, json={
        "login": name, "password": "haslo123", "role": "logistics",
        "company_id": company_id, "view_all_companies": False, "warehouse_id": None})
    assert r.status_code == 201, r.text
    return login(client, name, "haslo123")


def _seed_po(db, company, **kw):
    db.add(PurchaseOrder(company_id=company.id, **kw))


def _seed_two_companies(client):
    db = SessionLocal()
    try:
        acme = db.scalar(select(Company).where(Company.code == "ACME"))
        borealis = db.scalar(select(Company).where(Company.code == "BOREALIS"))
        _seed_po(db, acme, order_no="Z-100", supplier="Fushide",
                 etd=datetime.date(2026, 8, 1))
        _seed_po(db, acme, order_no="Z-200", supplier="Ningbo Tools",
                 etd=datetime.date(2026, 8, 5))
        _seed_po(db, borealis, order_no="T-100", supplier="Fushide")
        db.commit()
        return acme.id, borealis.id
    finally:
        db.close()


def test_po_list_without_company_code_respects_isolation(client, admin_headers):
    acme_id, _ = _seed_two_companies(client)
    # admin (view_all) bez company_code widzi obie spółki
    nums = {p["order_no"] for p in
            client.get("/api/purchase-orders", headers=admin_headers).json()}
    assert {"Z-100", "Z-200", "T-100"} <= nums
    # logistyk spółki ACME bez view_all — tylko swoja spółka
    log_hdr = _logistics(client, admin_headers, acme_id)
    nums = {p["order_no"] for p in
            client.get("/api/purchase-orders", headers=log_hdr).json()}
    assert "Z-100" in nums and "T-100" not in nums


def test_po_search_and_date_filters(client, admin_headers):
    _seed_two_companies(client)
    # wyszukiwarka: numer LUB dostawca (case-insensitive)
    nums = {p["order_no"] for p in client.get(
        "/api/purchase-orders?q=fushide", headers=admin_headers).json()}
    assert nums == {"Z-100", "T-100"}
    nums = {p["order_no"] for p in client.get(
        "/api/purchase-orders?q=Z-200", headers=admin_headers).json()}
    assert nums == {"Z-200"}
    # zakres dat utworzenia: dziś → wszystko; przyszłość → nic
    today = today_pl().isoformat()
    assert len(client.get(f"/api/purchase-orders?created_from={today}",
                          headers=admin_headers).json()) >= 3
    future = (today_pl() + datetime.timedelta(days=2)).isoformat()
    assert client.get(f"/api/purchase-orders?created_from={future}",
                      headers=admin_headers).json() == []
    # odpowiedź niesie pola master data
    po = client.get("/api/purchase-orders?q=Z-100", headers=admin_headers).json()[0]
    assert po["company_id"] and po["created_at"] and "purchase_decision" in po


def test_supplier_out_has_sap_code_and_country(client, admin_headers):
    acme = _company_id(client, admin_headers, "ACME")
    sup = client.post("/api/suppliers", headers=admin_headers,
                      json={"name": "MD Supplier", "company_id": acme}).json()
    row = next(s for s in client.get("/api/suppliers", headers=admin_headers).json()
               if s["id"] == sup["id"])
    assert row["sap_code"] == "" and row["country"] == ""


def test_companies_readable_by_logistics_scoped(client, admin_headers):
    acme = _company_id(client, admin_headers, "ACME")
    log_hdr = _logistics(client, admin_headers, acme, name="log_md2")
    companies = client.get("/api/companies", headers=log_hdr)
    assert companies.status_code == 200
    codes = {c["code"] for c in companies.json()}
    assert codes == {"ACME"}  # bez view_all: tylko własna spółka
    # zapis spółek zostaje admin-only
    denied = client.post("/api/companies", headers=log_hdr,
                         json={"name": "Nowa", "code": "NOWA"})
    assert denied.status_code == 403

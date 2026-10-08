"""Widoczność kartoteki dostawców (spec 2026-09-25 §2 „Widoczność"): reguła w deps.py,
kody spółek „z materiałami" z ustawień (SUPPLIER_COMPANY_CODES)."""
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Company, Role, Supplier, SupplierContact, User, Warehouse
from app.security import hash_password
from tests.conftest import forwarder, login


def _co(db, code):
    return db.scalar(select(Company).where(Company.code == code))


def _seed():
    with SessionLocal() as db:
        acme, pt, borealis = (_co(db, c) for c in ("ACME", "PT", "BOREALIS"))
        cat = Supplier(name="Kartoteka Co", sap_code="500100", address="Ningbo, CN")
        tim = Supplier(name="Nadawca Borealis", client_company_id=borealis.id, address="Adres T")
        wh = Warehouse(name="WH-Z", company_id=acme.id)
        db.add_all([cat, tim, wh])
        db.flush()
        db.add(SupplierContact(supplier_id=cat.id, full_name="Li", email="li@k.example"))
        for login_, role, cid, whid in (("vis-pt-zak", Role.purchasing, pt.id, None),
                                        ("vis-t-log", Role.logistics, borealis.id, None),
                                        ("vis-z-wh", Role.warehouse, acme.id, wh.id)):
            db.add(User(login=login_, hashed_password=hash_password("pass12345"), role=role,
                        company_id=cid, warehouse_id=whid))
        db.commit()
        return cat.id, tim.id


def _rows(client, hdr):
    return {s["name"]: s for s in client.get("/api/suppliers", headers=hdr).json()}


def test_material_company_purchasing_sees_catalog_with_details(client):
    cat, _ = _seed()
    hdr = login(client, "vis-pt-zak", "pass12345")
    rows = _rows(client, hdr)
    assert "Kartoteka Co" in rows and "Nadawca Borealis" not in rows
    assert rows["Kartoteka Co"]["sap_code"] == "500100"
    assert rows["Kartoteka Co"]["client_company_id"] is None
    assert client.get(f"/api/suppliers/{cat}/stats", headers=hdr).status_code == 200
    contacts = client.get(f"/api/supplier-contacts?supplier_id={cat}", headers=hdr).json()
    assert [c["full_name"] for c in contacts] == ["Li"]


def test_client_company_sees_only_own_senders(client):
    cat, tim = _seed()
    hdr = login(client, "vis-t-log", "pass12345")
    assert set(_rows(client, hdr)) == {"Nadawca Borealis"}
    assert client.get(f"/api/suppliers/{cat}/stats", headers=hdr).status_code == 404
    assert client.get(f"/api/suppliers/{tim}/stats", headers=hdr).status_code == 200
    assert client.get("/api/supplier-contacts", headers=hdr).json() == []


def test_warehouse_of_material_company_gets_names_only(client):
    cat, _ = _seed()
    hdr = login(client, "vis-z-wh", "pass12345")
    row = _rows(client, hdr)["Kartoteka Co"]
    assert row["sap_code"] == "" and row["address"] == ""
    # magazyn nie widzi dostawcy — statystyki zamknięte już bramką roli (2026-10-05)
    assert client.get(f"/api/suppliers/{cat}/stats", headers=hdr).status_code == 403


def test_forwarder_gets_names_without_details(client, admin_headers):
    _seed()
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    client.post("/api/users", headers=admin_headers, json={
        "login": "vis.fwd", "password": "haslo123", "role": "forwarder",
        "forwarder_id": spedalfa, "email": "vis.fwd@example.com"})
    rows = _rows(client, login(client, "vis.fwd", "haslo123"))
    assert rows["Kartoteka Co"]["sap_code"] == "" and rows["Nadawca Borealis"]["address"] == ""


def test_material_company_codes_come_from_settings(client, monkeypatch):
    _seed()
    monkeypatch.setattr(settings, "supplier_company_codes", "ACME")
    assert "Kartoteka Co" not in _rows(client, login(client, "vis-pt-zak", "pass12345"))


def test_create_maps_company_to_catalog_or_client_sender(client, admin_headers):
    with SessionLocal() as db:
        acme, borealis = _co(db, "ACME").id, _co(db, "BOREALIS").id
    a = client.post("/api/suppliers", headers=admin_headers,
                    json={"name": "Nowy K", "company_id": acme}).json()
    b = client.post("/api/suppliers", headers=admin_headers,
                    json={"name": "Nowy K", "company_id": borealis}).json()
    c = client.post("/api/suppliers", headers=admin_headers, json={"name": "Bez spółki"}).json()
    assert (a["client_company_id"], b["client_company_id"], c["client_company_id"]) == (
        None, borealis, None)
    # ta sama nazwa w kartotece → 409 (spółka z materiałami i brak spółki = ta sama kartoteka)
    assert client.post("/api/suppliers", headers=admin_headers,
                       json={"name": "Nowy K"}).status_code == 409


def test_patch_catalog_twin_with_unchanged_name_is_ok(client, admin_headers):
    """Po migracji kopia ACME/PT ma bliźniaka o tej samej nazwie — „Nieaktywny" nie może 409."""
    with SessionLocal() as db:
        a, b = Supplier(name="Blizniak", sap_code="610"), Supplier(name="Blizniak", sap_code="611")
        db.add_all([a, b])
        db.commit()
        aid = a.id
    r = client.patch(f"/api/suppliers/{aid}", headers=admin_headers,
                     json={"name": "Blizniak", "is_active": False})
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False


def test_rename_client_sender_to_taken_name_is_409(client, admin_headers):
    with SessionLocal() as db:
        borealis = _co(db, "BOREALIS").id
        a = Supplier(name="Nadawca A", client_company_id=borealis)
        db.add_all([a, Supplier(name="Nadawca B", client_company_id=borealis)])
        db.commit()
        aid = a.id
    assert client.patch(f"/api/suppliers/{aid}", headers=admin_headers,
                        json={"name": "Nadawca B"}).status_code == 409

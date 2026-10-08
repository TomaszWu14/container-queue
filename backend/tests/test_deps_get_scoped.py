"""Fetch-po-id tylko przez deps.get_scoped / get_company_scoped (audyt 2026-09-23, P5)."""
import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.deps import get_company_scoped
from app.models import (CartStatus, Company, Container, PurchaseOrder, Role, Supplier, User,
                        Warehouse)
from app.security import hash_password
from tests.conftest import login


def _two_companies():
    with SessionLocal() as db:
        a = Company(name="GS A", code="GSA"); b = Company(name="GS B", code="GSB")
        db.add_all([a, b]); db.flush()
        wh_b = Warehouse(name="GS-WB", company_id=b.id)
        cont_b = Container(container_no="GSCU0000001", company_id=b.id)
        sup_b = Supplier(name="GS-SB", client_company_id=b.id)
        db.add_all([wh_b, cont_b, sup_b]); db.flush()
        # zamówienie spółki A przypięte do kontenera spółki B (koszyk/konsolidacja)
        po_a = PurchaseOrder(company_id=a.id, order_no="GS-A1", container_id=cont_b.id,
                             cbm=1, cart_status=CartStatus.przypisane.value)
        po_b = PurchaseOrder(company_id=b.id, order_no="GS-B1", cbm=1)
        user_a = User(login="gs-log-a", hashed_password=hash_password("pass12345"),
                      role=Role.logistics, company_id=a.id)
        db.add_all([po_a, po_b, user_a]); db.commit()
        return {"wh_b": wh_b.id, "sup_b": sup_b.id, "po_a": po_a.id, "po_b": po_b.id}


def test_foreign_and_missing_record_give_identical_404(client, admin_headers):
    """Jednolite 404: rekord cudzej spółki nie różni się od nieistniejącego (bez enumeracji).
    Ręczne kopie miały własne komunikaty („Nie znaleziono magazynu.”) tylko dla braku."""
    ids = _two_companies()
    hdr = login(client, "gs-log-a", "pass12345")
    foreign = client.get(f"/api/calendar?warehouse_id={ids['wh_b']}", headers=hdr)
    missing = client.get("/api/calendar?warehouse_id=999999", headers=hdr)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_company_scoped_dictionary_foreign_and_missing_identical_404(client, admin_headers):
    """Słownik company_scoped (dostawcy, _get_or_404): cudzy dostawca = nieistniejący."""
    ids = _two_companies()
    hdr = login(client, "gs-log-a", "pass12345")
    foreign = client.get(f"/api/suppliers/{ids['sup_b']}/stats", headers=hdr)
    missing = client.get("/api/suppliers/999999/stats", headers=hdr)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_get_company_scoped_uses_company_not_container(client):
    ids = _two_companies()
    with SessionLocal() as db:
        user_a = db.query(User).filter_by(login="gs-log-a").one()
        # własne zamówienie w cudzym kontenerze — dostęp po spółce zamówienia
        assert get_company_scoped(db, PurchaseOrder, ids["po_a"], user_a).order_no == "GS-A1"
        for po_id in (ids["po_b"], 999999):
            with pytest.raises(HTTPException) as exc:
                get_company_scoped(db, PurchaseOrder, po_id, user_a)
            assert exc.value.status_code == 404

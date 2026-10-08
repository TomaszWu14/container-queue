"""Słownik mapowań indeksów dostawcy (feature #12): pierwszeństwo w dopasowaniu pozycji
faktury + CRUD endpointów."""
from sqlalchemy import select

from app.invoices import matching
from app.models import Company, InvoiceMatchStatus, Material, Supplier, SupplierMaterialMap

from .conftest import login


def _seed(db):
    company = db.scalars(select(Company)).first()
    supplier = Supplier(name="Dostawca Mapowy", client_company_id=company.id)
    db.add(supplier)
    db.add(Material(ref_code="ABC1", ref_norm="ABC1", name_pl="Rurka"))
    db.flush()
    return company, supplier


def test_supplier_map_wins_over_rules(db_session):
    company, supplier = _seed(db_session)
    db_session.add(SupplierMaterialMap(company_id=company.id, supplier_id=supplier.id,
                                       supplier_code="X-99", ref_code="ABC1"))
    db_session.commit()
    items = matching.build_items(db_session, [{"ref": "X-99", "qty": "10"}],
                                 company.id, supplier_id=supplier.id)
    assert items[0].match_status == InvoiceMatchStatus.matched
    assert items[0].master_ref == "ABC1"
    assert items[0].match_source == "supplier_map"


def test_no_map_falls_through_to_rules(db_session):
    company, supplier = _seed(db_session)
    db_session.commit()
    # bez mapy 'X-99' nie pasuje do żadnego REF → nie jest to dopasowanie z mapy
    items = matching.build_items(db_session, [{"ref": "X-99"}],
                                 company.id, supplier_id=supplier.id)
    assert items[0].match_source != "supplier_map"


def test_crud_and_upsert(client, db_session):
    company, supplier = _seed(db_session)
    db_session.commit()
    hdr = login(client)
    base = {"company_code": company.code, "supplier_id": supplier.id, "supplier_code": "X-99"}

    r = client.post("/api/supplier-material-maps", headers=hdr, json={**base, "ref_code": "ABC1", "note": "n"})
    assert r.status_code == 201, r.text
    map_id = r.json()["id"]

    # ten sam (spółka, dostawca, kod) = upsert ref_code, nie nowy wiersz
    r2 = client.post("/api/supplier-material-maps", headers=hdr, json={**base, "ref_code": "ABC2"})
    assert r2.status_code == 201 and r2.json()["id"] == map_id and r2.json()["ref_code"] == "ABC2"

    lst = client.get(f"/api/supplier-material-maps?supplier_id={supplier.id}", headers=hdr)
    assert lst.status_code == 200 and len(lst.json()) == 1

    p = client.patch(f"/api/supplier-material-maps/{map_id}", headers=hdr,
                     json={"supplier_code": "X-99", "ref_code": "ABC3", "note": "z"})
    assert p.status_code == 200 and p.json()["ref_code"] == "ABC3"

    assert client.delete(f"/api/supplier-material-maps/{map_id}", headers=hdr).status_code == 204
    assert client.get("/api/supplier-material-maps", headers=hdr).json() == []

"""Scalanie dostawców w kartotece globalnej (PR1): kolizje unikalności wygrywa cel, kontakty
po e-mailu, mapy indeksów per spółka, alias nazwy w spółkach, z których pochodzą pliki."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    Company,
    Container,
    Material,
    Order,
    Supplier,
    SupplierAlias,
    SupplierContact,
    SupplierMaterial,
    SupplierMaterialMap,
)


def _co(db, code):
    return db.scalar(select(Company).where(Company.code == code))


def _pair():
    with SessionLocal() as db:
        acme, pt = _co(db, "ACME"), _co(db, "PT")
        src = Supplier(name="ACME TRADING", sap_code="100")
        dst = Supplier(name="Acme Trading Co.", sap_code="100")
        m1, m2 = Material(ref_code="REF-M1", ref_norm="REFM1"), Material(ref_code="REF-M2", ref_norm="REFM2")
        db.add_all([src, dst, m1, m2])
        db.flush()
        db.add_all([
            SupplierMaterial(supplier_id=src.id, material_id=m1.id, supplier_code="S-1"),
            SupplierMaterial(supplier_id=src.id, material_id=m2.id, supplier_code="S-2"),
            SupplierMaterial(supplier_id=dst.id, material_id=m1.id, supplier_code="D-1"),
            SupplierMaterialMap(company_id=acme.id, supplier_id=src.id, supplier_code="X", ref_code="R-SRC"),
            SupplierMaterialMap(company_id=pt.id, supplier_id=src.id, supplier_code="X", ref_code="R-PT"),
            SupplierMaterialMap(company_id=acme.id, supplier_id=dst.id, supplier_code="X", ref_code="R-DST"),
        ])
        c_src = SupplierContact(supplier_id=src.id, full_name="Li", email="LI@acme.example")
        c_dst = SupplierContact(supplier_id=dst.id, full_name="Li Wei", email="li@acme.example")
        db.add_all([c_src, c_dst])
        db.flush()
        order = Order(number="PO-M1", company_id=pt.id, supplier_id=src.id,
                      supplier_contact_id=c_src.id)
        db.add_all([order, Container(container_no="MSKU5000009", company_id=pt.id,
                                     supplier_id=src.id)])
        db.commit()
        return src.id, dst.id, c_dst.id, order.id, pt.id, acme.id


def test_merge_resolves_unique_collisions_in_favour_of_target(client, admin_headers):
    src, dst, c_dst, order_id, pt, acme = _pair()
    r = client.post(f"/api/suppliers/{src}/merge", headers=admin_headers, json={"target_id": dst})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        codes = {m.supplier_code for m in db.scalars(
            select(SupplierMaterial).where(SupplierMaterial.supplier_id == dst))}
        assert codes == {"D-1", "S-2"}                       # materiał celu wygrał
        maps = {(m.company_id, m.ref_code) for m in db.scalars(
            select(SupplierMaterialMap).where(SupplierMaterialMap.supplier_id == dst))}
        assert maps == {(acme, "R-DST"), (pt, "R-PT")}      # kolizja tylko w tej samej spółce
        contacts = db.scalars(select(SupplierContact).where(SupplierContact.supplier_id == dst)).all()
        assert [c.id for c in contacts] == [c_dst]           # ten sam e-mail = jeden kontakt
        assert db.get(Order, order_id).supplier_contact_id == c_dst
        aliases = {(a.company_id, a.alias) for a in db.scalars(
            select(SupplierAlias).where(SupplierAlias.supplier_id == dst))}
        assert aliases == {(pt, "ACME TRADING")}             # spółka kontenerów duplikatu


def test_merge_of_same_name_adds_no_alias(client, admin_headers):
    with SessionLocal() as db:
        pt = _co(db, "PT")
        a, b = Supplier(name="Same Co", sap_code="7"), Supplier(name="SAME CO.", sap_code="7")
        db.add_all([a, b])
        db.flush()
        db.add(Container(container_no="MSKU5000014", company_id=pt.id, supplier_id=a.id))
        db.commit()
        a_id, b_id = a.id, b.id
    r = client.post(f"/api/suppliers/{a_id}/merge", headers=admin_headers, json={"target_id": b_id})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.scalars(select(SupplierAlias)).all() == []

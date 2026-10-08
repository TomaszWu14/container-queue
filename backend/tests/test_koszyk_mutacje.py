from app.consolidation import container_fill_cbm
from app.database import SessionLocal
from app.models import CartStatus, Company, ConsolidationStatus, Container, PurchaseOrder, Role, User
from app.security import hash_password

from tests.conftest import login


def _seed(db):
    co = db.query(Company).first()
    cont = Container(container_no="KMCU0000001", company_id=co.id)
    db.add(cont); db.flush()
    po = PurchaseOrder(company_id=co.id, order_no="KM-A", cbm=5,
                       cart_status=CartStatus.zwolnione.value)
    db.add(po); db.commit()
    return cont.id, po.id


def test_assign_and_remove(client, admin_headers):
    with SessionLocal() as db:
        cid, pid = _seed(db)
    r = client.put(f"/api/containers/{cid}/orders/{pid}", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["cart_status"] == "przypisane"
    assert r.json()["container_id"] == cid
    d = client.delete(f"/api/containers/{cid}/orders/{pid}", headers=admin_headers)
    assert d.status_code == 200 and d.json()["container_id"] is None
    assert d.json()["cart_status"] == "w_koszyku"


def test_assign_to_closed_container_400(client, admin_headers):
    with SessionLocal() as db:
        cid, pid = _seed(db)
        cont = db.get(Container, cid)
        cont.consolidation_status = ConsolidationStatus.zamkniety.value
        db.commit()
    r = client.put(f"/api/containers/{cid}/orders/{pid}", headers=admin_headers)
    assert r.status_code == 400
    assert "zamkni" in r.json()["detail"].lower()


def test_release_sets_zwolnione(client, admin_headers):
    with SessionLocal() as db:
        co = db.query(Company).first()
        po = PurchaseOrder(company_id=co.id, order_no="KM-R", cart_status=CartStatus.w_koszyku.value)
        db.add(po); db.commit(); pid = po.id
    r = client.post(f"/api/purchase-orders/{pid}/release", headers=admin_headers)
    assert r.status_code == 200 and r.json()["cart_status"] == "zwolnione"


def test_block_excludes_from_fill(client, admin_headers):
    with SessionLocal() as db:
        co = db.query(Company).first()
        cont = Container(container_no="KMCU0000009", company_id=co.id); db.add(cont); db.flush()
        po = PurchaseOrder(company_id=co.id, order_no="KM-B", cbm=8, container_id=cont.id,
                           cart_status=CartStatus.przypisane.value)
        db.add(po); db.commit(); cid, pid = cont.id, po.id
        assert container_fill_cbm(db, cid) == 8.0
    r = client.post(f"/api/purchase-orders/{pid}/block", headers=admin_headers)
    assert r.status_code == 200 and r.json()["cart_status"] == "zablokowane"
    with SessionLocal() as db:
        assert container_fill_cbm(db, cid) == 0.0   # zablokowane wypada


def test_close_consolidation_blocks_assign(client, admin_headers):
    with SessionLocal() as db:
        co = db.query(Company).first()
        cont = Container(container_no="KMCU0000010", company_id=co.id); db.add(cont); db.flush()
        po = PurchaseOrder(company_id=co.id, order_no="KM-C", cart_status=CartStatus.zwolnione.value)
        db.add(po); db.commit(); cid, pid = cont.id, po.id
    c = client.post(f"/api/containers/{cid}/close-consolidation", headers=admin_headers)
    assert c.status_code == 200 and c.json()["consolidation_status"] == "zamkniety"
    r = client.put(f"/api/containers/{cid}/orders/{pid}", headers=admin_headers)
    assert r.status_code == 400


def test_assign_cross_company_404_for_scoped_user(client, admin_headers):
    """logistics przypisany do spółki A dostaje 404 przy assign kontener/zamówienie spółki B."""
    with SessionLocal() as db:
        co_a = Company(name="Koszyk A", code="KMA")
        co_b = Company(name="Koszyk B", code="KMB")
        db.add_all([co_a, co_b]); db.flush()
        cont_b = Container(container_no="KMCU0000020", company_id=co_b.id)
        po_b = PurchaseOrder(company_id=co_b.id, order_no="KM-XB", cart_status=CartStatus.zwolnione.value)
        db.add_all([cont_b, po_b])
        db.add(User(login="km-log-a", hashed_password=hash_password("pass12345"),
                    role=Role.logistics, company_id=co_a.id))
        db.commit()
        cid, pid = cont_b.id, po_b.id
    hdr = login(client, "km-log-a", "pass12345")
    r = client.put(f"/api/containers/{cid}/orders/{pid}", headers=hdr)
    assert r.status_code == 404


def test_block_forbidden_for_warehouse_role(client, admin_headers):
    """warehouse (spoza admin/logistics/purchasing) dostaje 403 przy block."""
    with SessionLocal() as db:
        co = db.query(Company).first()
        po = PurchaseOrder(company_id=co.id, order_no="KM-WH", cart_status=CartStatus.w_koszyku.value)
        db.add(po)
        db.add(User(login="km-wh", hashed_password=hash_password("pass12345"),
                    role=Role.warehouse, company_id=co.id))
        db.commit()
        pid = po.id
    hdr = login(client, "km-wh", "pass12345")
    r = client.post(f"/api/purchase-orders/{pid}/block", headers=hdr)
    assert r.status_code == 403


def test_assign_cross_company_400_as_admin(client, admin_headers):
    """Strażnik integralności: admin nie może przypisać zamówienia spółki B do kontenera spółki A."""
    with SessionLocal() as db:
        co_a = Company(name="Koszyk C", code="KMC")
        co_b = Company(name="Koszyk D", code="KMD")
        db.add_all([co_a, co_b]); db.flush()
        cont_a = Container(container_no="KMCU0000030", company_id=co_a.id)
        po_b = PurchaseOrder(company_id=co_b.id, order_no="KM-XD", cart_status=CartStatus.zwolnione.value)
        db.add_all([cont_a, po_b]); db.commit()
        cid, pid = cont_a.id, po_b.id
    r = client.put(f"/api/containers/{cid}/orders/{pid}", headers=admin_headers)
    assert r.status_code == 400

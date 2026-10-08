from app.database import SessionLocal
from app.models import Company, Container, PurchaseOrder, CartStatus, ConsolidationStatus


def test_new_fields_have_defaults(client):
    with SessionLocal() as db:
        co = Company(name="FM Co", code="FMCO")
        db.add(co); db.flush()
        po = PurchaseOrder(company_id=co.id, order_no="PO-1")
        cont = Container(container_no="FMCU0000001", company_id=co.id)
        db.add_all([po, cont]); db.commit()
        db.refresh(po); db.refresh(cont)
        assert po.cart_status == CartStatus.w_koszyku.value
        assert po.crd is None and po.crd_target is None
        assert cont.consolidation_status == ConsolidationStatus.otwarty.value
        assert float(cont.capacity_cbm) == 70.0


import datetime
from app.consolidation import container_fill_cbm, container_crd, can_add_order


def _seed_consolidation(db):
    co = Company(name="CN Co", code="CNCO"); db.add(co); db.flush()
    cont = Container(container_no="CNCU0000001", company_id=co.id)
    db.add(cont); db.flush()
    d = datetime.date
    db.add_all([
        PurchaseOrder(company_id=co.id, order_no="A", container_id=cont.id,
                      cbm=10, crd=d(2026, 9, 10), cart_status=CartStatus.przypisane.value),
        PurchaseOrder(company_id=co.id, order_no="B", container_id=cont.id,
                      cbm=20, crd=d(2026, 9, 15), cart_status=CartStatus.przypisane.value),
        # zablokowane — NIE liczy się do fill ani CRD
        PurchaseOrder(company_id=co.id, order_no="C", container_id=cont.id,
                      cbm=999, crd=d(2027, 1, 1), cart_status=CartStatus.zablokowane.value),
    ])
    db.commit()
    return cont


def test_fill_cbm_ignores_blocked(client):
    with SessionLocal() as db:
        cont = _seed_consolidation(db)
        assert container_fill_cbm(db, cont.id) == 30.0        # 10+20, bez 999


def test_crd_is_latest_of_unblocked(client):
    with SessionLocal() as db:
        cont = _seed_consolidation(db)
        assert container_crd(db, cont.id) == datetime.date(2026, 9, 15)  # max(10,15), bez 2027


def test_can_add_order_false_when_closed(client):
    with SessionLocal() as db:
        co = Company(name="ZC", code="ZCCO"); db.add(co); db.flush()
        closed = Container(container_no="ZCCU0000001", company_id=co.id,
                           consolidation_status=ConsolidationStatus.zamkniety.value)
        db.add(closed); db.commit()
        assert can_add_order(closed) is False


from sqlalchemy import select as _select


def test_container_orders_endpoint(client, admin_headers):
    with SessionLocal() as db:
        co = db.scalar(_select(Company).limit(1)) or Company(name="EP", code="EPCO")
        if not co.id:
            db.add(co); db.flush()
        cont = Container(container_no="EPCU0000001", company_id=co.id)
        db.add(cont); db.flush()
        db.add(PurchaseOrder(company_id=co.id, order_no="EP-A", container_id=cont.id,
                             cbm=12, cart_status=CartStatus.przypisane.value))
        db.commit()
        cid = cont.id
    r = client.get(f"/api/containers/{cid}/orders", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fill_cbm"] == 12.0
    assert float(body["capacity_cbm"]) == 70.0
    assert body["consolidation_status"] == "otwarty"
    assert len(body["orders"]) == 1 and body["orders"][0]["order_no"] == "EP-A"


def test_list_open_consolidation_containers(client, admin_headers):
    with SessionLocal() as db:
        co = db.query(Company).first()
        opened = Container(container_no="LOCU0000001", company_id=co.id)
        closed = Container(container_no="LOCU0000002", company_id=co.id,
                           consolidation_status=ConsolidationStatus.zamkniety.value)
        db.add_all([opened, closed]); db.flush()
        db.add(PurchaseOrder(company_id=co.id, order_no="LOC-A", cbm=7,
                             container_id=opened.id, cart_status=CartStatus.przypisane.value))
        db.commit(); oid = opened.id
    r = client.get("/api/consolidation/containers?status=otwarty", headers=admin_headers)
    assert r.status_code == 200, r.text
    rows = {row["id"]: row for row in r.json()}
    assert oid in rows and rows[oid]["fill_cbm"] == 7.0 and rows[oid]["order_count"] == 1
    # zamkniety nie na liscie 'otwarty'
    assert all(row["consolidation_status"] == "otwarty" for row in r.json())

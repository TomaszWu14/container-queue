import datetime
from app.consolidation import crd_deviation_days, CRD_ESCALATION_DAYS
from app.models import PurchaseOrder


def test_deviation_none_without_dates(client):
    assert crd_deviation_days(PurchaseOrder(order_no="X")) is None


def test_deviation_positive_days(client):
    po = PurchaseOrder(order_no="Y", crd=datetime.date(2026, 9, 25),
                       crd_target=datetime.date(2026, 9, 10))
    assert crd_deviation_days(po) == 15
    assert CRD_ESCALATION_DAYS == 10


from app.database import SessionLocal
from app.models import Company, CartStatus, Container


def _po(db, **kw):
    co = db.query(Company).first()
    kw.setdefault("cart_status", CartStatus.w_koszyku.value)
    po = PurchaseOrder(company_id=co.id, order_no=kw.pop("order_no", "CRD-1"), **kw)
    db.add(po); db.commit()
    return po.id


def test_crd_update_within_threshold_no_block(client, admin_headers):
    with SessionLocal() as db:
        pid = _po(db, order_no="CRD-OK")
    r = client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                     json={"crd": "2026-09-15", "crd_target": "2026-09-10"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deviation_days"] == 5 and body["cart_status"] == "w_koszyku"


def test_crd_update_over_threshold_auto_blocks(client, admin_headers):
    with SessionLocal() as db:
        pid = _po(db, order_no="CRD-BLK")
    r = client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                     json={"crd": "2026-09-25", "crd_target": "2026-09-10"})
    assert r.status_code == 200
    assert r.json()["deviation_days"] == 15 and r.json()["cart_status"] == "zablokowane"


def test_new_target_unblocks_when_below_threshold(client, admin_headers):
    with SessionLocal() as db:
        pid = _po(db, order_no="CRD-UNB")
    client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                 json={"crd": "2026-09-25", "crd_target": "2026-09-10"})  # zablokowane
    r = client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                     json={"crd": "2026-09-25", "crd_target": "2026-09-20"})  # odchylenie 5
    assert r.json()["cart_status"] == "w_koszyku"


def test_crd_deviation_exactly_at_threshold_blocks(client, admin_headers):
    with SessionLocal() as db:
        pid = _po(db, order_no="CRD-EQ")
    r = client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                     json={"crd": "2026-09-20", "crd_target": "2026-09-10"})  # odchylenie == 10
    assert r.json()["deviation_days"] == 10 and r.json()["cart_status"] == "zablokowane"


def test_crd_negative_deviation_no_block(client, admin_headers):
    with SessionLocal() as db:
        pid = _po(db, order_no="CRD-NEG")
    r = client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                     json={"crd": "2026-09-05", "crd_target": "2026-09-10"})  # odchylenie -5
    assert r.json()["deviation_days"] == -5 and r.json()["cart_status"] == "w_koszyku"


def test_po_dict_exposes_crd_target_and_deviation(client, admin_headers):
    with SessionLocal() as db:
        co = db.query(Company).first()
        po = PurchaseOrder(company_id=co.id, order_no="PD-1",
                           crd=datetime.date(2026, 9, 25), crd_target=datetime.date(2026, 9, 10),
                           cart_status=CartStatus.w_koszyku.value)
        db.add(po); db.commit()
    r = client.get("/api/purchase-orders?cart_status=w_koszyku", headers=admin_headers)
    row = next(x for x in r.json() if x["order_no"] == "PD-1")
    assert row["crd_target"] == "2026-09-10"
    assert row["deviation_days"] == 15


def test_crd_unblock_restores_przypisane_when_in_container(client, admin_headers):
    with SessionLocal() as db:
        co = db.query(Company).first()
        cont = Container(container_no="KMCU0000099", company_id=co.id)
        db.add(cont); db.flush()
        pid = _po(db, order_no="CRD-CONT", container_id=cont.id,
                  cart_status=CartStatus.przypisane.value)
    r = client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                     json={"crd": "2026-09-25", "crd_target": "2026-09-10"})  # eskalacja
    assert r.json()["cart_status"] == "zablokowane"
    with SessionLocal() as db:
        from app.models import PurchaseOrder as PO
        po = db.get(PO, pid)
        assert po.container_id == cont.id  # container_id zachowany mimo blokady

    r2 = client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                      json={"crd": "2026-09-25", "crd_target": "2026-09-20"})  # odchylenie 5
    assert r2.json()["cart_status"] == "przypisane"
    with SessionLocal() as db:
        from app.models import PurchaseOrder as PO
        assert db.get(PO, pid).container_id == cont.id


from app.models import Notification, User, Role
from app.security import hash_password


def test_escalation_notifies_purchasing(client, admin_headers):
    with SessionLocal() as db:
        co = db.query(Company).first()
        buyer = User(login="kupiec.crd", email="k@example.com", full_name="Kupiec",
                     hashed_password=hash_password("haslo123"), role=Role.purchasing,
                     company_id=co.id, is_active=True)
        db.add(buyer)
        po = PurchaseOrder(company_id=co.id, order_no="CRD-ALERT",
                           cart_status=CartStatus.w_koszyku.value)
        db.add(po); db.commit(); pid, bid = po.id, buyer.id
    r = client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                     json={"crd": "2026-09-25", "crd_target": "2026-09-10"})  # odchylenie 15 -> blokada
    assert r.status_code == 200 and r.json()["cart_status"] == "zablokowane"
    with SessionLocal() as db:
        notes = db.query(Notification).filter(Notification.user_id == bid,
                                              Notification.kind == "crd_escalation").all()
        assert len(notes) == 1


def test_no_alert_when_no_transition(client, admin_headers):
    # aktualizacja w granicy progu nie wysyła alertu
    with SessionLocal() as db:
        co = db.query(Company).first()
        buyer = User(login="kupiec.crd2", email="k2@example.com", full_name="Kupiec2",
                     hashed_password=hash_password("haslo123"), role=Role.purchasing,
                     company_id=co.id, is_active=True)
        db.add(buyer)
        po = PurchaseOrder(company_id=co.id, order_no="CRD-NOALERT",
                           cart_status=CartStatus.w_koszyku.value)
        db.add(po); db.commit(); pid, bid = po.id, buyer.id
    client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                 json={"crd": "2026-09-15", "crd_target": "2026-09-10"})  # odchylenie 5, brak blokady
    with SessionLocal() as db:
        assert db.query(Notification).filter(Notification.user_id == bid).count() == 0

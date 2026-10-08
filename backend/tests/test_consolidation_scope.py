"""Konsolidacja: role na odczytach, izolacja zakresu (deps) i batch listy kontenerów."""
import datetime

from app.database import SessionLocal
from app.models import CartStatus, Company, Container, PurchaseOrder, Role, User, Warehouse
from app.security import hash_password
from tests.conftest import login


def _wh_user_with_containers():
    """Magazynier W1 + kontenery w W1 i W2 tej samej spółki."""
    with SessionLocal() as db:
        co = Company(name="Scope Co", code="SCCO"); db.add(co); db.flush()
        w1 = Warehouse(name="W1", company_id=co.id)
        w2 = Warehouse(name="W2", company_id=co.id)
        db.add_all([w1, w2]); db.flush()
        c2 = Container(container_no="SCCU0000002", company_id=co.id, warehouse_id=w2.id)
        db.add(c2); db.flush()
        db.add(PurchaseOrder(company_id=co.id, order_no="SC-W2", container_id=c2.id,
                             cbm=5, cart_status=CartStatus.przypisane.value))
        db.add(User(login="sc-wh1", hashed_password=hash_password("pass12345"),
                    role=Role.warehouse, company_id=co.id, warehouse_id=w1.id))
        db.commit()
        return c2.id


def test_warehouse_forbidden_on_consolidation_reads(client, admin_headers):
    c2 = _wh_user_with_containers()
    hdr = login(client, "sc-wh1", "pass12345")
    assert client.get("/api/consolidation/containers", headers=hdr).status_code == 403
    assert client.get("/api/consolidation/proposals", headers=hdr).status_code == 403
    assert client.get(f"/api/containers/{c2}/orders", headers=hdr).status_code == 403


def test_other_company_container_orders_404(client, admin_headers):
    with SessionLocal() as db:
        co_a = Company(name="Scope A", code="SCA"); co_b = Company(name="Scope B", code="SCB")
        db.add_all([co_a, co_b]); db.flush()
        cont_b = Container(container_no="SCCU0000010", company_id=co_b.id)
        db.add(cont_b)
        for login_name, role in (("sc-pur-a", Role.purchasing), ("sc-log-a", Role.logistics)):
            db.add(User(login=login_name, hashed_password=hash_password("pass12345"),
                        role=role, company_id=co_a.id))
        db.commit(); cid = cont_b.id
    for login_name in ("sc-pur-a", "sc-log-a"):
        hdr = login(client, login_name, "pass12345")
        assert client.get(f"/api/containers/{cid}/orders", headers=hdr).status_code == 404
        rows = client.get("/api/consolidation/containers", headers=hdr).json()
        assert cid not in {r["id"] for r in rows}


def test_list_batched_stats_ignore_blocked(client, admin_headers):
    d = datetime.date
    with SessionLocal() as db:
        co = Company(name="Batch Co", code="BTCO"); db.add(co); db.flush()
        full = Container(container_no="BTCU0000001", company_id=co.id)
        empty = Container(container_no="BTCU0000002", company_id=co.id)
        db.add_all([full, empty]); db.flush()
        db.add_all([
            PurchaseOrder(company_id=co.id, order_no="BT-A", container_id=full.id, cbm=10,
                          crd=d(2026, 9, 10), cart_status=CartStatus.przypisane.value),
            PurchaseOrder(company_id=co.id, order_no="BT-B", container_id=full.id, cbm=20,
                          crd=d(2026, 9, 15), cart_status=CartStatus.przypisane.value),
            PurchaseOrder(company_id=co.id, order_no="BT-C", container_id=full.id, cbm=999,
                          crd=d(2027, 1, 1), cart_status=CartStatus.zablokowane.value),
        ])
        db.commit(); fid, eid = full.id, empty.id
    rows = {r["id"]: r for r in client.get("/api/consolidation/containers",
                                           headers=admin_headers).json()}
    assert rows[fid]["order_count"] == 3
    assert rows[fid]["fill_cbm"] == 30.0
    assert rows[fid]["crd"] == "2026-09-15"
    assert rows[eid]["order_count"] == 0 and rows[eid]["fill_cbm"] == 0.0 and rows[eid]["crd"] is None

"""Plaster 6: silnik auto-propozycji konsolidacji (tylko odczyt, mono-dostawca)."""
from app.consolidation import propose_consolidation
from app.database import SessionLocal
from app.models import CartStatus, Company, PurchaseOrder


class Fake:
    def __init__(self, id, supplier, cbm, pod=None, podis=None):
        self.id, self.supplier, self.cbm = id, supplier, cbm
        self.port_of_departure, self.port_of_discharge = pod, podis


def test_two_orders_same_supplier_fit_one_bin():
    orders = [Fake(1, "ACME", 30), Fake(2, "ACME", 30)]
    proposals = propose_consolidation(orders)
    assert len(proposals) == 1
    core = {k: proposals[0][k] for k in ("supplier", "orders", "total_cbm")}
    assert core == {"supplier": "ACME", "orders": [1, 2], "total_cbm": 60.0}


def test_same_supplier_different_route_split():
    # auto-reguła #17: ten sam dostawca, ale różny port rozładunku → osobne propozycje
    orders = [Fake(1, "ACME", 10, podis="Gdańsk"), Fake(2, "ACME", 10, podis="Gdynia")]
    proposals = propose_consolidation(orders)
    assert len(proposals) == 2
    assert all(p["reason"].startswith("ACME") for p in proposals)


def test_overflow_splits_into_two_bins():
    orders = [Fake(1, "ACME", 30), Fake(2, "ACME", 50)]
    proposals = propose_consolidation(orders)
    assert len(proposals) == 2
    totals = sorted(p["total_cbm"] for p in proposals)
    assert totals == [30.0, 50.0]


def test_exact_capacity_boundary_fits_one_bin():
    orders = [Fake(1, "ACME", 40), Fake(2, "ACME", 30)]
    proposals = propose_consolidation(orders)
    assert len(proposals) == 1
    assert proposals[0]["total_cbm"] == 70.0


def test_single_order_over_capacity_gets_own_bin():
    orders = [Fake(1, "ACME", 999)]
    proposals = propose_consolidation(orders)
    assert len(proposals) == 1
    assert proposals[0]["orders"] == [1]
    assert proposals[0]["total_cbm"] == 999.0


def test_different_suppliers_kept_separate():
    orders = [Fake(1, "ACME", 10), Fake(2, "OTHER", 10)]
    proposals = propose_consolidation(orders)
    suppliers = {p["supplier"] for p in proposals}
    assert suppliers == {"ACME", "OTHER"}


def test_none_cbm_treated_as_zero_and_does_not_crash():
    orders = [Fake(1, "ACME", None), Fake(2, "ACME", 10)]
    proposals = propose_consolidation(orders)
    assert len(proposals) == 1
    assert proposals[0]["total_cbm"] == 10.0


def test_proposals_endpoint(client, admin_headers):
    with SessionLocal() as db:
        co = Company(name="AK Co", code="AKCO"); db.add(co); db.flush()
        db.add_all([
            PurchaseOrder(company_id=co.id, order_no="AK-1", supplier="ACME", cbm=30,
                          cart_status=CartStatus.w_koszyku.value),
            PurchaseOrder(company_id=co.id, order_no="AK-2", supplier="ACME", cbm=30,
                          cart_status=CartStatus.zwolnione.value),
            # zablokowane — poza zakresem konsolidacji
            PurchaseOrder(company_id=co.id, order_no="AK-3", supplier="ACME", cbm=999,
                          cart_status=CartStatus.zablokowane.value),
        ])
        db.commit()
    r = client.get("/api/consolidation/proposals", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    matching = [p for p in body if p["supplier"] == "ACME" and p["total_cbm"] == 60.0]
    assert len(matching) == 1

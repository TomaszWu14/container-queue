"""GET /api/purchase-orders — lista zamówień ETD dla kolejki (wczesny etap)."""
import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company, Container, PurchaseOrder
from tests.conftest import login


def _seed(db, company, **kw):
    po = PurchaseOrder(company_id=company.id, **kw)
    db.add(po)
    return po


def test_lists_only_unlinked_sorted_by_etd(client):
    hdr = login(client)
    db = SessionLocal()
    try:
        acme = db.scalar(select(Company).where(Company.code == "ACME"))
        cont = Container(company_id=acme.id, container_no="MSKU7026499")
        db.add(cont); db.flush()
        _seed(db, acme, order_no="B", etd=datetime.date(2026, 8, 5))
        _seed(db, acme, order_no="A", etd=datetime.date(2026, 8, 1))
        _seed(db, acme, order_no="C", etd=None)          # bez ETD → na koniec
        _seed(db, acme, order_no="LINKED", container_id=cont.id)  # powiązane → pominięte
        db.commit()
    finally:
        db.close()

    res = client.get("/api/purchase-orders?company_code=ACME", headers=hdr)
    assert res.status_code == 200, res.text
    nums = [p["order_no"] for p in res.json()]
    assert nums == ["A", "B", "C"]  # LINKED wykluczone, ETD rosnąco, None na końcu


def test_company_scoped(client):
    hdr = login(client)
    db = SessionLocal()
    try:
        acme = db.scalar(select(Company).where(Company.code == "ACME"))
        borealis = db.scalar(select(Company).where(Company.code == "BOREALIS"))
        _seed(db, acme, order_no="Z1")
        _seed(db, borealis, order_no="T1")
        db.commit()
    finally:
        db.close()
    acme_nums = [p["order_no"] for p in
                  client.get("/api/purchase-orders?company_code=ACME", headers=hdr).json()]
    assert "Z1" in acme_nums and "T1" not in acme_nums


def test_unlinked_false_returns_all(client):
    hdr = login(client)
    db = SessionLocal()
    try:
        acme = db.scalar(select(Company).where(Company.code == "ACME"))
        cont = Container(company_id=acme.id, container_no="MSKU7026499")
        db.add(cont); db.flush()
        _seed(db, acme, order_no="U")
        _seed(db, acme, order_no="L", container_id=cont.id)
        db.commit()
    finally:
        db.close()
    nums = [p["order_no"] for p in client.get(
        "/api/purchase-orders?company_code=ACME&unlinked=false", headers=hdr).json()]
    assert "U" in nums and "L" in nums


def test_limit_offset_and_total_count(client):
    """Przeglądarka master data: lista stronicowana (limit/offset) z X-Total-Count, po sortowaniu."""
    hdr = login(client)
    db = SessionLocal()
    try:
        acme = db.scalar(select(Company).where(Company.code == "ACME"))
        for i in range(5):
            _seed(db, acme, order_no=f"P{i}", etd=datetime.date(2026, 8, 1 + i))
        db.commit()
    finally:
        db.close()
    res = client.get("/api/purchase-orders?company_code=ACME&limit=2&offset=1", headers=hdr)
    assert res.status_code == 200, res.text
    assert [p["order_no"] for p in res.json()] == ["P1", "P2"]
    assert res.headers["X-Total-Count"] == "5"
    full = client.get("/api/purchase-orders?company_code=ACME", headers=hdr)
    assert full.headers["X-Total-Count"] == "5" and len(full.json()) == 5

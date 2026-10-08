"""KPI operacyjne kontenerów (W6/W15): rozkład statusów, przepustowość, lead-time."""
import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company, Container, ContainerStatus, Supplier, Warehouse
from tests.conftest import login


def _seed():
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        sup = Supplier(client_company_id=company.id, name="Dostawca A")
        wh = Warehouse(company_id=company.id, name="Magazyn 1")
        db.add_all([sup, wh])
        db.flush()
        now = datetime.datetime(2026, 9, 10, 12, 0)
        # 2 dostarczone (lead-time 5 i 15 dni; rozładunek 30 i 90 min)
        db.add(Container(company_id=company.id, container_no="AAAA1111111",
                         status=ContainerStatus.DOSTARCZONY, supplier_id=sup.id,
                         warehouse_id=wh.id, created_at=now - datetime.timedelta(days=5),
                         completed_at=now,
                         unload_started_at=now, unload_finished_at=now + datetime.timedelta(minutes=30)))
        db.add(Container(company_id=company.id, container_no="BBBB2222222",
                         status=ContainerStatus.DOSTARCZONY, supplier_id=sup.id,
                         warehouse_id=wh.id, created_at=now - datetime.timedelta(days=15),
                         completed_at=now,
                         unload_started_at=now, unload_finished_at=now + datetime.timedelta(minutes=90)))
        # 1 w drodze (bez completed_at) — liczy się tylko do statusów
        db.add(Container(company_id=company.id, container_no="CCCC3333333",
                         status=ContainerStatus.ZAPOWIEDZIANY, supplier_id=sup.id))
        db.commit()
    finally:
        db.close()


def test_operational_kpi(client):
    hdr = login(client)
    _seed()
    resp = client.get("/api/analytics/operational?months=12", headers=hdr)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 3
    assert data["by_status"]["DOSTARCZONY"] == 2
    assert data["by_status"]["ZAPOWIEDZIANY"] == 1
    assert data["avg_lead_time_days"] == 10.0          # (5 + 15) / 2
    assert data["avg_unload_minutes"] == 60.0          # (30 + 90) / 2
    # przepustowość: 2 dostarczone w 2026-09
    sep = next(b for b in data["throughput"] if b["month"] == "2026-09")
    assert sep["count"] == 2
    assert data["top_suppliers"][0] == {"name": "Dostawca A", "count": 3}
    assert data["top_warehouses"][0] == {"name": "Magazyn 1", "count": 2}


def test_operational_requires_auth(client):
    assert client.get("/api/analytics/operational").status_code == 401

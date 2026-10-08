"""KPI spedycji (W9): zlecenia per spedytor, statusy, czas realizacji, % odrzuceń."""
import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    Company,
    Container,
    Forwarder,
    TransportOrder,
    TransportOrderStatus,
)
from tests.conftest import login


def _seed():
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        fwd = Forwarder(name="Spedytor X")
        cont = Container(company_id=company.id, container_no="DDDD4444444")
        db.add_all([fwd, cont])
        db.flush()
        d = datetime.date(2026, 9, 1)
        db.add(TransportOrder(container_id=cont.id, company_id=company.id, forwarder_id=fwd.id,
                              status=TransportOrderStatus.WYKONANE,
                              pickup_date=d, delivery_date=d + datetime.timedelta(days=4)))
        db.add(TransportOrder(container_id=cont.id, company_id=company.id, forwarder_id=fwd.id,
                              status=TransportOrderStatus.WYKONANE,
                              pickup_date=d, delivery_date=d + datetime.timedelta(days=6)))
        db.add(TransportOrder(container_id=cont.id, company_id=company.id, forwarder_id=fwd.id,
                              status=TransportOrderStatus.ODRZUCONE))
        db.commit()
    finally:
        db.close()


def test_forwarding_kpi(client):
    hdr = login(client)
    _seed()
    resp = client.get("/api/transport-orders/kpi", headers=hdr)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 3
    assert data["by_status"]["WYKONANE"] == 2
    assert data["by_status"]["ODRZUCONE"] == 1
    assert data["avg_realization_days"] == 5.0        # (4 + 6) / 2
    assert data["rejection_rate"] == 33.3             # 1/3
    assert data["top_forwarders"][0] == {"name": "Spedytor X", "count": 3}


def test_forwarding_kpi_requires_auth(client):
    assert client.get("/api/transport-orders/kpi").status_code == 401

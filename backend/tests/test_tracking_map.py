"""Mapa trackingu (/api/tracking/map) — wydzielone z test_tracking.py (limit 500 linii)."""
import datetime

from app.database import SessionLocal
from app.models import Container, ContainerStatus
from tests.test_tracking import _borealis_id


def test_map_reports_counts(client, admin_headers):
    body = client.get("/api/tracking/map", headers=admin_headers).json()
    assert "tracked" in body and "total" in body
    assert "configured" not in body and "last_sync" not in body


def test_map_only_lists_containers_with_rf(client, admin_headers):
    # „możliwy do śledzenia" = ma numer RF (id śledzenia armatora) i nie jest
    # zrealizowany. Kontroluje regresję „setki śledzonych znikąd zamiast ~10".
    with SessionLocal() as db:
        company_id = _borealis_id(db)
        db.add(Container(container_no="MSDU1111111", company_id=company_id,
                         status=ContainerStatus.W_PORCIE, rf_number="6200000001"))  # RF → śledzony
        db.add(Container(container_no="MSDU2222222", company_id=company_id,
                         status=ContainerStatus.W_TRANSPORCIE))                      # brak RF → nie
        db.add(Container(container_no="MSDU3333333", company_id=company_id,
                         status=ContainerStatus.W_PORCIE, rf_number="   "))          # puste RF → nie
        db.add(Container(container_no="MSDU4444444", company_id=company_id,
                         status=ContainerStatus.ZREALIZOWANY, rf_number="6200000002"))  # RF, ale zrealizowany → nie
        db.commit()

    body = client.get("/api/tracking/map", headers=admin_headers).json()
    assert body["total"] == 1  # tylko RF + aktywny


def test_map_ignores_estimated_and_future_events(client, admin_headers):
    # przewoźnik podaje prognozowany ARRIVE w porcie docelowym z datą w przyszłości —
    # kontener w rejsie nie może „wylądować" na mapie w Gdańsku przed czasem,
    # a ETD ma iść z faktycznego DEPART, nie z prognozy
    from app.models import TrackingEvent, utcnow
    now = utcnow()
    with SessionLocal() as db:
        c = Container(container_no="MSDU5555555", company_id=_borealis_id(db),
                      status=ContainerStatus.W_TRANSPORCIE, rf_number="6200000005")
        db.add(c)
        db.flush()
        db.add_all([
            TrackingEvent(container_id=c.id, event_code="DEPART", location="SHANGHAI",
                          description="Prognoza wyjścia", is_estimated=True,
                          occurred_at=now - datetime.timedelta(days=12)),
            TrackingEvent(container_id=c.id, event_code="DEPART", location="SHANGHAI",
                          description="Wyjście z portu",
                          occurred_at=now - datetime.timedelta(days=10)),
            TrackingEvent(container_id=c.id, event_code="ARRIVE", location="GDANSK",
                          description="Prognoza przybycia", is_estimated=True,
                          occurred_at=now + datetime.timedelta(days=20)),
        ])
        db.commit()

    body = client.get("/api/tracking/map", headers=admin_headers).json()
    entry = next(e for e in body["points"] + body["unlocated"]
                 if e["container_no"] == "MSDU5555555")
    assert entry["location"] == "SHANGHAI"
    assert entry["event"] == "Wyjście z portu"
    assert entry["etd"] == (now - datetime.timedelta(days=10)).date().isoformat()

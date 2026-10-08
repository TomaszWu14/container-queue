"""Tracking: pola trackingu na kontenerze, konfiguracja UI, sygnał „utknął"."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Container, today_pl

VALID_NO = "MSDU0806613"


def _create_container(client, headers, **extra):
    companies = client.get("/api/companies", headers=headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    body = {"container_no": VALID_NO, "company_id": borealis,
            "status": "W_TRANSPORCIE", **extra}
    response = client.post("/api/containers", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_ui_config_buffer(client, admin_headers):
    assert client.get("/api/ui-config", headers=admin_headers).json() == {
        "warehouse_eta_buffer_days": 3, "max_upload_mb": 25}
    client.put("/api/settings", headers=admin_headers, json={
        "reminder_days": "15,30", "insurer_email": "", "complaint_prefix": "REK",
        "docs_reminder_days": "7", "forecast_alert_days": "7",
        "warehouse_eta_buffer_days": "5"})
    assert client.get("/api/ui-config", headers=admin_headers).json()[
        "warehouse_eta_buffer_days"] == 5


def _borealis_id(db):
    from app.models import Company
    return db.scalar(select(Company).where(Company.code == "BOREALIS")).id


def test_tracking_error_cleared_on_status_leaving_tracked(client, admin_headers):
    created = _create_container(client, admin_headers)
    with SessionLocal() as db:
        c = db.get(Container, created["id"])
        c.tracking_error = "HTTP 401: brak"
        db.commit()
    # zmiana statusu na nieśledzony (DOSTARCZONY) kasuje błąd
    resp = client.post(f"/api/containers/{created['id']}/status",
                       headers=admin_headers, json={"status": "DOSTARCZONY"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tracking_error"] == ""


def test_tracking_error_cleared_on_container_no_change(client, admin_headers):
    created = _create_container(client, admin_headers)
    with SessionLocal() as db:
        c = db.get(Container, created["id"])
        c.tracking_error = "HTTP 401: brak"
        db.commit()
    resp = client.patch(f"/api/containers/{created['id']}",
                       headers=admin_headers, json={"container_no": "MSKU0000006"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tracking_error"] == ""


def test_is_stuck_osobny_sygnal_od_opoznienia():
    """W porcie po ETA bez awizacji = „utknął"; to NIE to samo co is_delayed."""
    import datetime as dt

    from app.models import Container, ContainerStatus

    today = today_pl()
    stuck = Container(status=ContainerStatus.W_PORCIE,
                      eta=today - dt.timedelta(days=Container.STUCK_AFTER_DAYS + 1))
    assert stuck.is_stuck is True

    # świeżo przypłynięty w karencji — rozładunek i papiery trwają, to nie utknięcie
    fresh = Container(status=ContainerStatus.W_PORCIE,
                      eta=today - dt.timedelta(days=Container.STUCK_AFTER_DAYS - 1))
    assert fresh.is_stuck is False

    # awizowany = ktoś go już pilnuje
    notified = Container(status=ContainerStatus.W_PORCIE,
                         eta=today - dt.timedelta(days=30),
                         notify_date=today + dt.timedelta(days=2))
    assert notified.is_stuck is False

    # opóźniony w transporcie to nie „utknął" — inny sygnał, inna akcja
    late = Container(status=ContainerStatus.W_TRANSPORCIE,
                     eta=today - dt.timedelta(days=30))
    assert late.is_delayed is True
    assert late.is_stuck is False

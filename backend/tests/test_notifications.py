import datetime
import io

import openpyxl

from app.config import settings
from app.database import SessionLocal
from app.models import Container, today_pl
from app.notifications import check_demurrage_alerts, demurrage_deadline
from tests.conftest import forwarder, login

VALID_NO = "MSDU0806613"


def _setup(client, admin_headers):
    companies = client.get("/api/companies", headers=admin_headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.borealis", "password": "haslo123", "role": "logistics",
        "company_id": borealis, "email": "logistyka@borealis.example"})
    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.spedalfa", "password": "haslo123", "role": "forwarder",
        "forwarder_id": spedalfa["id"]})
    container = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis,
        "forwarder_id": spedalfa["id"]}).json()
    return {"borealis": borealis, "spedalfa": spedalfa, "container": container}


def _unread(client, headers):
    return client.get("/api/notifications/unread-count", headers=headers).json()["count"]


def test_message_and_order_notifications(client, admin_headers):
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.borealis", "haslo123")
    forwarder = login(client, "sped.spedalfa", "haslo123")
    cid = ctx["container"]["id"]

    assert _unread(client, forwarder) == 0
    client.post(f"/api/containers/{cid}/messages", headers=logistics,
                json={"body": "Proszę o odbiór we wtorek."})
    # spedytor dostał, autor nie
    assert _unread(client, forwarder) == 1
    assert _unread(client, logistics) == 0

    client.post("/api/transport-orders", headers=logistics, json={"container_id": cid})
    assert _unread(client, forwarder) == 2

    orders = client.get("/api/transport-orders", headers=forwarder).json()
    client.post(f"/api/transport-orders/{orders[0]['id']}/status",
                headers=forwarder, json={"status": "ZAAKCEPTOWANE", "reason": ""})
    assert _unread(client, logistics) == 1  # logistyka powiadomiona o akceptacji

    notifications = client.get("/api/notifications", headers=forwarder).json()
    assert {n["kind"] for n in notifications} == {"message", "order"}

    client.post("/api/notifications/read", headers=forwarder)
    assert _unread(client, forwarder) == 0


def test_demurrage_alert(client, admin_headers):
    ctx = _setup(client, admin_headers)
    logistics = login(client, "log.borealis", "haslo123")
    cid = ctx["container"]["id"]
    # ETA 10 dni temu, 12 dni wolnych → deadline za 2 dni (alert przy progu 3)
    eta = today_pl() - datetime.timedelta(days=10)
    client.patch(f"/api/containers/{cid}", headers=admin_headers,
                 json={"eta": eta.isoformat(), "demurrage_free_days": 12})

    with SessionLocal() as db:
        container = db.get(Container, cid)
        assert demurrage_deadline(db, container) == eta + datetime.timedelta(days=12)
        sent = check_demurrage_alerts(db)
        assert sent > 0
        # drugi przebieg tego samego dnia — bez duplikatów
        assert check_demurrage_alerts(db) == 0

    notifications = client.get("/api/notifications", headers=logistics).json()
    assert any(n["kind"] == "demurrage" and VALID_NO in n["title"] for n in notifications)


def test_no_demurrage_alert_when_far(client, admin_headers):
    ctx = _setup(client, admin_headers)
    cid = ctx["container"]["id"]
    eta = today_pl()
    client.patch(f"/api/containers/{cid}", headers=admin_headers,
                 json={"eta": eta.isoformat(),
                       "demurrage_free_days": settings.demurrage_alert_days + 10})
    with SessionLocal() as db:
        assert check_demurrage_alerts(db) == 0


def test_export_xlsx(client, admin_headers):
    ctx = _setup(client, admin_headers)
    del ctx
    response = client.get("/api/containers/export/xlsx", headers=admin_headers)
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0][1] == "NR KONTENERA"
    assert any(row[1] == VALID_NO for row in rows[1:])

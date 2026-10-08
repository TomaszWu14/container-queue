import datetime

from app.database import SessionLocal
from app.models import Container, Notification, pl_midnight_utc, today_pl
from app.notifications import check_weekly_digest_alerts
from tests.conftest import login

VALID_NO = "MSDU0806613"


def _setup(client, admin_headers):
    companies = client.get("/api/companies", headers=admin_headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.watch", "password": "haslo123", "role": "logistics",
        "company_id": borealis, "email": "watch@borealis.example"})
    container = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis}).json()
    return {"borealis": borealis, "container": container}


def test_watch_only_notifications_filters_non_watchers(client, admin_headers):
    ctx = _setup(client, admin_headers)
    cid = ctx["container"]["id"]
    headers = login(client, "log.watch", "haslo123")

    # włącz przełącznik przez self-update endpoint
    resp = client.patch("/api/auth/me/settings", headers=headers,
                        json={"watch_only_notifications": True})
    assert resp.status_code == 200
    assert resp.json()["watch_only_notifications"] is True

    def unread():
        return client.get("/api/notifications/unread-count", headers=headers).json()["count"]

    # nie obserwuje kontenera -> nie dostaje powiadomienia o nim
    client.post(f"/api/containers/{cid}/messages", headers=admin_headers,
               json={"body": "hej"})
    assert unread() == 0

    # zaczyna obserwować -> odtąd dostaje
    client.post(f"/api/containers/{cid}/watch", headers=headers)
    client.post(f"/api/containers/{cid}/messages", headers=admin_headers,
               json={"body": "hej ponownie"})
    assert unread() == 1


def test_weekly_digest_sends_and_dedupes(client, admin_headers):
    ctx = _setup(client, admin_headers)
    cid = ctx["container"]["id"]
    client.post("/api/users", headers=admin_headers, json={
        "login": "zak.purch", "password": "haslo123", "role": "purchasing",
        "company_id": ctx["borealis"], "email": "zak@borealis.example"})
    purch_headers = login(client, "zak.purch", "haslo123")
    client.post(f"/api/containers/{cid}/watch", headers=purch_headers)

    with SessionLocal() as db:
        offset = (0 - today_pl().weekday()) % 7
        monday = today_pl() + datetime.timedelta(days=offset)
        # 8:30 czasu PL (okno digestu) jako naiwny UTC — niezależnie od DST
        monday_6am = pl_midnight_utc(monday) + datetime.timedelta(hours=8, minutes=30)

        container = db.get(Container, cid)
        container.notify_date = monday + datetime.timedelta(days=2)
        db.commit()

        sent = check_weekly_digest_alerts(db, now=monday_6am)
        assert sent == 1
        # created_at bije prawdziwym utcnow(), nie fałszywym `now` testu — dociągamy
        # do okna poniedziałku, żeby dedup drugiego wywołania miał co znaleźć.
        db.query(Notification).filter(Notification.kind == "weekly_digest").update(
            {"created_at": monday_6am})
        db.commit()

        # drugie wywołanie tego samego dnia -> deduplikacja, nic nowego
        sent_again = check_weekly_digest_alerts(db, now=monday_6am)
        assert sent_again == 0

        count = db.query(Notification).filter(
            Notification.kind == "weekly_digest").count()
        assert count == 1


def test_weekly_digest_outside_window_noop(client, admin_headers):
    with SessionLocal() as db:
        tuesday = datetime.datetime(2026, 9, 8, 6, 30)  # 2026-09-08 to wtorek
        assert check_weekly_digest_alerts(db, now=tuesday) == 0

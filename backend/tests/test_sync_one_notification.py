"""Sync z Excela wysyła JEDNO powiadomienie na przebieg (dawniej jedno na kontener —
duży sync zalewał pocztę/Teams/n8n setkami wiadomości); audyt per kontener zostaje."""
import datetime

from app.database import SessionLocal
from app.models import AuditLog
from tests.test_sync import _xlsx

NUMBERS = ["MSKU7026487", "MSKU7026492", "MSKU7026506", "MSKU7026511", "MSKU7026532"]
URL = "/api/import/queue-sync?company_code=BOREALIS&dry_run=false"


def _file(day):
    return _xlsx([["ACME", "MAERSK", datetime.datetime(2026, 9, day), "kolej", no, "", ""]
                  for no in NUMBERS])


def test_sync_of_five_containers_sends_one_notification(client, admin_headers, monkeypatch):
    import app.importers.queue_notify as qn
    calls = []
    real = qn.notify
    monkeypatch.setattr(qn, "notify", lambda *a, **kw: calls.append(kw) or real(*a, **kw))

    r = client.post(URL, headers=admin_headers, files={"file": ("q.xlsx", _file(1))})
    assert r.status_code == 200, r.text
    assert r.json()["changed"] == 5 and len(calls) == 1
    assert "5 kontenerów" in calls[0]["title"] and "5 nowych" in calls[0]["title"]

    calls.clear()
    r = client.post(URL, headers=admin_headers, files={"file": ("q.xlsx", _file(9))})
    assert r.json()["changed"] == 5 and len(calls) == 1
    assert calls[0]["kind"] == "excel-sync" and calls[0]["container_id"] is None
    assert all(f"{no}: eta" in calls[0]["body"] for no in NUMBERS)
    db = SessionLocal()
    try:                                   # audyt nadal per kontener
        assert db.query(AuditLog).filter(AuditLog.field == "eta",
                                         AuditLog.note == "sync z Excela").count() >= 5
    finally:
        db.close()


def test_watch_only_user_gets_only_watched_containers(client, admin_headers):
    """Podsumowanie bez linku do kontenera omijało filtr „tylko obserwowane" — user z flagą
    dostawał zmiany WSZYSTKICH kontenerów. Teraz: tylko jego obserwowane (albo nic)."""
    from app.models import Container, Notification, User
    from tests.conftest import login
    borealis = next(c["id"] for c in client.get("/api/companies", headers=admin_headers).json()
                  if c["code"] == "BOREALIS")
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.gwiazdka", "password": "haslo123", "role": "logistics",
        "company_id": borealis})
    headers = login(client, "log.gwiazdka", "haslo123")
    client.patch("/api/auth/me/settings", headers=headers, json={"watch_only_notifications": True})

    def sync_notes(day):
        r = client.post(URL, headers=admin_headers, files={"file": ("q.xlsx", _file(day))})
        assert r.json()["changed"] == 5, r.text
        with SessionLocal() as db:
            uid = db.query(User).filter(User.login == "log.gwiazdka").one().id
            return [(n.title, n.body) for n in db.query(Notification).filter(
                Notification.user_id == uid, Notification.kind == "excel-sync")]

    assert sync_notes(1) == []                 # nic nie obserwuje → nic nie dostaje
    with SessionLocal() as db:
        ids = {c.container_no: c.id for c in db.query(Container).filter(
            Container.container_no.in_(NUMBERS))}
    for no in NUMBERS[:2]:
        client.post(f"/api/containers/{ids[no]}/watch", headers=headers)
    notes = sync_notes(9)
    assert len(notes) == 1
    title, body = notes[0]
    assert "2 kontenerów" in title
    assert all(no in body for no in NUMBERS[:2])
    assert not any(no in body for no in NUMBERS[2:])

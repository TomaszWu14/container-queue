"""Zmiana numeru kontenera (np. poprawka literówki) zeruje dane trackingu starego numeru."""
import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.audit import record
from app.models import Container, ContainerStatus, TrackingEvent, utcnow

OLD_NO, NEW_NO = "MSDU0806613", "MSKU7026492"


def _tracked_container(client, headers, status="ZAPOWIEDZIANY") -> int:
    companies = client.get("/api/companies", headers=headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    resp = client.post("/api/containers", headers=headers,
                       json={"container_no": OLD_NO, "company_id": borealis, "status": status})
    assert resp.status_code == 201, resp.text
    cid = resp.json()["id"]
    when = datetime.datetime(2026, 7, 1, 8, 0)
    # dane naniesione historycznie przez tracking (audyt z note "tracking:*")
    with SessionLocal() as db:
        c = db.get(Container, cid)
        note = "tracking:historyczny"
        record(db, entity_type="containers", entity_id=cid, field="etd",
               old_value=None, new_value=when.date(), user=None, note=note)
        record(db, entity_type="containers", entity_id=cid, field="status",
               old_value=c.status.value, new_value=ContainerStatus.W_PORCIE.value,
               user=None, note=note)
        record(db, entity_type="containers", entity_id=cid, field="vessel",
               old_value="", new_value="MV STARY", user=None, note=note)
        c.etd, c.status, c.vessel = when.date(), ContainerStatus.W_PORCIE, "MV STARY"
        c.tracked_at = utcnow()
        db.add(TrackingEvent(container_id=cid, event_code="DEPART", location="SHANGHAI",
                             description="Wyjście z portu", vessel="MV STARY",
                             occurred_at=when, source="historyczny"))
        db.commit()
    return cid


def test_container_no_change_drops_old_tracking(client, admin_headers):
    cid = _tracked_container(client, admin_headers)
    with SessionLocal() as db:
        c = db.get(Container, cid)
        assert c.status == ContainerStatus.W_PORCIE and c.etd and c.tracked_at

    resp = client.patch(f"/api/containers/{cid}", headers=admin_headers,
                        json={"container_no": NEW_NO})
    assert resp.status_code == 200, resp.text

    with SessionLocal() as db:
        c = db.get(Container, cid)
        assert db.scalar(select(TrackingEvent).where(TrackingEvent.container_id == cid)) is None
        # pola naniesione przez tracking wracają do stanu sprzed trackingu
        assert c.etd is None
        assert c.status == ContainerStatus.ZAPOWIEDZIANY
        assert c.vessel == ""
        assert c.tracked_at is None
    history = client.get(f"/api/containers/{cid}/history", headers=admin_headers).json()
    assert any(h["field"] == "tracking_events" for h in history)


def test_manual_values_survive_number_change(client, admin_headers):
    """Status ustawiony ręcznie PO trackingu nie jest cofany — to już nie dane trackingu."""
    cid = _tracked_container(client, admin_headers)
    assert client.post(f"/api/containers/{cid}/status", headers=admin_headers,
                       json={"status": "W_TRANSPORCIE", "note": "korekta"}).status_code == 200
    client.patch(f"/api/containers/{cid}", headers=admin_headers,
                 json={"container_no": NEW_NO})
    with SessionLocal() as db:
        assert db.get(Container, cid).status == ContainerStatus.W_TRANSPORCIE


def test_same_number_keeps_tracking(client, admin_headers):
    cid = _tracked_container(client, admin_headers)
    client.patch(f"/api/containers/{cid}", headers=admin_headers,
                 json={"container_no": OLD_NO})
    with SessionLocal() as db:
        assert db.scalar(select(TrackingEvent).where(TrackingEvent.container_id == cid))

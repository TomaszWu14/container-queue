"""GDPR-001 (audyt 2026-09-28, N-12): dane kierowcy nie zostają jawnie w audycie,
powiadomieniach ani historii SMS po anonimizacji."""
import datetime

from app import avizo_workflow as wf
from app.database import SessionLocal
from app.models import (AuditLog, AvizoItem, AvizoRequest, AvizoStatus, Company, Container,
                        Forwarder, Notification, SmsMessage, User, utcnow)
from app.routers import forwarding
from app.sms import mock_outbox
from app.config import settings

PII = ("Jan Kowalski", "WX12345", "WX9999", "600100200")


def _no_pii(text: str | None) -> bool:
    return not any(p in (text or "") for p in PII)


def _new_container(client, admin_headers, no):
    companies = client.get("/api/companies", headers=admin_headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    return client.post("/api/containers", headers=admin_headers,
                       json={"container_no": no, "company_id": borealis}).json()


def test_driver_data_masked_in_audit_and_notification(client, admin_headers, monkeypatch):
    sent = []
    monkeypatch.setattr(forwarding, "notify", lambda db, users, **kw: sent.append(kw))
    c = _new_container(client, admin_headers, "MSDU0806613")
    r = client.patch(f"/api/containers/{c['id']}/driver", headers=admin_headers, json={
        "driver_name": "Jan Kowalski", "driver_id_no": "", "truck_no": "WX12345",
        "trailer_no": "WX9999", "driver_phone": "600100200"})
    assert r.status_code == 200
    assert sent and sent[0]["kind"] == "driver"
    assert _no_pii(sent[0]["title"]) and _no_pii(sent[0]["body"])
    with SessionLocal() as db:
        rows = db.query(AuditLog).filter_by(entity_type="containers", entity_id=c["id"]).all()
        assert {r.field for r in rows} >= {"driver_name", "truck_no", "trailer_no"}
        assert all(_no_pii(r.old_value) and _no_pii(r.new_value) for r in rows)


def test_driver_sms_audit_note_without_phone(client, admin_headers):
    settings.sms_provider = "mock"
    mock_outbox.clear()
    c = _new_container(client, admin_headers, "MSDU0806613")
    client.patch(f"/api/containers/{c['id']}/driver", headers=admin_headers, json={
        "driver_name": "Jan Kowalski", "driver_id_no": "", "truck_no": "",
        "trailer_no": "", "driver_phone": "600100200"})
    assert client.post(f"/api/containers/{c['id']}/driver-sms",
                       headers=admin_headers).status_code == 200
    with SessionLocal() as db:
        row = db.query(AuditLog).filter_by(entity_id=c["id"], field="driver_sms").one()
        assert _no_pii(row.note)


def test_maintenance_purges_notification_and_sms_copies(client):
    with SessionLocal() as db:
        c = Container(container_no="MNTU0000011", company_id=db.query(Company).first().id,
                      driver_name="Jan Kowalski", driver_phone="600100200", truck_no="WX12345")
        db.add(c)
        db.flush()
        req = AvizoRequest(token=wf.hash_token("gdpr-001"), status=AvizoStatus.CLOSED,
                           company_id=c.company_id, forwarder_id=db.query(Forwarder).first().id,
                           closed_at=utcnow() - datetime.timedelta(days=91))
        db.add(req)
        db.flush()
        db.add(AvizoItem(request_id=req.id, container_id=c.id))
        uid = db.query(User).first().id
        db.add(Notification(user_id=uid, kind="driver", title="Dane kierowcy",
                            body="Jan Kowalski / WX12345 / 600100200", container_id=c.id))
        db.add(SmsMessage(container_id=c.id, phone="600100200", body="TIMPORYE: dostawa"))
        db.commit()
        cid = c.id

    with SessionLocal() as db:
        assert wf.run_maintenance(db)["anonymized"] == 1
    with SessionLocal() as db:
        assert all(_no_pii(n.body) for n in db.query(Notification).filter_by(container_id=cid))
        sms = db.query(SmsMessage).filter_by(container_id=cid).one()
        assert (sms.phone, sms.body) == ("", "")
        rows = db.query(AuditLog).filter_by(entity_type="containers", entity_id=cid).all()
        assert all(_no_pii(r.old_value) and _no_pii(r.new_value) for r in rows)

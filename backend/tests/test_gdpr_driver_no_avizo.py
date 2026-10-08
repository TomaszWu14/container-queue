"""GDPR-002 (audyt 2026-09-28): dane kierowcy kontenera ZREALIZOWANEGO bez awizacji
też są anonimizowane po DRIVER_DATA_RETENTION_DAYS od realizacji."""
import datetime

from app import avizo_workflow as wf
from app.config import settings
from app.database import SessionLocal
from app.models import (Company, Container, ContainerStatus, Notification, SmsMessage, User,
                        utcnow)

DRIVER = {"driver_name": "Jan Kowalski", "driver_id_no": "ABC123", "truck_no": "WX12345",
          "trailer_no": "WX9999", "driver_phone": "600100200"}


def _container(db, no, days_ago):
    c = Container(container_no=no, company_id=db.query(Company).first().id,
                  status=ContainerStatus.ZREALIZOWANY,
                  completed_at=utcnow() - datetime.timedelta(days=days_ago), **DRIVER)
    db.add(c)
    db.flush()
    return c


def test_maintenance_anonymizes_finished_container_without_avizo(client):
    old_days = settings.driver_data_retention_days + 10
    with SessionLocal() as db:
        old = _container(db, "MNTU0000022", old_days)
        fresh = _container(db, "MNTU0000033", 1)
        db.add(Notification(user_id=db.query(User).first().id, kind="driver",
                            title="Dane kierowcy", body="Jan Kowalski", container_id=old.id))
        db.add(SmsMessage(container_id=old.id, phone="600100200", body="TIMPORYE: dostawa"))
        db.commit()
        old_id, fresh_id = old.id, fresh.id

    with SessionLocal() as db:
        assert wf.run_maintenance(db)["anonymized"] == 1
    with SessionLocal() as db:
        old, fresh = db.get(Container, old_id), db.get(Container, fresh_id)
        assert all(getattr(old, f) == "" for f in wf.DRIVER_FIELDS)
        assert all(getattr(fresh, f) == v for f, v in DRIVER.items())
        assert db.query(Notification).filter_by(container_id=old_id).one().body == ""
        sms = db.query(SmsMessage).filter_by(container_id=old_id).one()
        assert (sms.phone, sms.body) == ("", "")
    with SessionLocal() as db:   # idempotentne
        assert wf.run_maintenance(db)["anonymized"] == 0

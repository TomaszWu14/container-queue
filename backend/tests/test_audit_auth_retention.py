"""GDPR-004: retencja logu logowań w audit_log; biznesowa historia zostaje."""
import datetime

from sqlalchemy import select

from app import applog
from app.models import AuditLog, utcnow


def test_purge_auth_audit_keeps_fresh_auth_and_business_history(db_session):
    old = utcnow() - datetime.timedelta(days=91)
    fresh = utcnow() - datetime.timedelta(days=1)
    for et, field, at in (("auth", "login_failed", old), ("auth", "login", fresh),
                          ("container", "status", old)):
        db_session.add(AuditLog(entity_type=et, entity_id=1, field=field, new_value="x",
                                note="z 10.0.0.1", created_at=at))
    db_session.commit()
    assert applog.purge_auth_audit(db_session) == 1
    left = {(r.entity_type, r.field) for r in db_session.scalars(select(AuditLog))}
    assert left == {("auth", "login"), ("container", "status")}


def test_failed_login_unknown_user_does_not_store_full_input(client, db_session):
    secret = "MojeTajneHaslo123!"
    r = client.post("/api/auth/login", data={"username": secret, "password": "x"})
    assert r.status_code == 401
    row = db_session.scalars(select(AuditLog).where(AuditLog.field == "login_failed")).one()
    assert secret not in (row.new_value or "")
    assert row.new_value.startswith("Mo")

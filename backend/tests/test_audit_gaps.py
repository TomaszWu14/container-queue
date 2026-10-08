"""OBS-003: zapisy, które wcześniej omijały ślad audytowy (reguły powiadomień,
przyjęcia towaru, publiczny link kontenera) — każdy zostawia wpis z autorem."""
import pytest
from sqlalchemy import select

from app.models import AuditLog, User

from .test_goods_receipts import _seed


def _rules(client, hdr, cid):
    r = client.put("/api/notifications/rules", headers=hdr, json=[
        {"kind": "message", "role": "logistics", "channel": "email", "enabled": False}])
    assert r.status_code == 200, r.text
    return "notification_rules", "disabled", "message/logistics/email"


def _receipt_put(client, hdr, cid):
    r = client.put(f"/api/containers/{cid}/receipts", headers=hdr,
                   json={"order_number": "4500000001", "position": "10", "qty_received": "70"})
    assert r.status_code == 200, r.text
    return "goods_receipt_lines", "qty_received", "70"


def _receipt_delete(client, hdr, cid):
    rid = client.put(f"/api/containers/{cid}/receipts", headers=hdr,
                     json={"order_number": "4500000001", "position": "10",
                           "qty_received": "5"}).json()["id"]
    assert client.delete(f"/api/containers/{cid}/receipts/{rid}",
                         headers=hdr).status_code == 204
    return "goods_receipt_lines", "delete", None


@pytest.mark.parametrize("action", [_rules, _receipt_put, _receipt_delete])
def test_write_leaves_audit_entry(client, db_session, admin_headers, action):
    _, container = _seed(db_session)
    db_session.commit()
    entity_type, field, new_value = action(client, admin_headers, container.id)
    db_session.expire_all()
    rows = db_session.scalars(select(AuditLog).where(
        AuditLog.entity_type == entity_type, AuditLog.field == field)).all()
    assert rows, f"brak wpisu audytu {entity_type}.{field}"
    admin = db_session.scalar(select(User).where(User.login == "admin"))
    assert rows[-1].user_id == admin.id
    assert rows[-1].new_value == new_value


def test_rules_unchanged_no_audit_noise(client, db_session, admin_headers):
    for _ in range(2):
        _rules(client, admin_headers, None)
    assert len(db_session.scalars(select(AuditLog).where(
        AuditLog.entity_type == "notification_rules")).all()) == 1

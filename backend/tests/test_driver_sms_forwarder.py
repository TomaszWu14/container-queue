"""S10 (audyt UI 2026-09-27): spedytor wysyła SMS do kierowcy SWOJEGO kontenera,
max 3 na kontener w dobie kalendarzowej (czas PL); logistyka/admin bez limitu; cudzy spedytor → 404."""
import datetime

from app.models import AuditLog, pl_midnight_utc
from app.sms import mock_outbox
from tests.conftest import forwarder, login
from tests.test_driver_link import _setup


def _forwarder_user(client, admin_headers, name, fwd_id):
    assert client.post("/api/users", headers=admin_headers, json={
        "login": name, "password": "haslo123", "role": "forwarder",
        "forwarder_id": fwd_id, "email": f"{name}@example.com"}).status_code == 201
    return login(client, name, "haslo123")


def test_forwarder_sms_own_container_with_daily_limit(client, admin_headers, db_session):
    cid = _setup(client, admin_headers)["id"]
    own, other = forwarder(client, admin_headers, "SMS-SPEDALFA"), forwarder(client, admin_headers, "SMS-TOLL")
    assert client.patch(f"/api/containers/{cid}", headers=admin_headers,
                        json={"forwarder_id": own["id"]}).status_code == 200
    own_h = _forwarder_user(client, admin_headers, "sms.own", own["id"])
    other_h = _forwarder_user(client, admin_headers, "sms.other", other["id"])
    url = f"/api/containers/{cid}/driver-sms"

    # SMS logistyki nie zjada limitu spedytora
    assert client.post(url, headers=admin_headers).json()["status"] == "sent"
    for _ in range(3):
        r = client.post(url, headers=own_h)
        assert r.status_code == 200 and r.json()["status"] == "sent", r.text
    blocked = client.post(url, headers=own_h)
    assert blocked.status_code == 429 and "dzisiaj" in blocked.json()["detail"]
    assert len(mock_outbox) == 4
    # logistyka/admin bez limitu
    assert client.post(url, headers=admin_headers).json()["status"] == "sent"
    assert len(client.get(url, headers=own_h).json()["messages"]) == 5

    # cudzy spedytor: ani historia, ani wysyłka (404 z check_container_access)
    assert client.get(url, headers=other_h).status_code == 404
    assert client.post(url, headers=other_h).status_code == 404

    # doba kalendarzowa: SMS-y sprzed polskiej północy nie liczą się do dzisiejszego limitu
    db_session.query(AuditLog).filter(AuditLog.field == "driver_sms").update(
        {AuditLog.created_at: pl_midnight_utc() - datetime.timedelta(minutes=1)})
    db_session.commit()
    assert client.post(url, headers=own_h).json()["status"] == "sent"

"""COST-003: globalny dzienny limit SMS (koszt bramki) z alertem adminów przy 80% i 100%
oraz ograniczona liczba prób auto-przypomnienia na kontener w dobie."""
import datetime

from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.models import Notification, SmsMessage, today_pl
from app.routers import driver
from app.routers.driver import send_tomorrow_sms
from app.sms import SmsError, mock_outbox
from tests.test_driver_link import _setup

def _after_reminder_hour() -> datetime.datetime:
    """14:00 UTC „dziś” wg PL — liczone przy użyciu, nie przy imporcie: suita zebrana przed
    północą PL a wykonana po niej dawała wczorajszą godzinę przy dzisiejszym kontenerze."""
    return datetime.datetime.combine(today_pl(), datetime.time(14, 0))


def _alerts(kind: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(Notification.id)).where(Notification.kind == kind))


def _attempts(container_id: int) -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(SmsMessage.id)).where(
            SmsMessage.container_id == container_id))


def test_manual_sms_over_daily_cap_is_429_and_alerts_admins_once(client, admin_headers,
                                                                   monkeypatch):
    cid = _setup(client, admin_headers)["id"]
    monkeypatch.setattr(settings, "sms_daily_cap", 5)
    url = f"/api/containers/{cid}/driver-sms"
    for _ in range(3):
        assert client.post(url, headers=admin_headers).json()["status"] == "sent"
    assert _alerts("sms_budget_warning") == 0
    # 4. próba = 80% limitu → ostrzeżenie (raz)
    assert client.post(url, headers=admin_headers).json()["status"] == "sent"
    warned = _alerts("sms_budget_warning")
    assert warned >= 1
    assert client.post(url, headers=admin_headers).json()["status"] == "sent"
    assert _alerts("sms_budget_warning") == warned
    # limit wyczerpany: 429, nic nie poszło do bramki, alert raz na dobę
    for _ in range(2):
        blocked = client.post(url, headers=admin_headers)
        assert blocked.status_code == 429 and "limit" in blocked.json()["detail"].lower()
    assert len(mock_outbox) == 5 and _attempts(cid) == 5
    assert _alerts("sms_budget_exceeded") == warned


def test_zero_cap_means_no_global_limit(client, admin_headers, monkeypatch):
    cid = _setup(client, admin_headers)["id"]
    monkeypatch.setattr(settings, "sms_daily_cap", 0)
    for _ in range(4):
        assert client.post(f"/api/containers/{cid}/driver-sms",
                           headers=admin_headers).status_code == 200
    assert _alerts("sms_budget_warning") == 0 and _alerts("sms_budget_exceeded") == 0


def test_failed_auto_reminder_retried_at_most_n_times_a_day(client, admin_headers, monkeypatch):
    cid = _setup(client, admin_headers)["id"]
    monkeypatch.setattr(settings, "sms_auto_max_attempts", 2)

    def _gateway_down(phone, body):
        raise SmsError("Błąd bramki SMS: 500")
    monkeypatch.setattr(driver, "send_sms", _gateway_down)
    for _ in range(5):   # pętla co 15 min — bez limitu każda próbowałaby od nowa
        assert send_tomorrow_sms(SessionLocal(), now=_after_reminder_hour()) == 0
    assert _attempts(cid) == 2


def test_auto_reminders_stop_at_daily_cap(client, admin_headers, monkeypatch):
    cid = _setup(client, admin_headers)["id"]
    monkeypatch.setattr(settings, "sms_daily_cap", 1)
    with SessionLocal() as db:   # dzisiejszy SMS innej dostawy zjada cały limit
        db.add(SmsMessage(container_id=cid, phone="600100200", body="x", status="sent",
                          delivery_date=today_pl() - datetime.timedelta(days=3)))
        db.commit()
    assert send_tomorrow_sms(SessionLocal(), now=_after_reminder_hour()) == 0
    assert _attempts(cid) == 1 and mock_outbox == []
    assert _alerts("sms_budget_exceeded") >= 1

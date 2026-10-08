"""Ustawienia SMS w panelu admina (decyzja 2026-09-28): włączenie, godzina PL, dni przed dostawą,
limit SMS spedytora. Wysyłka czyta ustawienia; godzina liczona w czasie polskim."""
import datetime
from types import SimpleNamespace

from sqlalchemy import select

from app.models import Company, Container, today_pl
from app.routers import driver



def test_admin_edits_sms_settings_and_others_cannot(client, admin_headers):
    assert client.get("/api/admin/sms-settings", headers=admin_headers).json()["reminder_hour"] == 15
    r = client.put("/api/admin/sms-settings", headers=admin_headers, json={
        "reminder_enabled": True, "reminder_hour": 9, "reminder_days_before": [1, 2, 2],
        "forwarder_daily_limit": 1})
    assert r.status_code == 200, r.text
    assert r.json()["reminder_days_before"] == [2, 1] and r.json()["forwarder_daily_limit"] == 1
    bad = client.put("/api/admin/sms-settings", headers=admin_headers, json={"reminder_hour": 25})
    assert bad.status_code == 422


def test_reminder_uses_panel_hour_and_days(client, admin_headers, db_session, monkeypatch):
    client.put("/api/admin/sms-settings", headers=admin_headers, json={
        "reminder_enabled": True, "reminder_hour": 9, "reminder_days_before": [2],
        "forwarder_daily_limit": 3})
    co = db_session.scalars(select(Company)).first()
    target = today_pl() + datetime.timedelta(days=2)
    db_session.add(Container(company_id=co.id, container_no="MSKU1234565", driver_phone="+48 000 000 001",
                             notify_date=target))
    db_session.commit()
    sent = []
    monkeypatch.setattr(driver, "sms_configured", lambda: True)
    monkeypatch.setattr(driver, "send_driver_sms",
                        lambda db, c: sent.append(c.container_no) or SimpleNamespace(status="sent"))
    pl_midnight = driver.pl_midnight_utc(today_pl())
    assert driver.send_tomorrow_sms(db_session, now=pl_midnight + datetime.timedelta(hours=8)) == 0
    assert driver.send_tomorrow_sms(db_session, now=pl_midnight + datetime.timedelta(hours=10)) == 1
    assert sent == ["MSKU1234565"]

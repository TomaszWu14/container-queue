"""Powiadomienia: kanały zewnętrzne dopiero po commicie, dedup alertu palet po redeployu,
doby PL w digestach, poranny digest spółki nie wychodzi tylko z powodu wspólnej sekcji DLT."""
import datetime

from sqlalchemy import select

from app import jobs, notification_digests, pallets_cache, powerbi
from app import notifications as n
from app.database import SessionLocal
from app.models import (Company, Container, Notification, Role, User, WatchedContainer,
                        pl_midnight_utc)


def _user(db, login, role=Role.logistics, company_code="BOREALIS"):
    company = db.scalar(select(Company).where(Company.code == company_code))
    user = User(login=login, hashed_password="x", role=role, company_id=company.id,
                email=f"{login}@example.com")
    db.add(user)
    db.commit()
    return user


def test_external_channels_only_after_commit(client, db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(n, "_send_email", lambda emails, t, b: sent.append(t))
    user = _user(db_session, "after.commit")
    n.notify(db_session, [user], kind="system", title="wycofane")
    db_session.rollback()
    assert sent == []
    db_session.commit()          # pusta transakcja — wycofane nie wraca
    assert sent == []
    n.notify(db_session, [user], kind="system", title="zapisane")
    assert sent == []            # przed commitem nic nie wychodzi
    db_session.commit()
    assert sent == ["zapisane"]


def test_pallet_urgent_dedup_after_restart(client, db_session, monkeypatch):
    _user(db_session, "acme.pal", company_code="ACME")
    monkeypatch.setattr(powerbi, "is_configured", lambda: True)
    monkeypatch.setattr(pallets_cache, "get_analysis",
                        lambda db: ([{"produkt": "DLT-1", "pilne": True}], None, None, None))
    assert jobs._run(n.check_pallet_urgent_alerts) >= 1
    assert jobs._run(n.check_pallet_urgent_alerts) == 0     # „redeploy” w oknie interwału
    with SessionLocal() as db:
        assert len(db.scalars(select(Notification).where(
            Notification.kind == "pallet_urgent")).all()) == 1


def test_daily_digest_uses_pl_day(client, db_session, monkeypatch):
    """Digest o 00:30 czasu PL (22:30 UTC poprzedniego dnia): „dziś” to data PL."""
    monkeypatch.setattr(n.settings, "digest_hour", 0)
    monkeypatch.setattr(notification_digests, "_dlt_low_stock_lines", lambda db: [])
    pl_day = datetime.date(2026, 11, 3)
    now = pl_midnight_utc(pl_day) + datetime.timedelta(minutes=30)
    assert now.date() != pl_day
    user = _user(db_session, "dig.pl")
    db_session.add(Container(container_no="PLDU0000001", company_id=user.company_id,
                             notify_date=pl_day))
    db_session.commit()
    assert notification_digests.check_daily_digest_alerts(db_session, now=now) >= 1
    body = db_session.scalar(select(Notification.body).where(
        Notification.user_id == user.id, Notification.kind == "daily_digest"))
    assert "Dzisiejsze dostawy (1)" in body and "PLDU0000001" in body


def test_daily_digest_not_sent_for_dlt_only(client, db_session, monkeypatch):
    """Sekcja DLT jest wspólna — spółka bez własnych pozycji nie dostaje codziennego maila."""
    monkeypatch.setattr(n.settings, "digest_hour", 7)
    monkeypatch.setattr(notification_digests, "_dlt_low_stock_lines",
                        lambda db: ["DLT-1 — zapas 2 dni"])
    user = _user(db_session, "dig.dlt", company_code="COBALT")
    db_session.query(Container).filter(Container.company_id == user.company_id).delete()
    db_session.commit()
    now = pl_midnight_utc(datetime.date(2026, 11, 3)) + datetime.timedelta(hours=7, minutes=5)
    notification_digests.check_daily_digest_alerts(db_session, now=now)
    assert db_session.scalar(select(Notification.id).where(
        Notification.user_id == user.id, Notification.kind == "daily_digest")) is None


def test_weekly_digest_window_in_pl_time_winter(client, db_session):
    """Zimą (CET) poniedziałek 8:30 PL = 7:30 UTC — dawne okno 6–7 UTC go gubiło."""
    monday = datetime.date(2026, 11, 2)
    now = pl_midnight_utc(monday) + datetime.timedelta(hours=8, minutes=30)
    user = _user(db_session, "zak.zima", role=Role.purchasing)
    c = Container(container_no="PLDU0000002", company_id=user.company_id,
                  notify_date=monday + datetime.timedelta(days=2))
    db_session.add(c)
    db_session.flush()
    db_session.add(WatchedContainer(user_id=user.id, container_id=c.id))
    db_session.commit()
    assert notification_digests.check_weekly_digest_alerts(db_session, now=now) == 1

"""Milestone'y trackingowe: przekroczone ETA i dryf ETA statku (AIS)."""
import datetime

from app.models import Notification, TrackedVessel
from app.notifications import check_tracking_alerts
from tests.conftest import login


def _make_container(client, headers, no, vessel="", eta=None):
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    payload = {"container_no": no, "company_id": company_id}
    if vessel:
        payload["vessel"] = vessel
    if eta:
        payload["eta"] = eta
    resp = client.post("/api/containers", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_eta_overdue_alert_fires_once_for_yesterday(client, db_session):
    headers = login(client)
    today = datetime.date(2026, 9, 10)
    _make_container(client, headers, "TGBU6784203", eta="2026-09-09")   # wczoraj
    _make_container(client, headers, "MSCU7654329", eta="2026-09-05")   # dawniej — poza oknem

    sent = check_tracking_alerts(db_session, today=today)
    assert sent > 0
    kinds = [n.kind for n in db_session.query(Notification).all()]
    assert "eta_overdue" in kinds
    titles = [n.title for n in db_session.query(Notification)
              .filter_by(kind="eta_overdue").all()]
    assert any("TGBU6784203" in t for t in titles)
    assert not any("MSCU7654321" in t for t in titles)   # tylko okno wczorajsze


def test_eta_drift_alert_dedups_per_day(client, db_session):
    headers = login(client)
    today = datetime.date(2026, 9, 10)
    _make_container(client, headers, "TGBU6784203", vessel="MV ALERT",
                    eta="2026-09-20")
    vessel = TrackedVessel(name="MV ALERT",
                           ais_eta=datetime.datetime(2026, 9, 24, 8, 0))  # +4 dni
    db_session.add(vessel)
    db_session.commit()

    first = check_tracking_alerts(db_session, today=today)
    assert first > 0
    drift = db_session.query(Notification).filter_by(kind="eta_drift").count()
    assert drift >= 1

    # drugi przebieg tego samego dnia — deduplikacja, zero nowych alertów dryfu
    check_tracking_alerts(db_session, today=today)
    assert db_session.query(Notification).filter_by(kind="eta_drift").count() == drift


def test_dest_port_alert_once_per_vessel_and_port(client, db_session):
    """Wejście w geofence portu DOCELOWEGO (near_port == cel z AIS Destination):
    jedno powiadomienie per statek+port — dedup bez okna czasowego."""
    headers = login(client)
    _make_container(client, headers, "TGBU6784203", vessel="MV DEST")
    db_session.add(TrackedVessel(name="MV DEST", near_port="GDANSK",
                                 destination="PLGDN"))
    db_session.commit()

    first = check_tracking_alerts(db_session, today=datetime.date(2026, 9, 10))
    assert first > 0
    count = db_session.query(Notification).filter_by(kind="dest_port").count()
    assert count >= 1
    # drugi i trzeci przebieg (także innego dnia) — zero nowych alertów
    check_tracking_alerts(db_session, today=datetime.date(2026, 9, 11))
    assert db_session.query(Notification).filter_by(kind="dest_port").count() == count


def test_no_dest_port_alert_for_intermediate_port(client, db_session):
    """Postój w porcie pośrednim (near_port ≠ cel) nie generuje alertu dest_port."""
    headers = login(client)
    _make_container(client, headers, "TGBU6784203", vessel="MV VIA")
    db_session.add(TrackedVessel(name="MV VIA", near_port="SINGAPORE",
                                 destination="PLGDN"))
    db_session.commit()
    check_tracking_alerts(db_session, today=datetime.date(2026, 9, 10))
    assert db_session.query(Notification).filter_by(kind="dest_port").count() == 0


def test_no_drift_alert_below_threshold(client, db_session):
    headers = login(client)
    _make_container(client, headers, "TGBU6784203", vessel="MV OK", eta="2026-09-20")
    db_session.add(TrackedVessel(name="MV OK",
                                 ais_eta=datetime.datetime(2026, 9, 21, 8, 0)))  # +1 dzień
    db_session.commit()
    check_tracking_alerts(db_session, today=datetime.date(2026, 9, 10))
    assert db_session.query(Notification).filter_by(kind="eta_drift").count() == 0


def test_vessel_stuck_only_with_fresh_ais(client, db_session):
    """Statek, który zniknął z AIS, ma zamrożony near_port — nie alarmujemy
    „stoi już N h” codziennie; ten sam postój ze świeżym sygnałem alarmuje."""
    from app.models import utcnow
    headers = login(client)
    _make_container(client, headers, "TGBU6784203", vessel="MV GONE")
    _make_container(client, headers, "MSCU7654329", vessel="MV HERE")
    since = utcnow() - datetime.timedelta(days=5)
    db_session.add(TrackedVessel(name="MV GONE", near_port="SINGAPORE", near_port_since=since,
                                 last_seen=utcnow() - datetime.timedelta(days=3)))
    db_session.add(TrackedVessel(name="MV HERE", near_port="SINGAPORE", near_port_since=since,
                                 last_seen=utcnow()))
    db_session.commit()
    check_tracking_alerts(db_session)
    titles = [n.title for n in db_session.query(Notification).filter_by(kind="vessel_stuck")]
    assert any("MV HERE" in t for t in titles)
    assert not any("MV GONE" in t for t in titles)


def test_eta_overdue_dedups_and_skips_arrived(client, db_session):
    """Job biegnie co 6 h (+ przy restarcie): drugi przebieg tego samego dnia nie
    dubluje alertu, a kontener już po przybyciu (W_PORCIE) nie dostaje „brak
    potwierdzenia przybycia"."""
    from app.models import Container, ContainerStatus
    headers = login(client)
    today = datetime.date(2026, 9, 10)
    _make_container(client, headers, "TGBU6784203", eta="2026-09-09")
    arrived = _make_container(client, headers, "MSCU7654329", eta="2026-09-09")
    db_session.get(Container, arrived["id"]).status = ContainerStatus.W_PORCIE
    db_session.commit()

    check_tracking_alerts(db_session, today=today)
    first = db_session.query(Notification).filter_by(kind="eta_overdue").count()
    assert first >= 1
    check_tracking_alerts(db_session, today=today)
    assert db_session.query(Notification).filter_by(kind="eta_overdue").count() == first
    titles = [n.title for n in db_session.query(Notification).filter_by(kind="eta_overdue")]
    assert not any("MSCU7654329" in t for t in titles)

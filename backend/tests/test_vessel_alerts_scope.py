"""Alerty per statek (dryf ETA, postój, port docelowy, geofence) a izolacja spółek:
każda spółka dostaje alert wyłącznie ze swoimi kontenerami — bez wycieku numerów
innych spółek i bez pomijania obserwatorów pozostałych spółek na tym samym statku."""
import datetime

from app.models import Company, Container, Notification, Role, TrackedVessel, User, utcnow
from app.notifications import check_tracking_alerts
from app.tracking.ais import _notify_port_arrival


def _two_companies_on_vessel(db, vessel_name):
    users = {}
    for code, no in (("VSA", "MSCU1111110"), ("VSB", "TGBU2222220")):
        co = Company(name=f"{code} Co", code=code)
        db.add(co)
        db.flush()
        users[code] = User(login=f"log-{code.lower()}", hashed_password="x",
                           role=Role.logistics, company_id=co.id)
        db.add(users[code])
        db.add(Container(container_no=no, company_id=co.id, vessel=vessel_name,
                         eta=datetime.date(2026, 9, 20)))
    db.commit()
    return users


def _texts(db, user, kind):
    return [f"{n.title} {n.body}" for n in db.query(Notification)
            .filter_by(user_id=user.id, kind=kind).all()]


def _assert_scoped(db, users, kind):
    a, b = _texts(db, users["VSA"], kind), _texts(db, users["VSB"], kind)
    assert len(a) == 1 and len(b) == 1, (a, b)   # każda spółka dostaje swój alert, raz
    assert "MSCU1111110" in a[0] and "TGBU2222220" not in a[0]
    assert "TGBU2222220" in b[0] and "MSCU1111110" not in b[0]


def test_eta_drift_per_company(client, db_session):
    users = _two_companies_on_vessel(db_session, "MV SCOPE")
    db_session.add(TrackedVessel(name="MV SCOPE",
                                 ais_eta=datetime.datetime(2026, 9, 25, 8, 0)))
    db_session.commit()
    check_tracking_alerts(db_session, today=datetime.date(2026, 9, 10))
    check_tracking_alerts(db_session, today=datetime.date(2026, 9, 10))  # dedup
    _assert_scoped(db_session, users, "eta_drift")


def test_vessel_stuck_per_company(client, db_session):
    users = _two_companies_on_vessel(db_session, "MV STUCK")
    db_session.add(TrackedVessel(name="MV STUCK", near_port="SINGAPORE",
                                 near_port_since=utcnow() - datetime.timedelta(days=5),
                                 last_seen=utcnow()))
    db_session.commit()
    check_tracking_alerts(db_session)
    check_tracking_alerts(db_session)
    _assert_scoped(db_session, users, "vessel_stuck")


def test_dest_port_per_company(client, db_session):
    users = _two_companies_on_vessel(db_session, "MV HOME")
    db_session.add(TrackedVessel(name="MV HOME", near_port="GDANSK", destination="PLGDN"))
    db_session.commit()
    check_tracking_alerts(db_session)
    check_tracking_alerts(db_session)
    _assert_scoped(db_session, users, "dest_port")


def test_geofence_per_company(client, db_session):
    users = _two_companies_on_vessel(db_session, "MV GEO")
    vessel = TrackedVessel(name="MV GEO")
    db_session.add(vessel)
    db_session.commit()
    _notify_port_arrival(db_session, vessel, "GDANSK")
    db_session.commit()
    _assert_scoped(db_session, users, "vessel_port")

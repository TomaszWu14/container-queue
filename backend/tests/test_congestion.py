"""Kongestia portów: dzienny zapis, upsert-max, alert 2× mediana, endpoint trendu."""
import datetime

from app.models import Notification, PortCongestion, TrackedVessel, today_pl
from app.tracking.congestion import check_congestion_alerts, record_port_congestion
from tests.conftest import login


def _make_container(client, headers, no, vessel):
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    resp = client.post("/api/containers", headers=headers,
                       json={"container_no": no, "company_id": company_id,
                             "vessel": vessel})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_record_congestion_counts_and_upserts_max(client, db_session):
    headers = login(client)
    _make_container(client, headers, "TGBU6784203", "MV REDA")
    _make_container(client, headers, "MSCU7654329", "MV REDA DWA")
    db_session.add(TrackedVessel(name="MV REDA", near_port="GDANSK"))
    db_session.add(TrackedVessel(name="MV REDA DWA", near_port="GDANSK"))
    # statek bez aktywnego kontenera — nie liczy się do kongestii
    db_session.add(TrackedVessel(name="OBCY STATEK", near_port="GDANSK"))
    db_session.commit()

    today = today_pl()
    assert record_port_congestion(db_session) == 1
    row = db_session.query(PortCongestion).filter_by(port="GDANSK", day=today).one()
    assert row.waiting == 2

    # drugi przebieg z mniejszą liczbą — max dnia zostaje
    db_session.query(TrackedVessel).filter_by(name="MV REDA DWA") \
        .update({"near_port": ""})
    db_session.commit()
    record_port_congestion(db_session)
    db_session.refresh(row)
    assert row.waiting == 2


def test_congestion_alert_over_double_median_dedups(client, db_session):
    today = today_pl()
    # 14 dni historii z medianą 1, dziś 3 (> 2×1)
    for i in range(1, 15):
        db_session.add(PortCongestion(port="GDANSK",
                                      day=today - datetime.timedelta(days=i), waiting=1))
    db_session.add(PortCongestion(port="GDANSK", day=today, waiting=3))
    db_session.commit()

    assert check_congestion_alerts(db_session) > 0
    count = db_session.query(Notification).filter_by(kind="port_congestion").count()
    assert count >= 1
    # drugi przebieg tego samego dnia — dedup po tytule
    check_congestion_alerts(db_session)
    assert db_session.query(Notification) \
        .filter_by(kind="port_congestion").count() == count


def test_congestion_alert_once_per_day_even_when_count_grows(client, db_session):
    """Licznik dnia rośnie (upsert max 3 → 4) — nadal jeden alert per port i dzień."""
    today = today_pl()
    for i in range(1, 15):
        db_session.add(PortCongestion(port="GDANSK",
                                      day=today - datetime.timedelta(days=i), waiting=1))
    row = PortCongestion(port="GDANSK", day=today, waiting=3)
    db_session.add(row)
    db_session.commit()

    check_congestion_alerts(db_session)
    count = db_session.query(Notification).filter_by(kind="port_congestion").count()
    assert count >= 1
    row.waiting = 4                       # kolejny cykl trackingu tego samego dnia
    db_session.commit()
    check_congestion_alerts(db_session)
    assert db_session.query(Notification) \
        .filter_by(kind="port_congestion").count() == count


def test_congestion_job_runs_only_with_ais():
    """Kongestię zasila AIS (near_port) — job powstaje tylko przy włączonym AIS."""
    from app import jobs
    congestion = check_congestion_alerts, record_port_congestion
    fns = [fn for job in jobs.build_jobs(with_ais=True)
           for fn in job.fns]
    assert all(fn in fns for fn in congestion)
    fns = [fn for job in jobs.build_jobs(with_ais=False)
           for fn in job.fns]
    assert not any(fn in fns for fn in congestion)   # bez AIS nie ma czego liczyć


def test_no_alert_without_history_or_below_threshold(client, db_session):
    today = today_pl()
    # krótka historia (3 dni) — cisza mimo skoku
    for i in range(1, 4):
        db_session.add(PortCongestion(port="GDYNIA",
                                      day=today - datetime.timedelta(days=i), waiting=1))
    db_session.add(PortCongestion(port="GDYNIA", day=today, waiting=9))
    # pełna historia, ale dziś dokładnie 2× mediana — bez alertu (próg to >2×)
    for i in range(1, 15):
        db_session.add(PortCongestion(port="ROTTERDAM",
                                      day=today - datetime.timedelta(days=i), waiting=2))
    db_session.add(PortCongestion(port="ROTTERDAM", day=today, waiting=4))
    db_session.commit()
    check_congestion_alerts(db_session)
    assert db_session.query(Notification).filter_by(kind="port_congestion").count() == 0


def test_congestion_endpoint_trend_and_alert_flag(client, db_session):
    headers = login(client)
    today = today_pl()
    for i in range(1, 15):
        db_session.add(PortCongestion(port="GDANSK",
                                      day=today - datetime.timedelta(days=i), waiting=1))
    db_session.add(PortCongestion(port="GDANSK", day=today, waiting=3))
    db_session.commit()

    data = client.get("/api/tracking/congestion", headers=headers).json()
    gd = next(x for x in data if x["port"] == "GDANSK")
    assert gd["alert"] is True
    assert len(gd["days"]) == 15
    assert gd["days"][-1] == {"day": today.isoformat(), "waiting": 3}

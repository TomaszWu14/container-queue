"""Dziennik żądań/zadań: co trafia do bazy, maskowanie, alerty, retencja."""
import datetime

from sqlalchemy import select

from app import applog
from app.models import JobRun, Notification, RequestCounter, RequestLog, utcnow
from tests.conftest import login


def _flush(db_session):
    applog.flush(db_session)
    db_session.expire_all()


def test_error_and_slow_requests_logged_ok_counted_only(client, db_session, monkeypatch):
    applog.reset_for_tests()
    # Na obciążonej maszynie login (bcrypt) potrafi przekroczyć SLOW_MS i trafić do dziennika
    # jako „wolne" — test sprawdza podział błąd/OK, więc próg wolnych wyłączamy.
    monkeypatch.setattr(applog, "SLOW_MS", 10**9)
    h = login(client)
    client.get("/api/containers/999999", headers=h)          # 404 → zapis
    client.get("/api/companies", headers=h)                   # 200 → tylko licznik
    client.get("/api/health")                                 # pomijane całkiem
    _flush(db_session)
    rows = db_session.scalars(select(RequestLog)).all()
    assert [(r.method, r.path, r.status) for r in rows] == [("GET", "/api/containers/999999", 404)]
    assert rows[0].user_id is not None and rows[0].request_id
    total = sum(c.total for c in db_session.scalars(select(RequestCounter)).all())
    assert total >= 3          # login + 404 + companies (health nie liczony)


def test_public_token_masked_in_path(db_session):
    applog.reset_for_tests()
    applog.record_request(method="GET", path="/api/avizo/abcdefghijklmnopqrstuv", status=404,
                          duration_ms=5, user_id=None, ip="1.2.3.4", request_id="r1")
    _flush(db_session)
    row = db_session.scalars(select(RequestLog)).one()
    assert "abcdefghijklmnopqrstuv" not in row.path


def test_5xx_alerts_admins_once_per_hour(db_session):
    applog.reset_for_tests()
    for _ in range(3):
        applog.record_request(method="GET", path="/api/x", status=500, duration_ms=3,
                              user_id=None, ip="", request_id="r", error="Traceback…")
        _flush(db_session)
    alerts = db_session.scalars(select(Notification).where(Notification.kind == "system-error")).all()
    assert len(alerts) == len({a.user_id for a in alerts}) >= 1   # jeden na admina, nie trzy


def test_failed_job_recorded(db_session):
    applog.reset_for_tests()
    applog.record_job(job="demo", fn="boom", started_at=utcnow(), duration_ms=12, ok=False,
                      detail="ValueError: x")
    _flush(db_session)
    run = db_session.scalars(select(JobRun)).one()
    assert (run.job, run.fn, run.ok) == ("demo", "boom", False)


def test_method_over_8_chars_truncated(db_session):
    applog.reset_for_tests()
    applog.record_request(method="PROPFIND1", path="/api/x", status=500, duration_ms=1,
                          user_id=None, ip="", request_id="r")
    _flush(db_session)
    row = db_session.scalars(select(RequestLog)).one()
    assert row.method == "PROPFIND1"[:8]
    assert len(row.method) == 8


def test_alert_body_has_no_traceback(db_session):
    applog.reset_for_tests()
    applog.record_request(method="GET", path="/api/x", status=500, duration_ms=3,
                          user_id=None, ip="", request_id="r",
                          error="Traceback (most recent call last):\n  boom")
    _flush(db_session)
    alert = db_session.scalars(select(Notification).where(Notification.kind == "system-error")).one()
    assert "Traceback" not in alert.body


def test_two_flushes_same_minute_sum_into_one_row(db_session):
    applog.reset_for_tests()
    applog.record_request(method="GET", path="/api/x", status=200, duration_ms=5,
                          user_id=None, ip="", request_id="r1")
    _flush(db_session)
    applog.record_request(method="GET", path="/api/x", status=200, duration_ms=7,
                          user_id=None, ip="", request_id="r2")
    _flush(db_session)
    rows = db_session.scalars(select(RequestCounter)).all()
    assert len(rows) == 1
    assert rows[0].total == 2
    assert rows[0].dur_ms_sum == 12


def test_middleware_unhandled_exception_logged_as_500(client, db_session):
    applog.reset_for_tests()
    from fastapi.testclient import TestClient

    from app.main import app

    @app.get("/api/_boom_test", include_in_schema=False)
    def _boom():
        raise ValueError("kaboom")
    # SPA fallback (/{full_path:path}) jest już zarejestrowany i łapie /api/* jako 404
    # JSON zanim dojdzie do reszty routera — nowa trasa musi wyprzedzić go w liście.
    app.router.routes.insert(0, app.router.routes.pop())

    h = login(client)
    with TestClient(app, raise_server_exceptions=False) as raw_client:
        raw_client.get("/api/_boom_test", headers=h)
    _flush(db_session)
    row = db_session.scalars(select(RequestLog).where(RequestLog.path == "/api/_boom_test")).one()
    assert row.status == 500
    assert "ValueError" in row.error


def test_monitor_sample_success_not_recorded_only_failure_is(db_session):
    applog.reset_for_tests()
    applog.record_job(job="monitor_sample", fn="sample", started_at=utcnow(), duration_ms=1,
                      ok=True, detail="")
    applog.record_job(job="monitor_sample", fn="sample", started_at=utcnow(), duration_ms=1,
                      ok=False, detail="boom")
    _flush(db_session)
    rows = db_session.scalars(select(JobRun)).all()
    assert len(rows) == 1
    assert rows[0].ok is False


def test_purge_removes_older_than_30_days(db_session):
    old = utcnow() - datetime.timedelta(days=31)
    db_session.add(RequestLog(at=old, method="GET", path="/api/a", status=500, duration_ms=1,
                              ip="", request_id="", error=""))
    db_session.add(JobRun(job="j", fn="f", started_at=old, duration_ms=1, ok=True, detail=""))
    db_session.add(RequestCounter(minute=old.replace(second=0, microsecond=0), total=1, c4xx=0,
                                  c5xx=0, dur_ms_sum=1))
    db_session.commit()
    assert applog.purge(db_session) == 3


def test_alert_respects_bell_rule_in_matrix(db_session):
    from app.models import NotificationRule
    applog.reset_for_tests()
    db_session.add(NotificationRule(kind="system-error", role="admin", channel="bell", enabled=False))
    db_session.commit()
    applog.record_request(method="GET", path="/api/x", status=500, duration_ms=3,
                          user_id=None, ip="", request_id="r", error="boom")
    _flush(db_session)
    assert db_session.scalars(select(Notification).where(
        Notification.kind == "system-error")).all() == []

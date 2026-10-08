"""API dziennika (admin-only): żądania, ruch, zadania tła, błędy frontu."""
import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import ClientError, JobRun, RequestCounter, RequestLog, Role, User, utcnow
from app.security import hash_password
from tests.conftest import login


def _logi_headers(client):
    with SessionLocal() as db:
        u = User(login="logi-logs", hashed_password=hash_password("pass12345"),
                 role=Role.logistics, company_id=None, view_all_companies=False,
                 full_name="", email="")
        db.add(u)
        db.commit()
    return login(client, "logi-logs", "pass12345")


def test_requests_status_filters_and_user_login(client, db_session):
    admin = login(client)
    admin_id = db_session.scalar(select(User.id).where(User.login == "admin"))
    now = utcnow()
    db_session.add_all([
        RequestLog(at=now, method="GET", path="/api/containers", status=500, duration_ms=5,
                  user_id=admin_id, ip="", request_id="r1", error=""),
        RequestLog(at=now, method="GET", path="/api/containers", status=404, duration_ms=5,
                  user_id=None, ip="", request_id="r2", error=""),
        RequestLog(at=now, method="GET", path="/api/orders", status=200, duration_ms=1500,
                  user_id=None, ip="", request_id="r3", error=""),
    ])
    db_session.commit()

    r5xx = client.get("/api/admin/logs/requests", headers=admin, params={"status": "5xx"}).json()
    assert r5xx["total"] == 1
    assert r5xx["items"][0]["status"] == 500
    assert r5xx["items"][0]["user_login"] == "admin"

    slow = client.get("/api/admin/logs/requests", headers=admin, params={"status": "slow"}).json()
    assert slow["total"] == 1
    assert slow["items"][0]["duration_ms"] == 1500

    q = client.get("/api/admin/logs/requests", headers=admin, params={"q": "containers"}).json()
    assert q["total"] == 2


def test_traffic_aggregates_into_5min_buckets(client, db_session):
    admin = login(client)
    base = utcnow().replace(second=0, microsecond=0)
    bucket = base - datetime.timedelta(minutes=base.minute % 5)
    db_session.add_all([
        RequestCounter(minute=bucket, total=3, c4xx=1, c5xx=0, dur_ms_sum=30),
        RequestCounter(minute=bucket + datetime.timedelta(minutes=1), total=2, c4xx=0, c5xx=1,
                       dur_ms_sum=20),
    ])
    db_session.commit()

    data = client.get("/api/admin/logs/traffic", headers=admin, params={"hours": 1}).json()
    points = [p for p in data if p["total"] > 0]
    assert len(points) == 1
    assert points[0]["total"] == 5
    assert points[0]["c4xx"] == 1
    assert points[0]["c5xx"] == 1
    assert points[0]["avg_ms"] == 10


def test_jobs_latest_is_newest_per_pair(client, db_session):
    admin = login(client)
    older = utcnow() - datetime.timedelta(minutes=5)
    newer = utcnow()
    db_session.add_all([
        JobRun(job="demurrage", fn="check", started_at=older, duration_ms=1, ok=True, detail=""),
        JobRun(job="demurrage", fn="check", started_at=newer, duration_ms=2, ok=False,
              detail="err"),
    ])
    db_session.commit()

    data = client.get("/api/admin/logs/jobs", headers=admin).json()
    matching = [j for j in data["latest"] if (j["job"], j["fn"]) == ("demurrage", "check")]
    assert len(matching) == 1
    assert matching[0]["ok"] is False
    assert len(data["history"]) >= 2


def test_jobs_latest_survives_200row_window(client, db_session):
    admin = login(client)
    base = utcnow()
    db_session.add(JobRun(job="rzadki", fn="check", started_at=base - datetime.timedelta(days=1),
                          duration_ms=1, ok=True, detail=""))
    db_session.add_all([
        JobRun(job="czesty", fn="tick", started_at=base - datetime.timedelta(seconds=i),
              duration_ms=1, ok=True, detail="")
        for i in range(205)
    ])
    db_session.commit()

    data = client.get("/api/admin/logs/jobs", headers=admin).json()
    matching = [j for j in data["latest"] if (j["job"], j["fn"]) == ("rzadki", "check")]
    assert len(matching) == 1
    assert len(data["history"]) == 200


def test_requests_status_abc_returns_422(client):
    admin = login(client)
    r = client.get("/api/admin/logs/requests", headers=admin, params={"status": "abc"})
    assert r.status_code == 422


def test_requests_date_from_to_filters_inclusive(client, db_session):
    admin = login(client)
    day1 = utcnow() - datetime.timedelta(days=2)
    day2 = utcnow() - datetime.timedelta(days=1)
    day3 = utcnow()
    db_session.add_all([
        RequestLog(at=day1, method="GET", path="/api/a", status=200, duration_ms=1,
                  user_id=None, ip="", request_id="d1", error=""),
        RequestLog(at=day2, method="GET", path="/api/b", status=200, duration_ms=1,
                  user_id=None, ip="", request_id="d2", error=""),
        RequestLog(at=day3, method="GET", path="/api/c", status=200, duration_ms=1,
                  user_id=None, ip="", request_id="d3", error=""),
    ])
    db_session.commit()

    data = client.get("/api/admin/logs/requests", headers=admin,
                      params={"date_from": day2.date().isoformat(),
                              "date_to": day2.date().isoformat()}).json()
    assert data["total"] == 1
    assert data["items"][0]["request_id"] == "d2"


def test_client_errors_lists_recent(client, db_session):
    admin = login(client)
    db_session.add(ClientError(name="TypeError", message="boom", stack="", url="/x",
                               user_agent=""))
    db_session.commit()

    data = client.get("/api/admin/logs/client-errors", headers=admin).json()
    assert any(e["name"] == "TypeError" and e["message"] == "boom" for e in data)


def test_logistics_role_forbidden_on_all_endpoints(client):
    headers = _logi_headers(client)
    for path in ("/api/admin/logs/requests", "/api/admin/logs/traffic",
                "/api/admin/logs/jobs", "/api/admin/logs/client-errors"):
        assert client.get(path, headers=headers).status_code == 403

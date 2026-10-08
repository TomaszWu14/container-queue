"""/api/health: pola diagnostyczne (wersja, uptime, ostatnia synchronizacja)."""
from app.models import Container, TrackedVessel, utcnow


def test_health_returns_ok_with_diagnostics(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok" and data["database"] == "ok"
    assert isinstance(data["uptime_s"], int) and data["uptime_s"] >= 0
    assert data["version"]  # 'dev' w testach, ale zawsze obecne
    assert data["last_ais_seen"] is None
    assert data["last_tracking_sync"] is None


def test_dzis_removed_redirects_301_to_queue_keeping_query(client):
    """Zakładka „Co dziś” usunięta: /dzis → 301 /kolejka (query zachowane)."""
    r = client.get("/dzis?firm=acme", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/kolejka?firm=acme"
    assert client.get("/dzis", follow_redirects=False).headers["location"] == "/kolejka"


def test_health_reports_last_ais_seen_and_tracking_sync(client, db_session):
    now = utcnow()
    db_session.add(TrackedVessel(name="MV HEALTH", last_seen=now))
    db_session.add(Container(container_no="TGBU6784271", company_id=1, tracked_at=now))
    db_session.commit()
    data = client.get("/api/health").json()
    assert data["last_ais_seen"] is not None
    assert data["last_tracking_sync"] is not None

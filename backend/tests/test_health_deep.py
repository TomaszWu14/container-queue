"""OBS-009: /api/health/deep — pętle tła, wiek kopii zapasowej, zajętość dysku.

/api/health zostaje lekki (Docker, proxy); głęboki wariant dla zewnętrznego monitora:
503, gdy kopia jest za stara, zadanie tła dawno nie przeszło albo dysk się kończy.
Publicznie tylko status — szczegóły (wiek, procenty, nazwy zadań) widzi wyłącznie admin."""
import asyncio
import datetime
import os
import time

import pytest

from app import applog, jobs, monitoring
from app.config import settings
from app.models import JobRun, RequestLog, utcnow
from tests.conftest import login

PG_URL = "postgresql+psycopg2://timporye:x@db:5432/timporye"   # tylko parsowany, bez połączenia


@pytest.fixture(autouse=True)
def _healthy_env(monkeypatch, tmp_path):
    """Punkt wyjścia: świeża kopia, pusty dysk, brak pętli tła — każdy test psuje jedno."""
    monkeypatch.setattr(settings, "database_url", PG_URL)
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path))
    (tmp_path / "timporye-20260928-020000.sql.gz").write_bytes(b"x")
    monkeypatch.setattr(monitoring, "disks", lambda: [
        {"label": "system", "path": "/", "total_gb": 100.0, "used_gb": 40.0,
         "free_gb": 60.0, "percent": 40.0}])
    monkeypatch.setattr(jobs, "STARTED", {})


def test_deep_ok_when_everything_fresh(client):
    r = client.get("/api/health/deep")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_deep_503_when_backup_dir_empty(client, tmp_path):
    for f in tmp_path.iterdir():
        f.unlink()
    r = client.get("/api/health/deep")
    assert r.status_code == 503
    assert r.json() == {"status": "fail"}          # publicznie bez szczegółów


def test_deep_503_when_newest_backup_too_old(client, tmp_path):
    dump = tmp_path / "timporye-20260928-020000.sql.gz"
    old = time.time() - (settings.backup_max_age_hours + 1) * 3600
    os.utime(dump, (old, old))
    assert client.get("/api/health/deep").status_code == 503


def test_backup_not_checked_without_postgres(client, tmp_path, monkeypatch):
    # dev/SQLite: backup.sh pomija kopię, więc brak plików to nie awaria
    monkeypatch.setattr(settings, "database_url", "sqlite:///./x.db")
    for f in tmp_path.iterdir():
        f.unlink()
    assert client.get("/api/health/deep").status_code == 200


def test_deep_503_when_disk_almost_full(client, monkeypatch):
    monkeypatch.setattr(monitoring, "disks", lambda: [
        {"label": "załączniki", "path": "/data/uploads", "total_gb": 100.0, "used_gb": 95.0,
         "free_gb": 5.0, "percent": 95.0}])
    assert client.get("/api/health/deep").status_code == 503


def _started(name, interval_s, fns, loop_age_h):
    return {name: (interval_s, fns, utcnow() - datetime.timedelta(hours=loop_age_h))}


def test_deep_503_when_background_job_stale(client, db_session, monkeypatch):
    """Pętla żyje od 10 h, zadanie co 6 h, ostatni udany przebieg 8 h temu = martwa pętla."""
    monkeypatch.setattr(jobs, "STARTED", _started("demurrage", 6 * 3600,
                                                  ("check_demurrage_alerts",), 10))
    db_session.add(JobRun(job="demurrage", fn="check_demurrage_alerts", ok=True, duration_ms=5,
                          started_at=utcnow() - datetime.timedelta(hours=8)))
    db_session.commit()
    assert client.get("/api/health/deep").status_code == 503
    details = client.get("/api/admin/health/deep", headers=login(client)).json()
    job = details["checks"]["jobs"]["items"][0]
    assert job["job"] == "demurrage" and job["ok"] is False
    assert job["stale"] == ["check_demurrage_alerts"]


def test_failed_runs_do_not_count_as_alive(client, db_session, monkeypatch):
    monkeypatch.setattr(jobs, "STARTED", _started("customs_delay", 6 * 3600,
                                                  ("check_customs_alerts",), 10))
    db_session.add(JobRun(job="customs_delay", fn="check_customs_alerts", ok=False,
                          duration_ms=5, started_at=utcnow() - datetime.timedelta(minutes=5)))
    db_session.commit()
    assert client.get("/api/health/deep").status_code == 503


def test_recent_successful_run_is_ok(client, db_session, monkeypatch):
    monkeypatch.setattr(jobs, "STARTED", _started("demurrage", 6 * 3600,
                                                  ("check_demurrage_alerts",), 10))
    db_session.add(JobRun(job="demurrage", fn="check_demurrage_alerts", ok=True, duration_ms=5,
                          started_at=utcnow() - datetime.timedelta(hours=1)))
    db_session.commit()
    assert client.get("/api/health/deep").status_code == 200


def test_freshly_started_loop_gets_grace(client, monkeypatch):
    # po restarcie pierwszy przebieg jeszcze trwa / czeka na zrzut dziennika — to nie awaria
    monkeypatch.setattr(jobs, "STARTED", _started("demurrage", 6 * 3600,
                                                  ("check_demurrage_alerts",), 0.1))
    assert client.get("/api/health/deep").status_code == 200


def test_job_loop_registers_itself():
    async def one_pass():
        job = jobs.Job("demo", 3600, (lambda db: None,))
        task = asyncio.ensure_future(jobs.job_loop(job))
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(one_pass())
    interval_s, fns, loop_started = jobs.STARTED["demo"]
    assert interval_s == 3600 and fns == ("<lambda>",)
    assert utcnow() - loop_started < datetime.timedelta(minutes=1)


def test_admin_details_require_admin(client):
    assert client.get("/api/admin/health/deep").status_code == 401
    details = client.get("/api/admin/health/deep", headers=login(client)).json()
    assert details["status"] == "ok"
    assert set(details["checks"]) == {"database", "jobs", "invoice_queue", "backup", "disk"}
    assert details["checks"]["backup"]["newest"] == "timporye-20260928-020000.sql.gz"


def test_deep_503_not_logged_as_server_error(client, db_session, tmp_path):
    """Awaria zgłaszana monitorowi nie może co minutę zalewać dziennika i dzwonka adminów."""
    for f in tmp_path.iterdir():
        f.unlink()
    applog.reset_for_tests()
    assert client.get("/api/health/deep").status_code == 503
    applog.flush(db_session)
    assert db_session.query(RequestLog).filter(RequestLog.path == "/api/health/deep").count() == 0


def test_plain_health_stays_lightweight(client, tmp_path):
    # brak kopii nie może położyć HEALTHCHECK Dockera (restart kontenera nic nie naprawi)
    for f in tmp_path.iterdir():
        f.unlink()
    assert client.get("/api/health").status_code == 200

"""BUILD-003 / ARCH-003: kilka workerów uvicorna (WEB_CONCURRENCY>1).

- Start z WEB_CONCURRENCY>1 dozwolony na PostgreSQL (limiter logowań jest w bazie —
  loginlim001, pętle tła prowadzi jeden proces-lider), blokowany na SQLite (brak
  advisory locków i jeden zapisujący — test_jedna_instancja).
- Lider = sesyjny pg_advisory_lock na własnym połączeniu. Dwa procesy na jednej bazie →
  pętle tła startuje tylko jeden; po jego końcu przejmuje drugi (weryfikacja z audytu:
  „dwa razy job_loop na tej samej bazie → jedna notyfikacja”).
"""
import asyncio
import threading
import time
from types import SimpleNamespace

from app import jobs, leader
from app.config import settings
from app.rate_limit import assert_worker_config


def test_wiele_workerow_na_postgres_startuje(monkeypatch, caplog):
    monkeypatch.setattr(settings, "web_concurrency", 3)
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg2://u:p@db/timporye")
    with caplog.at_level("INFO", logger="app.rate_limit"):
        assert_worker_config()
    # budżet połączeń: 3 × (pula + overflow + lider/locki) — do porównania z max_connections
    need = 3 * (settings.db_pool_size + settings.db_max_overflow + 2)
    assert f"{need}" in caplog.text


def test_podzial_zadan_monitor_w_kazdym_procesie():
    per_process, leader_only = jobs.split_jobs(jobs.build_jobs(with_ais=True))
    assert [j.name for j in per_process] == ["monitor_sample"]
    assert "monitor_sample" not in {j.name for j in leader_only}
    assert {"demurrage", "sms_reminders", "daily_digest"} <= {j.name for j in leader_only}


def test_sqlite_zawsze_lider():
    lead = leader.Leadership(url="sqlite:///./x.db")
    assert lead.acquire() is True
    lead.release()


def test_lifespan_jeden_proces_startuje_obie_grupy(monkeypatch, _db_template):
    """Jeden proces (SQLite = zawsze lider): zadanie per proces i zadanie lidera ruszają."""
    from fastapi.testclient import TestClient

    from app import main
    from app.database import engine
    ran: list[str] = []
    monkeypatch.setattr(settings, "run_background_jobs", True)
    monkeypatch.setattr(settings, "aisstream_api_key", "")
    monkeypatch.setattr(main, "build_jobs", lambda with_ais=False: [
        jobs.Job("monitor_sample", 3600, (lambda _db: ran.append("per_proces"),)),
        jobs.Job("demurrage", 3600, (lambda _db: ran.append("lider"),))])
    engine.dispose()
    with engine.raw_connection() as raw:
        _db_template.backup(raw.driver_connection)
    with TestClient(main.app):
        for _ in range(100):
            if {"per_proces", "lider"} <= set(ran):
                break
            time.sleep(0.05)
    assert sorted(ran) == ["lider", "per_proces"]


class _FakeServer:
    """Zastępca serwera PG: sesyjny advisory lock = wspólny threading.Lock."""

    def __init__(self):
        self.lock = threading.Lock()
        self.owner = None


class _FakeConn:
    def __init__(self, server):
        self.server, self.closed, self.mine = server, False, False

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "pg_try_advisory_lock" in sql:
            self.mine = self.server.lock.acquire(blocking=False)
            got = self.mine
        elif "pg_advisory_unlock" in sql:
            got = self.mine
            if self.mine:
                self.server.lock.release()
                self.mine = False
        else:
            got = 1
        return SimpleNamespace(scalar=lambda: got)

    def commit(self):
        pass

    def close(self):
        if self.mine:   # koniec sesji PG = zwolnienie jej advisory locków
            self.server.lock.release()
            self.mine = False
        self.closed = True


def _pg_leadership(server):
    lead = leader.Leadership(url="postgresql+psycopg2://u:p@db/timporye")
    lead._connect = lambda: _FakeConn(server)
    return lead


def test_postgres_drugi_proces_nie_jest_liderem_do_zwolnienia():
    server = _FakeServer()
    a, b = _pg_leadership(server), _pg_leadership(server)
    assert a.acquire() is True
    assert a.acquire() is True    # ponowne sprawdzenie nie gubi roli
    assert b.acquire() is False
    a.release()
    assert b.acquire() is True


def test_dwa_procesy_petle_tla_startuje_jeden():
    server = _FakeServer()
    starts: list[str] = []

    def starter(name):
        def start():
            starts.append(name)
            return [asyncio.create_task(asyncio.sleep(3600))]
        return start

    async def scenario():
        a = asyncio.create_task(leader.leader_loop(starter("A"), _pg_leadership(server), 0.01))
        await asyncio.sleep(0.05)
        b = asyncio.create_task(leader.leader_loop(starter("B"), _pg_leadership(server), 0.01))
        await asyncio.sleep(0.1)
        assert starts == ["A"]          # B czeka jako rezerwowy
        a.cancel()                      # proces A kończy się → lock zwolniony
        await asyncio.gather(a, return_exceptions=True)
        await asyncio.sleep(0.1)
        assert starts == ["A", "B"]     # B przejął pętle
        b.cancel()
        await asyncio.gather(b, return_exceptions=True)

    asyncio.run(scenario())
    assert not server.lock.locked()

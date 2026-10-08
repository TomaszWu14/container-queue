"""ARCH-003: pętle tła pod advisory lockiem + blokada startu z wieloma workerami na SQLite."""
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app import jobs
from app.config import settings
from app.main import validate_settings


def test_zajete_zadanie_druga_proba_sie_pomija(monkeypatch):
    """Dwa równoległe przebiegi tego samego zadania: drugi trafia na zajęty lock i pomija."""
    held = threading.Lock()   # zastępca pg_try_advisory_lock (na SQLite lock to no-op)

    @contextmanager
    def fake_lock(_name):
        got = held.acquire(blocking=False)
        try:
            yield got
        finally:
            if got:
                held.release()

    monkeypatch.setattr(jobs, "job_lock", fake_lock)
    inside, release, calls = threading.Event(), threading.Event(), []

    def slow(_db):
        calls.append(1)
        inside.set()
        release.wait(5)
        return "ok"

    first: list = []
    t = threading.Thread(target=lambda: first.append(jobs._run(slow, "demurrage")))
    t.start()
    assert inside.wait(5)
    assert jobs._run(slow, "demurrage") is jobs.SKIPPED   # równoległa próba
    release.set()
    t.join(5)
    assert first == ["ok"] and calls == [1]
    assert jobs._run(slow, "demurrage") == "ok"   # po zwolnieniu znów wolno


class _FakeConn:
    def __init__(self, got):
        self.got, self.sql = got, []

    def execute(self, stmt, params):
        self.sql.append((str(stmt), params["k"]))
        return SimpleNamespace(scalar=lambda: self.got)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _pg_engine(monkeypatch, got):
    conn = _FakeConn(got)
    monkeypatch.setattr(jobs, "engine", SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"), connect=lambda: conn))
    return conn


def test_postgres_lock_zwalniany_przy_wyjatku_na_tym_samym_polaczeniu(monkeypatch):
    conn = _pg_engine(monkeypatch, got=True)

    def boom(_db):
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        jobs._run(boom, "customs_delay")
    key = jobs.lock_key("customs_delay")
    assert conn.sql == [("SELECT pg_try_advisory_lock(:k)", key),
                        ("SELECT pg_advisory_unlock(:k)", key)]


def test_postgres_zajety_lock_pomija_bez_unlock(monkeypatch):
    conn = _pg_engine(monkeypatch, got=False)
    called = []
    assert jobs._run(called.append, "sms_reminders") is jobs.SKIPPED
    assert called == [] and len(conn.sql) == 1   # nie zwalniamy cudzego locka


def test_klucze_stale_i_rozne_per_zadanie():
    names = [j.name for j in jobs.build_jobs(with_ais=True)] + ["ais"]
    keys = [jobs.lock_key(n) for n in names]
    assert len(set(keys)) == len(keys)
    assert jobs.lock_key("demurrage") == jobs.lock_key("demurrage") < 2**63


def test_monitor_per_proces_bez_locka(monkeypatch):
    monkeypatch.setattr(jobs, "job_lock", lambda _n: pytest.fail("monitor nie bierze locka"))
    monkeypatch.setattr(jobs, "_run_fn", lambda fn: "próbka")
    assert jobs._run(lambda db: None, "monitor_sample") == "próbka"


def test_web_concurrency_2_blokuje_start_na_sqlite(monkeypatch):
    # BUILD-003: limiter logowań jest w bazie (loginlim001), pętle tła ma lider (leader.py) —
    # >1 worker dozwolony na PostgreSQL (test_wiele_workerow), SQLite nadal blokuje
    monkeypatch.setattr(settings, "web_concurrency", 2)
    with pytest.raises(RuntimeError, match="WEB_CONCURRENCY=2.*SQLite"):
        validate_settings()


def test_web_concurrency_1_startuje(monkeypatch):
    monkeypatch.setattr(settings, "web_concurrency", 1)
    validate_settings()

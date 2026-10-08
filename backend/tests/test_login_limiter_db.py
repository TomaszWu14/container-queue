"""ARCH-003 + SEC-012 — limiter logowań ze stanem w bazie + limit per konto.

Weryfikacja z audytu: „nowa instancja LoginRateLimiter nie zeruje licznika konta” (restart
= deploy) i „dwie instancje współdzielące bazę liczą razem” (kilka workerów uvicorna).
Per konto: porażki ze WSZYSTKICH IP (rozproszony brute force obchodzi limit pary IP+login)
dają progresywną przerwę z Retry-After, alert do adminów przy wejściu w blokadę.
"""
import datetime
import importlib.util
import itertools
import pathlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, select, update

from app.config import settings
from app.database import Base, SessionLocal
from app.models import LoginFailure, Notification, Role, User
from app.rate_limit import LoginRateLimiter
from app.routers import auth
from app.security import hash_password, login_limiter

BAD = {"username": "admin", "password": "zle-haslo-123"}
_MIG = (pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"
        / "loginlim001_limiter_logowan_w_bazie.py")


def _429(fn, *args, **kwargs) -> HTTPException:
    with pytest.raises(HTTPException) as exc:
        fn(*args, **kwargs)
    assert exc.value.status_code == 429
    return exc.value


def test_restart_does_not_reset_counters(client):
    for _ in range(settings.login_max_attempts):
        login_limiter.register_failure("ip:10.0.0.1|login:admin")
    fresh = LoginRateLimiter()   # „restart procesu” = nowy obiekt, pusta pamięć
    _429(fresh.check, "ip:10.0.0.1|login:admin")


def test_two_instances_share_one_counter(client):
    worker_a, worker_b = LoginRateLimiter(), LoginRateLimiter()
    for i in range(settings.login_max_attempts):
        (worker_a if i % 2 else worker_b).register_failure("ip:10.0.0.2|login:admin")
    _429(worker_a.check, "ip:10.0.0.2|login:admin")
    _429(worker_b.check, "ip:10.0.0.2|login:admin")
    worker_b.reset("ip:10.0.0.2|login:admin")
    worker_a.check("ip:10.0.0.2|login:admin")   # reset w B widoczny w A


def test_keys_are_hashed_and_old_rows_swept(client, monkeypatch):
    login_limiter.register_failure("ip:10.9.9.9|login:tajne-haslo")
    with SessionLocal() as db:
        keys = db.scalars(select(LoginFailure.key)).all()
        assert keys and all(len(k) == 64 and "10.9.9.9" not in k for k in keys)
        db.execute(update(LoginFailure).values(created_at=datetime.datetime(2020, 1, 1)))
        db.commit()
    limiter = LoginRateLimiter()
    monkeypatch.setattr(LoginRateLimiter, "SWEEP_EVERY", 1)
    limiter.register_failure("ip:live")
    with SessionLocal() as db:
        assert db.scalars(select(LoginFailure.key)).all() == [LoginRateLimiter.digest("ip:live")]


def test_migration_sqlite_isolated_idempotent(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("mig_loginlim001", _MIG)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.down_revision == "fkidx001"
    eng = create_engine(f"sqlite:///{tmp_path / 'l.db'}")
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.exec_driver_sql("DROP TABLE login_failures")

    def run(fn):
        with eng.connect() as conn:
            monkeypatch.setattr(mig, "op", Operations(MigrationContext.configure(conn)))
            fn()
            conn.commit()

    run(mig.upgrade)
    run(mig.upgrade)   # drugi raz = no-op (create_all bootstrapu mógł założyć tabelę)
    assert {"ix_login_failures_key_created", "ix_login_failures_created_at"} <= {
        ix["name"] for ix in inspect(eng).get_indexes("login_failures")}
    run(mig.downgrade)
    assert not inspect(eng).has_table("login_failures")
    eng.dispose()


def test_account_delay_is_progressive_and_capped(monkeypatch):
    monkeypatch.setattr(settings, "login_account_lock_after", 10)
    monkeypatch.setattr(settings, "login_account_lock_seconds", 30)
    delays = [LoginRateLimiter.account_delay(n) for n in (9, 10, 11, 12, 30)]
    assert delays[0] is None
    assert [d.total_seconds() for d in delays[1:]] == [
        30, 60, 120, settings.login_window_minutes * 60]


@pytest.fixture()
def rotating_ip(monkeypatch):
    """Każde żądanie z innego IP — rozproszony atak (limit pary i IP nie zadziała)."""
    ips = (f"203.0.113.{i}" for i in itertools.count(1))
    monkeypatch.setattr(auth, "_client_ip", lambda _request: next(ips))


def _shift_failures_back(minutes: float) -> None:
    with SessionLocal() as db:
        for row in db.scalars(select(LoginFailure)):
            row.created_at -= datetime.timedelta(minutes=minutes)
        db.commit()


def test_distributed_attack_locks_account_with_retry_after(client, db_session, rotating_ip):
    lock_after = settings.login_account_lock_after
    codes = [client.post("/api/auth/login", data=BAD).status_code for _ in range(lock_after)]
    assert codes == [401] * lock_after      # każda próba z nowego IP — limit pary nie działa
    blocked = client.post("/api/auth/login", data=BAD)
    assert blocked.status_code == 429
    assert 0 < int(blocked.headers["Retry-After"]) <= settings.login_account_lock_seconds
    # w przerwie nawet poprawne hasło nie przechodzi (inaczej przerwa nic nie daje)
    ok = {"username": "admin", "password": "admin123"}   # konto z bootstrapu testów
    assert client.post("/api/auth/login", data=ok).status_code == 429
    # alert: admini dostają powiadomienie „system” raz, przy wejściu w blokadę
    admin = db_session.scalar(select(User).where(User.login == "admin"))
    alerts = db_session.scalars(select(Notification).where(
        Notification.user_id == admin.id, Notification.kind == "system")).all()
    assert len(alerts) == 1 and "admin" in alerts[0].title
    # po przerwie poprawne hasło loguje i zeruje licznik konta
    _shift_failures_back(settings.login_account_lock_seconds / 60 + 0.1)
    assert client.post("/api/auth/login", data=ok).status_code == 200
    assert login_limiter.failures("acct:admin") == 0


def test_lock_does_not_reveal_whether_account_exists(client, rotating_ip):
    ghost = {"username": "nie-ma-takiego", "password": "x" * 12}
    for _ in range(settings.login_account_lock_after):
        assert client.post("/api/auth/login", data=ghost).status_code == 401
    assert client.post("/api/auth/login", data=ghost).status_code == 429


def test_other_account_not_affected(client, db_session, rotating_ip):
    db_session.add(User(login="kolega", hashed_password=hash_password("Kolega-haslo-1"),
                        role=Role.logistics))
    db_session.commit()
    for _ in range(settings.login_account_lock_after):
        client.post("/api/auth/login", data=BAD)
    assert client.post("/api/auth/login", data=BAD).status_code == 429
    assert client.post("/api/auth/login", data={
        "username": "kolega", "password": "Kolega-haslo-1"}).status_code == 200

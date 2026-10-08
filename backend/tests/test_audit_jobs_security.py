"""Audyt backendu: runner pętli tła, maskowanie tokenów, XFF za zaufanym proxy,
limiter 2FA per user + anty-replay TOTP, sprzątanie martwych kluczy limitera."""
import asyncio
import logging
from types import SimpleNamespace

import pytest

from app import jobs
from app.config import settings
from app.main import AvizoTokenLogFilter, _sentry_before_send
from app.security import LoginRateLimiter, client_ip, totp
from tests.conftest import login


# --- 1. runner pętli tła ---

def test_runner_isolates_failing_fn(monkeypatch):
    called = []

    def boom(db):
        called.append("boom")
        raise RuntimeError("x")

    def ok(db):
        called.append("ok")
        return 1

    async def stop(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(jobs.asyncio, "sleep", stop)
    job = jobs.Job("test", 60, (boom, ok))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(jobs.job_loop(job))
    assert called == ["boom", "ok"]


def test_weekly_digest_polled_more_often_than_hourly():
    job = next(j for j in jobs.build_jobs() if j.name == "weekly_digest")
    assert job.interval_s < 3600


def test_customs_bundle_split_into_separate_fns():
    job = next(j for j in jobs.build_jobs() if j.name == "customs_delay")
    assert len(job.fns) == 5
    # SMS do kierowców: osobne zadanie co 15 min (godzina z panelu admina, 2026-09-28)
    sms = next(j for j in jobs.build_jobs() if j.name == "sms_reminders")
    assert sms.interval_s == 15 * 60


# --- 2. maskowanie tokenów ---

TOKEN = "Zx9_" + "a" * 39
PATHS = [
    f"/avizo/{TOKEN}", f"/api/avizo/driver/{TOKEN}", f"/api/public/portal/{TOKEN}",
    f"/api/public/containers/{TOKEN}/docs", f"/api/driver/{TOKEN}", f"/api/dlt/{TOKEN}",
    f"/dostawa/{TOKEN}", f"/portal/{TOKEN}", f"/reset-password?token={TOKEN}",
    f"/api/auth/reset?foo=1&token={TOKEN}&x=2",
]


@pytest.mark.parametrize("path", PATHS)
def test_token_redacted_in_logs_and_sentry(path):
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
                               '%s - "%s %s HTTP/%s" %d',
                               ("1.2.3.4", "GET", path, "1.1", 200), None)
    AvizoTokenLogFilter().filter(record)
    assert TOKEN not in record.getMessage()
    event = {"request": {"url": f"https://app.example{path}", "headers": {}},
             "transaction": path,
             "breadcrumbs": {"values": [{"message": f"GET {path}",
                                         "data": {"url": path}}]}}
    assert TOKEN not in str(_sentry_before_send(event, None))


def test_sentry_scrubs_extra_sensitive_headers_case_insensitive():
    event = {"request": {"headers": {"X-Automation-Token": "s1", "X-API-Key": "s2"},
                         "data": {"totp_secret": "s3", "Pending_Token": "s4"}}}
    out = str(_sentry_before_send(event, None))
    assert not any(s in out for s in ("s1", "s2", "s3", "s4"))


# --- 3. X-Forwarded-For tylko od zaufanego proxy ---

def _req(peer, xff):
    return SimpleNamespace(client=SimpleNamespace(host=peer),
                           headers={"x-forwarded-for": xff})


def test_xff_ignored_from_untrusted_peer():
    assert client_ip(_req("203.0.113.9", "6.6.6.6")) == "203.0.113.9"


def test_xff_used_from_trusted_proxy_peer():
    assert client_ip(_req("172.18.0.5", "1.1.1.1, 198.51.100.7")) == "198.51.100.7"
    assert client_ip(_req("127.0.0.1", "198.51.100.8")) == "198.51.100.8"


def test_xff_ignored_for_non_ip_peer():
    assert client_ip(_req("testclient", "6.6.6.6")) == "testclient"


# --- 4. 2FA: limiter per user + anty-replay ---

def _pending(client):
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    return resp.json()["pending_token"]


def _enable(client):
    headers = login(client)
    secret = client.post("/api/auth/2fa/setup", headers=headers).json()["secret"]
    assert client.post("/api/auth/2fa/enable", headers=headers,
                       json={"secret": secret, "code": totp(secret)}).status_code == 200
    return secret


def test_2fa_per_user_limit_across_ips(client, monkeypatch):
    _enable(client)
    pending = _pending(client)
    from app.routers import auth
    ips = iter(f"198.51.100.{i}" for i in range(1, 50))
    monkeypatch.setattr(auth, "_client_ip", lambda _r: next(ips))
    for _ in range(settings.login_max_attempts):
        r = client.post("/api/auth/2fa/verify", json={"pending_token": pending, "code": "000000"})
        assert r.status_code == 401
    r = client.post("/api/auth/2fa/verify", json={"pending_token": pending, "code": "000000"})
    assert r.status_code == 429


def test_2fa_totp_code_not_replayable(client):
    secret = _enable(client)
    code = totp(secret)
    first = client.post("/api/auth/2fa/verify", json={"pending_token": _pending(client),
                                                       "code": code})
    assert first.status_code == 200, first.text
    again = client.post("/api/auth/2fa/verify", json={"pending_token": _pending(client),
                                                       "code": code})
    assert again.status_code == 401


# --- 5. LoginRateLimiter sprząta martwe klucze ---

def test_login_limiter_sweeps_dead_keys(client, monkeypatch):
    # stan w bazie (ARCH-003): martwe = wiersze starsze niż okno, kasowane co SWEEP_EVERY porażek
    import datetime

    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import LoginFailure
    limiter = LoginRateLimiter()
    now = [datetime.datetime(2026, 9, 28, 12, 0)]
    monkeypatch.setattr("app.rate_limit.utcnow", lambda: now[0])
    for i in range(50):
        limiter.register_failure(f"ip:{i}")
    now[0] += datetime.timedelta(minutes=settings.login_window_minutes, seconds=1)
    for _ in range(LoginRateLimiter.SWEEP_EVERY):
        limiter.register_failure("ip:live")
    with SessionLocal() as db:
        assert set(db.scalars(select(LoginFailure.key))) == {LoginRateLimiter.digest("ip:live")}

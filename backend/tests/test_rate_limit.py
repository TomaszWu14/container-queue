"""Globalny limit żądań API (429) + wspólne wyznaczanie IP klienta."""
from app.config import settings
from app.security import ApiRateLimiter, api_limiter


def test_api_rate_limiter_unit():
    limiter = ApiRateLimiter()
    assert all(limiter.hit("1.2.3.4", limit=3) is None for _ in range(3))
    retry = limiter.hit("1.2.3.4", limit=3)   # 4. żądanie ponad limit
    assert retry is not None and retry > 0
    assert limiter.hit("9.9.9.9", limit=3) is None   # inne IP ma własny licznik


def test_api_rate_limit_returns_429(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "api_rate_limit_per_minute", 5)
    api_limiter._hits.clear()   # czysty licznik dla tego IP
    codes = [client.get("/api/companies", headers=admin_headers).status_code
             for _ in range(8)]
    assert 429 in codes                       # po przekroczeniu limitu
    assert codes.count(200) <= 5              # do limitu przechodzą
    # nagłówek Retry-After na odpowiedzi 429
    resp = client.get("/api/companies", headers=admin_headers)
    assert resp.status_code == 429 and "Retry-After" in resp.headers
    api_limiter._hits.clear()

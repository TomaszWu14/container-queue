"""Nagłówki bezpieczeństwa API i panelu (audyt SEC-011): Permissions-Policy, COOP, HSTS tylko
za HTTPS, działający przycisk „Drukuj” pod CSP i ta sama polityka w nginx panelu dev."""
import base64
import hashlib
import pathlib
import re

from app.config import settings
from app.main import SecurityHeadersMiddleware
from tests.test_complaints_w11 import _company_id, _complaint, _container
from tests.test_notifications import _setup

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_api_sends_permissions_policy_and_coop(client):
    h = client.get("/api/health").headers
    policy = {p.strip() for p in h["permissions-policy"].split(",")}
    # aparat tylko dla własnej domeny (zdjęcia/skaner magazynu), reszta wyłączona
    assert {"camera=(self)", "microphone=()", "geolocation=()"} <= policy
    assert h["cross-origin-opener-policy"] == "same-origin"
    assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in h["content-security-policy"]


def test_hsts_only_behind_https(client, monkeypatch):
    # HSTS na gołym HTTP zablokowałby panel na miesiące — tylko przy SECURE_COOKIES
    monkeypatch.setattr(settings, "secure_cookies", False)
    assert "strict-transport-security" not in client.get("/api/health").headers
    monkeypatch.setattr(settings, "secure_cookies", True)
    assert client.get("/api/health").headers["strict-transport-security"].startswith(
        "max-age=31536000")


def _inline_scripts(html: str) -> list[str]:
    return re.findall(r"<script>(.*?)</script>", html, re.S)


def test_print_button_allowed_by_csp(client, admin_headers):
    # inline onclick="window.print()" blokował CSP script-src 'self' — przycisk nie działał
    cid = _setup(client, admin_headers)["container"]["id"]
    _assert_print_allowed(client.get(f"/api/containers/{cid}/cmr", headers=admin_headers))


def test_complaint_letter_print_button_allowed_by_csp(client, admin_headers):
    # pismo reklamacyjne renderuje szablon Jinja (ARCH-008) — skrypt nie może zostać escapowany
    company = _company_id(client, admin_headers)
    c = _complaint(client, admin_headers, _container(client, admin_headers, "MSDU0806613", company))
    _assert_print_allowed(client.get(f"/api/complaints/{c['id']}/letter", headers=admin_headers))


def _assert_print_allowed(page):
    assert page.status_code == 200
    assert "onclick=" not in page.text and "data-print" in page.text
    csp = page.headers["content-security-policy"]
    scripts = _inline_scripts(page.text)
    assert scripts, "brak skryptu obsługi przycisku druku"
    for body in scripts:
        digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        assert f"'sha256-{digest}'" in csp


def test_no_inline_event_handlers_in_backend_html():
    app = ROOT / "backend" / "app"
    handler = re.compile(r"<[a-z][^>]*\son[a-z]+\s*=", re.I)   # atrybut w znaczniku HTML
    offenders = [f"{p.relative_to(app)}:{no}" for p in sorted(app.rglob("*.py"))
                 for no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if handler.search(line)]
    assert offenders == []


def test_nginx_spa_headers_match_backend():
    # panel z docker-compose (frontend/nginx.conf) dostaje tę samą politykę co z backendu
    conf = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    nginx = dict(re.findall(r'add_header\s+(\S+)\s+"([^"]*)"\s+always;', conf))
    assert nginx == SecurityHeadersMiddleware.HEADERS

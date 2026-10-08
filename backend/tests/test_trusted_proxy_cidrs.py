"""SEC-002: domyślnie ufamy tylko sieci dockera proxy (Traefik Coolify) i localhost.

Pracownik z sieci firmowej 10.x łączący się bezpośrednio NIE może podrobić IP
nagłówkiem X-Forwarded-For (obejście limitu logowań, blokady IP, audytu)."""
import re
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.rate_limit import client_ip

DEFAULT = Settings.model_fields["trusted_proxy_cidrs"].default


def _req(peer, xff):
    return SimpleNamespace(client=SimpleNamespace(host=peer),
                           headers={"x-forwarded-for": xff})


def test_corporate_peer_cannot_spoof_xff(monkeypatch):
    monkeypatch.setattr("app.rate_limit.settings.trusted_proxy_cidrs", DEFAULT)
    assert client_ip(_req("192.0.2.50", "1.2.3.4")) == "192.0.2.50"
    assert client_ip(_req("172.18.0.2", "1.2.3.4")) == "1.2.3.4"
    assert client_ip(_req("127.0.0.1", "1.2.3.4")) == "1.2.3.4"


def test_uvicorn_uses_same_cidrs_as_app():
    """Dockerfile: --forwarded-allow-ips z TRUSTED_PROXY_CIDRS, z tym samym domyślnym."""
    root = Path(__file__).resolve().parents[2]
    cmd = (root / "Dockerfile.coolify").read_text(encoding="utf-8")
    m = re.search(r'--forwarded-allow-ips=\\?"\$\{TRUSTED_PROXY_CIDRS:-([^}]+)\}', cmd)
    assert m, "uvicorn musi brać --forwarded-allow-ips z TRUSTED_PROXY_CIDRS"
    assert m.group(1) == DEFAULT
    compose = (root / "docker-compose.coolify.yml").read_text(encoding="utf-8")
    assert f"TRUSTED_PROXY_CIDRS: ${{TRUSTED_PROXY_CIDRS:-{DEFAULT}}}" in compose


def test_invalid_cidr_entry_is_ignored_not_crashing(monkeypatch):
    """Błędna wartość w Coolify (TRUSTED_PROXY_CIDRS=1) nie może dawać 500 na każdym żądaniu."""
    from app import rate_limit
    monkeypatch.setattr(rate_limit.settings, "trusted_proxy_cidrs", "1,172.16.0.0/12")
    assert rate_limit._is_trusted_proxy("172.18.0.2") is True
    assert rate_limit._is_trusted_proxy("192.0.2.50") is False

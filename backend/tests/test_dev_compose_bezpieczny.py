"""BUILD-006: dev docker-compose.yml i frontend/Dockerfile nie mogą wystawiać
portów na wszystkie interfejsy, mieć gotowych haseł ani ignorować lockfile."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_porty_tylko_na_localhost():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    ports = [str(p) for s in compose["services"].values() for p in s.get("ports", [])]
    assert ports, "brak portów w docker-compose.yml?"
    assert all(p.startswith("127.0.0.1:") for p in ports), ports


def test_brak_domyslnych_hasel():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for zakazane in ("admin123", "change-me", "POSTGRES_PASSWORD:-", "postgres:postgres"):
        assert zakazane not in text, zakazane


def test_frontend_npm_ci_z_lockfile():
    if not (ROOT / "frontend" / "package-lock.json").exists():
        return
    docker = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert "package-lock.json" in docker
    assert "npm ci" in docker and "npm install" not in docker

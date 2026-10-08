"""Instancja portfolio: konto demo tylko do odczytu (egzekwowane w API), podpowiedź logowania,
bezpieczniki skryptu scripts/seed_demo.py (kasuje wszystko — tylko na instancji pokazowej, z flagą)."""
import pytest

from app.config import settings
from app.models import Role, User
from app.security import hash_password
from scripts import seed_demo

from .conftest import login

PW = "Demo-Portfolio-2026"


def test_demo_account_reads_but_cannot_write(client, db_session, monkeypatch, admin_headers):
    monkeypatch.setattr(settings, "demo_readonly_logins", "demo")
    db_session.add(User(login="demo", hashed_password=hash_password(PW), role=Role.logistics,
                        view_all_companies=True))
    db_session.commit()
    hdr = login(client, "demo", PW)
    assert client.get("/api/containers", headers=hdr).status_code == 200
    r = client.patch("/api/auth/me/settings", headers=hdr, json={"language": "en"})
    assert r.status_code == 403 and "demo" in r.json()["detail"]
    assert client.post("/api/containers", headers=hdr, json={"container_no": "MSKU1234565"}).status_code == 403
    assert client.post("/api/auth/logout", headers=hdr).status_code in (200, 204)
    # zwykłe konto na tej samej instancji zapisuje normalnie
    assert client.patch("/api/auth/me/settings", headers=admin_headers,
                        json={"language": "pl"}).status_code != 403


def test_branding_exposes_demo_hint_only_when_set(client, monkeypatch):
    assert client.get("/api/public/branding").json()["demo_hint"] == ""
    monkeypatch.setattr(settings, "demo_login_hint", "demo / Demo-Portfolio-2026")
    assert client.get("/api/public/branding").json()["demo_hint"] == "demo / Demo-Portfolio-2026"


def test_seed_refuses_without_demo_instance_or_flag(monkeypatch):
    monkeypatch.setattr(settings, "demo_readonly_logins", "")
    with pytest.raises(SystemExit, match="nie jest instancja pokazowa"):
        seed_demo.check_guards(["--wyczysc-wszystko"])
    monkeypatch.setattr(settings, "demo_readonly_logins", "demo")
    with pytest.raises(SystemExit, match="brak flagi"):
        seed_demo.check_guards([])
    assert seed_demo.check_guards(["--wyczysc-wszystko"]) == ["demo"]

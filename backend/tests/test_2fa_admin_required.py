"""Audyt SEC-006: 2FA obowiązkowe dla administratorów (REQUIRE_2FA_ADMIN, domyślnie wyłączone)
i dostępne dla wszystkich ról. Admin bez 2FA czyta, ale nic nie zmieni poza własnym kontem
(/api/auth/*), dopóki nie włączy 2FA. Testy domyślnie mają wymóg wyłączony (conftest)."""
import pytest

from app.config import settings
from app.security import totp
from tests.conftest import login


@pytest.fixture()
def require_2fa(monkeypatch):
    monkeypatch.setattr(settings, "require_2fa_admin", True)


def _enable(client, headers) -> str:
    setup = client.post("/api/auth/2fa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    enable = client.post("/api/auth/2fa/enable", headers=headers,
                         json={"secret": secret, "code": totp(secret)})
    assert enable.status_code == 200, enable.text
    return secret


def test_default_setting_does_not_require_2fa_for_admin():
    # decyzja właściciela 2026-09-29: wymóg włącza się jawnie REQUIRE_2FA_ADMIN=true
    from app.config import Settings
    assert Settings.model_fields["require_2fa_admin"].default is False


def test_admin_without_2fa_blocked_from_mutations_until_enrolled(client, require_2fa):
    headers = login(client)
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["must_enroll_2fa"] is True
    assert client.get("/api/containers", headers=headers).status_code == 200   # odczyt działa
    blocked = client.post("/api/companies", headers=headers,
                          json={"code": "NOWA2FA", "name": "Nowa 2FA"})
    assert blocked.status_code == 403
    assert "2FA" in blocked.json()["detail"]

    _enable(client, headers)                    # /api/auth/2fa/* przepuszczone mimo blokady
    assert client.get("/api/auth/me", headers=headers).json()["must_enroll_2fa"] is False
    assert client.post("/api/companies", headers=headers,
                       json={"code": "NOWA2FA", "name": "Nowa 2FA"}).status_code == 201


def test_requirement_only_for_admin_role(client, admin_headers, monkeypatch):
    user = {"login": "logi.sec6", "password": "haslo1234", "role": "logistics",
            "view_all_companies": True}
    assert client.post("/api/users", headers=admin_headers, json=user).status_code == 201
    logistics = login(client, "logi.sec6", "haslo1234")
    monkeypatch.setattr(settings, "require_2fa_admin", True)
    assert client.get("/api/auth/me", headers=logistics).json()["must_enroll_2fa"] is False
    # pusty formularz: logistyka przechodzi uwierzytelnienie i dostaje 422 z walidacji,
    # admin bez 2FA odpada wcześniej — 403
    assert client.post("/api/containers", headers=logistics, json={}).status_code == 422
    assert client.post("/api/containers", headers=admin_headers, json={}).status_code == 403


def test_2fa_available_for_non_admin_roles(client, admin_headers):
    assert client.post("/api/users", headers=admin_headers, json={
        "login": "sped.sec6", "password": "haslo1234", "role": "logistics",
        "view_all_companies": True}).status_code == 201
    headers = login(client, "sped.sec6", "haslo1234")
    secret = _enable(client, headers)
    first = client.post("/api/auth/login", data={"username": "sped.sec6", "password": "haslo1234"})
    assert first.json().get("totp_required") is True
    ok = client.post("/api/auth/2fa/verify",
                     json={"pending_token": first.json()["pending_token"], "code": totp(secret)})
    assert ok.status_code == 200, ok.text

"""Audyt ACL-005: konto serwisowe n8n — ograniczenie skutków wycieku tokenu.
Rola admin zabroniona, logowanie hasłem zablokowane, opcjonalne sieci i termin ważności,
rotacja bez przestoju (poprzedni token akceptowany w okresie przejściowym)."""
import datetime

from app.config import settings
from tests.test_automation import TOKEN, automation, service_account  # noqa: F401 — fixture

NEW_TOKEN = "nowy-token-automatyzacji-min-32-znaki-xyz"


def _service(client, admin_headers, role="logistics"):
    response = client.post("/api/users", headers=admin_headers, json={
        "login": "n8n", "password": "haslo-serwisowe-123", "role": role,  # gitleaks:allow — fikstura
        "view_all_companies": role != "admin"})
    assert response.status_code == 201, response.text


def test_admin_service_account_rejected(client, admin_headers, monkeypatch):
    _service(client, admin_headers, role="admin")
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    response = automation(client)
    assert response.status_code == 403
    assert "admin" in response.json()["detail"]


def test_password_login_blocked_for_service_account(client, service_account, monkeypatch):
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    response = client.post("/api/auth/login", data={
        "username": "n8n", "password": "haslo-serwisowe-123"})  # gitleaks:allow — fikstura
    assert response.status_code == 401


def test_previous_token_accepted_during_rotation(client, service_account, monkeypatch):
    monkeypatch.setattr(settings, "automation_api_token", NEW_TOKEN)
    monkeypatch.setattr(settings, "automation_api_token_previous", TOKEN)
    assert automation(client, token=NEW_TOKEN).status_code == 200
    assert automation(client, token=TOKEN).status_code == 200
    monkeypatch.setattr(settings, "automation_api_token_previous", "")
    assert automation(client, token=TOKEN).status_code == 401


def test_token_expiry(client, service_account, monkeypatch):
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    monkeypatch.setattr(settings, "automation_token_expires",
                        (datetime.date.today() + datetime.timedelta(days=2)).isoformat())
    assert automation(client).status_code == 200
    monkeypatch.setattr(settings, "automation_token_expires",
                        (datetime.date.today() - datetime.timedelta(days=2)).isoformat())
    expired = automation(client)
    assert expired.status_code == 401 and "wygasł" in expired.json()["detail"]


def test_allowed_cidrs(client, service_account, monkeypatch):
    from app import automation_policy
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    monkeypatch.setattr(settings, "automation_allowed_cidrs", "10.0.0.0/8, 172.16.0.0/12")
    monkeypatch.setattr(automation_policy, "client_ip", lambda request: "203.0.113.7")
    assert automation(client).status_code == 403
    monkeypatch.setattr(automation_policy, "client_ip", lambda request: "172.18.0.5")
    assert automation(client).status_code == 200

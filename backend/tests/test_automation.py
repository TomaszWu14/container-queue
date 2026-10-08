"""Integracja z n8n: token serwisowy (wejście) + webhook zdarzeń (wyjście).

Token serwisowy celowo NIE ma własnej ścieżki autoryzacji — mapuje się na konto
użytkownika, więc obowiązują te same role i izolacja per zasób co dla ludzi.
"""
import json
import threading

import pytest

from app import notifications as N
from app.config import settings
from app.security import AUTOMATION_HEADER

TOKEN = "test-automation-token-at-least-32-chars"


def automation(client, token=TOKEN):
    """Żądanie „jak z n8n": wyłącznie nagłówek tokenu, bez cookies sesji.

    TestClient trzyma cookies z logowania admina (fixture `admin_headers`), więc bez
    ich wyczyszczenia test przechodziłby na cudzej sesji, a nie na tokenie.
    """
    client.cookies.clear()
    return client.get("/api/containers", headers={AUTOMATION_HEADER: token})


@pytest.fixture()
def service_account(client, admin_headers):
    """Konto serwisowe „n8n" z rolą logistics (jak zaleca docs/N8N.md)."""
    response = client.post("/api/users", headers=admin_headers, json={
        "login": "n8n", "password": "haslo-serwisowe-123", "role": "logistics",
        "view_all_companies": True})
    assert response.status_code == 201, response.text
    return response.json()


def test_token_opens_api_without_login(client, service_account, monkeypatch):
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    response = automation(client)
    assert response.status_code == 200, response.text


def test_wrong_token_rejected(client, service_account, monkeypatch):
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    response = automation(client, token="zle")
    assert response.status_code == 401


def test_non_ascii_token_header_is_rejected_not_500(client, service_account, monkeypatch):
    """Nagłówek z bajtem non-ASCII nie może wywalić serwera (porównanie na bajtach).

    Bajty >127 podajemy wprost: Starlette dekoduje nagłówki jako latin-1, więc do
    porównania trafiłby str z non-ASCII — na `str` compare_digest rzuca TypeError (500).
    """
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    response = automation(client, token=b"\xff-token")
    assert response.status_code == 401


def test_token_ignored_when_integration_disabled(client, service_account, monkeypatch):
    """Puste AUTOMATION_API_TOKEN = kanał wyłączony, nagłówek nic nie otwiera."""
    monkeypatch.setattr(settings, "automation_api_token", "")
    response = automation(client)
    assert response.status_code == 401


def test_missing_service_account_gives_403(client, monkeypatch):
    """Poprawny token bez istniejącego konta serwisowego nie wpuszcza „anonimowo"."""
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    response = automation(client)
    assert response.status_code == 403


def test_deactivated_service_account_is_cut_off(client, admin_headers, service_account,
                                                monkeypatch):
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    client.patch(f"/api/users/{service_account['id']}", headers=admin_headers,
                 json={"is_active": False})
    response = automation(client)
    assert response.status_code == 403


def test_role_limits_what_automation_can_do(client, admin_headers, monkeypatch):
    """Rola konta serwisowego wyznacza zakres — magazyn nie zakłada kontenerów."""
    client.post("/api/users", headers=admin_headers, json={
        "login": "n8n-ro", "password": "haslo-serwisowe-123", "role": "warehouse"})
    monkeypatch.setattr(settings, "automation_api_token", TOKEN)
    monkeypatch.setattr(settings, "automation_actor_login", "n8n-ro")
    companies = client.get("/api/companies", headers=admin_headers).json()
    client.cookies.clear()
    response = client.post("/api/containers", headers={AUTOMATION_HEADER: TOKEN},
                           json={"container_no": "MSDU0806613",
                                 "company_id": companies[0]["id"]})
    assert response.status_code == 403


def test_event_signed_and_offloaded(monkeypatch):
    done = threading.Event()
    box: dict[str, object] = {}

    def fake_post(url, content, headers, timeout):
        box.update(url=url, content=content, headers=headers,
                   thread=threading.current_thread().name)
        done.set()

    monkeypatch.setattr(N.settings, "automation_webhook_url", "https://n8n.example.com/webhook/x")
    monkeypatch.setattr(N.settings, "automation_webhook_secret", "sekret-webhooka")
    monkeypatch.setattr(N.httpx, "post", fake_post)

    N.send_automation_event("demurrage", "Tytuł", "treść", container_id=7)
    assert done.wait(3), "zdarzenie nie poszło w tle"

    assert box["url"] == "https://n8n.example.com/webhook/x"
    assert str(box["thread"]).startswith("notify")
    payload = json.loads(box["content"])
    assert payload["event"] == "demurrage" and payload["container_id"] == 7
    assert payload["title"] == "Tytuł" and payload["sent_at"]
    # podpis liczony z DOKŁADNIE tych bajtów, które poszły w ciele
    expected = N.sign_payload(box["content"], "sekret-webhooka")
    assert box["headers"]["X-Timporye-Signature"] == expected


def test_event_skipped_without_url(monkeypatch):
    monkeypatch.setattr(N.settings, "automation_webhook_url", "")
    calls = []
    monkeypatch.setattr(N, "_n8n_post", lambda *a, **k: calls.append(1))
    N.send_automation_event("demurrage", "Tytuł")
    assert calls == []


def test_event_unsigned_when_secret_empty(monkeypatch):
    done = threading.Event()
    box: dict[str, object] = {}

    def fake_post(url, content, headers, timeout):
        box["headers"] = headers
        done.set()

    monkeypatch.setattr(N.settings, "automation_webhook_url", "https://n8n.example.com/webhook/x")
    monkeypatch.setattr(N.settings, "automation_webhook_secret", "")
    monkeypatch.setattr(N.httpx, "post", fake_post)
    N.send_automation_event("demurrage", "Tytuł")
    assert done.wait(3)
    assert "X-Timporye-Signature" not in box["headers"]

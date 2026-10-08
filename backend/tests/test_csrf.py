"""SEC-004: zapis uwierzytelniony ciasteczkiem tylko z naszego frontu (Origin / X-Requested-With)."""
import pytest

from tests.conftest import login

PREFS = "/api/auth/me/prefs"
EVIL = "https://evil.example"


@pytest.fixture()
def cookie_client(client):
    """Klient z ciasteczkiem sesji po logowaniu — bez nagłówka Authorization."""
    login(client)
    assert "timporye_access" in client.cookies
    return client


def test_foreign_origin_with_cookie_rejected(cookie_client):
    r = cookie_client.put(PREFS, json={"density": "compact"}, headers={"Origin": EVIL})
    assert r.status_code == 403
    assert r.json()["detail"] == "Niedozwolone źródło żądania."
    assert cookie_client.post("/api/auth/logout", headers={"Origin": EVIL}).status_code == 403


def test_foreign_referer_and_null_origin_rejected(cookie_client):
    assert cookie_client.put(PREFS, json={}, headers={"Referer": f"{EVIL}/x"}).status_code == 403
    assert cookie_client.put(PREFS, json={}, headers={"Origin": "null"}).status_code == 403


def test_same_site_other_port_rejected(cookie_client):
    """Inna usługa na tym samym hoście (inny port) to ten sam „site” — też odrzucona."""
    r = cookie_client.put(PREFS, json={}, headers={"Origin": "http://testserver:8000"})
    assert r.status_code == 403


def test_own_origin_passes(cookie_client):
    r = cookie_client.put(PREFS, json={"density": "compact"},
                          headers={"Origin": "http://testserver"})
    assert r.status_code == 200
    assert cookie_client.get(PREFS).json() == {"density": "compact"}


def test_public_base_url_origin_passes(cookie_client, monkeypatch):
    """Za proxy Host bywa bez portu ($host) — adres z PUBLIC_BASE_URL jest wtedy źródłem prawdy."""
    from app.config import settings
    monkeypatch.setattr(settings, "public_base_url", "http://10.0.0.5:81/")
    r = cookie_client.put(PREFS, json={}, headers={"Origin": "http://10.0.0.5:81"})
    assert r.status_code == 200


def test_frontend_header_passes_regardless_of_origin(cookie_client):
    """Front wysyła X-Requested-With — obca strona nie doda go bez preflightu CORS."""
    r = cookie_client.put(PREFS, json={},
                          headers={"Origin": "http://localhost:5173", "X-Requested-With": "fetch"})
    assert r.status_code == 200


def test_bearer_and_non_browser_clients_pass(client):
    headers = login(client)
    client.cookies.clear()
    r = client.put(PREFS, json={}, headers={**headers, "Origin": EVIL})
    assert r.status_code == 200                      # Bearer: brak ambientnych poświadczeń
    login(client)
    assert client.put(PREFS, json={}).status_code == 200   # bez Origin/Referer: nie przeglądarka


def test_safe_methods_and_anonymous_not_checked(cookie_client, client):
    assert cookie_client.get(PREFS, headers={"Origin": EVIL}).status_code == 200
    client.cookies.clear()
    r = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"},
                    headers={"Origin": EVIL})
    assert r.status_code == 200                      # bez ciasteczka sesji nie ma czego chronić

"""Audyt SEC-007: konto z hasłem tymczasowym (zaproszenie / reset przez admina) do czasu
ustawienia własnego hasła może tylko odczytać siebie, zmienić hasło i się wylogować —
blokada egzekwowana w API, nie tylko ekranem w panelu."""
from tests.conftest import login


def _invite(client, admin_headers, name):
    resp = client.post("/api/users", headers=admin_headers, json={
        "login": name, "email": f"{name}@example.com", "role": "logistics",
        "view_all_companies": True, "send_invite": True})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_temp_password_account_limited_to_password_change(client, admin_headers):
    temp = _invite(client, admin_headers, "zaproszony.sec7")["temp_password"]
    hdr = login(client, "zaproszony.sec7", temp)
    assert client.get("/api/containers", headers=hdr).status_code == 403
    assert client.get("/api/companies", headers=hdr).status_code == 403
    assert client.patch("/api/auth/me/settings", headers=hdr, json={}).status_code == 403
    me = client.get("/api/auth/me", headers=hdr)
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    assert client.get("/api/auth/me/prefs", headers=hdr).status_code == 200

    changed = client.post("/api/auth/change-password", headers=hdr,
                          json={"new_password": "WlasneHaslo123!"})
    assert changed.status_code == 200, changed.text
    fresh = login(client, "zaproszony.sec7", "WlasneHaslo123!")
    assert client.get("/api/containers", headers=fresh).status_code == 200


def test_admin_password_reset_also_blocks_until_change(client, admin_headers):
    uid = client.post("/api/users", headers=admin_headers, json={
        "login": "reset.sec7", "password": "haslo1234", "role": "logistics",
        "view_all_companies": True}).json()["id"]
    assert client.patch(f"/api/users/{uid}", headers=admin_headers,
                        json={"password": "tymczas123"}).status_code == 200
    hdr = login(client, "reset.sec7", "tymczas123")
    assert client.get("/api/containers", headers=hdr).status_code == 403
    assert client.post("/api/auth/change-password", headers=hdr,
                       json={"new_password": "noweHaslo123"}).status_code == 200

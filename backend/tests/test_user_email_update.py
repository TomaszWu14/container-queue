"""#4 — e-mail edytowalny w panelu admina: walidacja formatu przy PATCH /api/users/{id}."""


def _create_user(client, admin_headers, login_name="user.email.test"):
    resp = client.post("/api/users", headers=admin_headers, json={
        "login": login_name, "password": "haslo123", "role": "logistics",
        "view_all_companies": True, "email": "start@example.com"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_patch_updates_email(client, admin_headers):
    uid = _create_user(client, admin_headers)
    resp = client.patch(f"/api/users/{uid}", headers=admin_headers,
                        json={"email": "nowy@example.com"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "nowy@example.com"


def test_patch_rejects_bad_email(client, admin_headers):
    uid = _create_user(client, admin_headers, "user.email.bad")
    resp = client.patch(f"/api/users/{uid}", headers=admin_headers,
                        json={"email": "to-nie-email"})
    assert resp.status_code == 422, resp.text


def test_patch_empty_email_allowed(client, admin_headers):
    """Pusty e-mail jest dozwolony (konto bez adresu — reset hasła po prostu nie zadziała)."""
    uid = _create_user(client, admin_headers, "user.email.empty")
    resp = client.patch(f"/api/users/{uid}", headers=admin_headers, json={"email": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == ""


def test_patch_without_email_keeps_current(client, admin_headers):
    """Pominięcie pola e-mail nie kasuje istniejącego adresu."""
    uid = _create_user(client, admin_headers, "user.email.keep")
    resp = client.patch(f"/api/users/{uid}", headers=admin_headers,
                        json={"full_name": "Zmiana Nazwiska"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "start@example.com"

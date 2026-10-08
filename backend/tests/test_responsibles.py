"""S10 (audyt UI 2026-09-27): lekka lista osób do pola „Odpowiedzialny” w Specjalnej
trosce — logistyka jej używa, /api/users zostaje tylko dla admina."""
from tests.conftest import forwarder, login


def _user(client, admin_headers, name, role, company_id, **extra):
    r = client.post("/api/users", headers=admin_headers, json={
        "login": name, "password": "haslo123", "role": role, "company_id": company_id,
        "full_name": name.upper(), "email": f"{name}@example.com", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_responsibles_minimal_fields_and_scope(client, admin_headers):
    companies = client.get("/api/companies", headers=admin_headers).json()
    own, other = companies[0]["id"], companies[1]["id"]
    _user(client, admin_headers, "resp.log", "logistics", own)
    _user(client, admin_headers, "resp.buy", "purchasing", own)
    _user(client, admin_headers, "resp.other", "logistics", other)
    gone = _user(client, admin_headers, "resp.gone", "logistics", own)
    assert client.patch(f"/api/users/{gone['id']}", headers=admin_headers,
                        json={"is_active": False}).status_code == 200
    fwd = forwarder(client, admin_headers, "RESP-SPEDALFA")
    _user(client, admin_headers, "resp.fwd", "forwarder", None, forwarder_id=fwd["id"])

    log_h = login(client, "resp.log", "haslo123")
    rows = client.get("/api/customer-orders/responsibles", headers=log_h).json()
    names = {r["name"] for r in rows}
    assert {"RESP.LOG", "RESP.BUY"} <= names
    # inna spółka, konto nieaktywne i firma zewnętrzna — poza listą
    assert not names & {"RESP.OTHER", "RESP.GONE", "RESP.FWD"}
    # bez e-maili, ról, 2FA — tylko id + imię i nazwisko
    assert all(set(r) == {"id", "name"} for r in rows)
    # pełna lista użytkowników nadal tylko dla admina
    assert client.get("/api/users", headers=log_h).status_code == 403

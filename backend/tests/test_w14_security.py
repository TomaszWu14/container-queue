"""W14: 2FA TOTP (wektory RFC 6238), sesje, polityka haseł, BlockedIP, beacon,
impersonacja read-only, uprawnienia per magazyn, panel System, weryfikacja backupu."""
import base64
import json

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import AuditLog, Company, Container, User, Warehouse
from app.security import (
    generate_totp_secret,
    hotp,
    totp,
    validate_password_policy,
    verify_totp,
)
from tests.conftest import login

# --- TOTP: wektory testowe RFC 6238 (Appendix B, SHA-1, 8 cyfr) ---

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()
RFC_VECTORS = [(59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
               (1234567890, "89005924"), (2000000000, "69279037"),
               (20000000000, "65353130")]


def test_totp_rfc6238_vectors():
    for t, expected in RFC_VECTORS:
        assert totp(RFC_SECRET, at=t, digits=8) == expected


def test_hotp_rfc4226_vector():
    # RFC 4226 Appendix D: counter=0 → 755224
    assert hotp(RFC_SECRET, 0) == "755224"


def test_verify_totp_window_and_constant_time():
    secret = generate_totp_secret()
    code = totp(secret, at=1_000_000)
    assert verify_totp(secret, code, at=1_000_000)
    assert verify_totp(secret, code, at=1_000_000 + 30)   # ±1 krok tolerancji
    assert not verify_totp(secret, code, at=1_000_000 + 120)
    assert not verify_totp(secret, "000000", at=1_000_000)


def test_2fa_enable_invalid_base32_secret_is_400(client):
    """Sekret spoza alfabetu base32 → 400 „Nieprawidłowy kod", nie 500."""
    headers = login(client)
    resp = client.post("/api/auth/2fa/enable", headers=headers,
                       json={"secret": "abcdefgh!!!!!!!!", "code": "123456"})
    assert resp.status_code == 400, resp.text


# --- 2FA: pełny przepływ logowania ---

def _enable_2fa(client, headers):
    setup = client.post("/api/auth/2fa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert "otpauth://totp/" in setup.json()["otpauth_url"]
    enable = client.post("/api/auth/2fa/enable", headers=headers,
                         json={"secret": secret, "code": totp(secret)})
    assert enable.status_code == 200, enable.text
    codes = enable.json()["backup_codes"]
    assert len(codes) == 10
    return secret, codes


def test_2fa_flow_login_requires_code(client):
    headers = login(client)
    secret, codes = _enable_2fa(client, headers)
    # logowanie hasłem nie wydaje już tokenów — zwraca pending
    resp = client.post("/api/auth/login",
                       data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("totp_required") is True
    pending = body["pending_token"]
    # zły kod → 401 + audyt login_failed
    bad = client.post("/api/auth/2fa/verify",
                      json={"pending_token": pending, "code": "000000"})
    assert bad.status_code == 401
    # poprawny kod TOTP → tokeny
    ok = client.post("/api/auth/2fa/verify",
                     json={"pending_token": pending, "code": totp(secret)})
    assert ok.status_code == 200, ok.text
    assert ok.json()["access_token"]
    # kod zapasowy działa raz
    resp2 = client.post("/api/auth/login",
                        data={"username": "admin", "password": "admin123"})
    pending2 = resp2.json()["pending_token"]
    first = client.post("/api/auth/2fa/verify",
                        json={"pending_token": pending2, "code": codes[0]})
    assert first.status_code == 200
    resp3 = client.post("/api/auth/login",
                        data={"username": "admin", "password": "admin123"})
    again = client.post("/api/auth/2fa/verify",
                        json={"pending_token": resp3.json()["pending_token"],
                              "code": codes[0]})
    assert again.status_code == 401  # zużyty


def test_2fa_setup_available_for_all_roles(client, admin_headers):
    # SEC-006: 2FA nie tylko dla admina (wcześniej logistyka dostawała 403)
    client.post("/api/users", headers=admin_headers,
                json={"login": "logi2fa", "password": "haslo1234", "role": "logistics",
                      "view_all_companies": True})
    h = login(client, "logi2fa", "haslo1234")
    assert client.post("/api/auth/2fa/setup", headers=h).status_code == 200


def test_2fa_disable_only_other_admin(client):
    headers = login(client)
    _enable_2fa(client, headers)
    with SessionLocal() as db:
        me = db.scalar(select(User).where(User.login == "admin"))
        my_id = me.id
    # samemu sobie nie można
    assert client.post(f"/api/users/{my_id}/2fa/disable",
                       headers=headers).status_code == 400
    # drugi admin może
    client.post("/api/users", headers=headers,
                json={"login": "admin2", "password": "haslo1234", "role": "admin"})
    h2 = login(client, "admin2", "haslo1234")
    resp = client.post(f"/api/users/{my_id}/2fa/disable", headers=h2)
    assert resp.status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.login == "admin")).totp_secret is None
        assert db.scalar(select(AuditLog).where(AuditLog.field == "2fa_disabled"))


# --- #88 sesje aktywne ---

def test_sessions_list_and_revoke(client, admin_headers):
    login(client)  # druga sesja (refresh token)
    sessions = client.get("/api/auth/sessions", headers=admin_headers).json()
    assert len(sessions) >= 2
    sid = sessions[0]["id"]
    assert client.delete(f"/api/auth/sessions/{sid}",
                         headers=admin_headers).status_code == 204
    left = client.get("/api/auth/sessions", headers=admin_headers).json()
    assert all(s["id"] != sid for s in left)
    assert client.post("/api/auth/sessions/revoke-others",
                       headers=admin_headers).status_code == 204


def test_admin_sees_and_revokes_user_sessions(client, admin_headers):
    client.post("/api/users", headers=admin_headers,
                json={"login": "sesuser", "password": "haslo1234", "role": "logistics",
                      "view_all_companies": True})
    login(client, "sesuser", "haslo1234")
    with SessionLocal() as db:
        uid = db.scalar(select(User).where(User.login == "sesuser")).id
    sessions = client.get(f"/api/users/{uid}/sessions", headers=admin_headers).json()
    assert len(sessions) == 1
    resp = client.delete(f"/api/users/{uid}/sessions/{sessions[0]['id']}",
                         headers=admin_headers)
    assert resp.status_code == 204
    assert client.get(f"/api/users/{uid}/sessions", headers=admin_headers).json() == []


# --- #89 polityka haseł ---

def test_password_policy(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "password_min_length", 12)
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        validate_password_policy("krotkie1")           # za krótkie
    with pytest.raises(HTTPException):
        validate_password_policy("samelitery" * 2)     # bez cyfry
    with pytest.raises(HTTPException):
        validate_password_policy("123456789012345")    # bez litery
    validate_password_policy("poprawnehaslo1")
    # zmiana własnego hasła egzekwuje politykę
    resp = client.post("/api/auth/change-password", headers=admin_headers,
                       json={"current_password": "admin123", "new_password": "krotkie1"})
    assert resp.status_code == 422


def test_admin_password_reset_forces_change(client, admin_headers):
    created = client.post("/api/users", headers=admin_headers,
                          json={"login": "resetme", "password": "haslo1234",
                                "role": "logistics", "view_all_companies": True})
    uid = created.json()["id"]
    resp = client.patch(f"/api/users/{uid}", headers=admin_headers,
                        json={"password": "nowehaslo1"})
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is True


# --- #90 BlockedIP ---

def test_blocked_ip_gets_403_before_rate_limit(client, admin_headers, monkeypatch):
    # TestClient łączy się jako peer "testclient" — udajemy zaufane proxy, żeby XFF działał
    monkeypatch.setattr("app.rate_limit._is_trusted_proxy", lambda _host: True)
    resp = client.post("/api/admin/blocked-ips", headers=admin_headers,
                       json={"ip": "10.9.9.9", "note": "test"})
    assert resp.status_code == 201
    blocked = client.post("/api/auth/login",
                          data={"username": "admin", "password": "admin123"},
                          headers={"X-Forwarded-For": "10.9.9.9"})
    assert blocked.status_code == 403
    # odblokowanie przywraca logowanie
    bid = resp.json()["id"]
    client.delete(f"/api/admin/blocked-ips/{bid}", headers=admin_headers)
    ok = client.post("/api/auth/login",
                     data={"username": "admin", "password": "admin123"},
                     headers={"X-Forwarded-For": "10.9.9.9"})
    assert ok.status_code == 200


def test_auth_log_endpoint(client, admin_headers):
    rows = client.get("/api/admin/auth-log", headers=admin_headers).json()
    assert any(r["field"] == "login" for r in rows)
    none = client.get("/api/admin/auth-log?q=nieistnieje", headers=admin_headers).json()
    assert none == []


# --- #50 beacon błędów klienta ---

def test_client_error_beacon_and_rate_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "client_error_rate_per_minute", 3)
    payload = {"name": "TypeError", "message": "x is null", "stack": "at foo",
               "url": "/kolejka"}
    for _ in range(3):
        assert client.post("/api/client-error", json=payload).status_code == 202
    assert client.post("/api/client-error", json=payload).status_code == 429
    # walidacja rozmiaru
    big = dict(payload, message="x" * 3000)
    monkeypatch.setattr(settings, "client_error_rate_per_minute", 100)
    assert client.post("/api/client-error", json=big).status_code == 422


# --- #87 impersonacja read-only ---

def test_impersonation_readonly_and_audited(client, admin_headers):
    with SessionLocal() as db:
        company_id = db.scalar(select(Company.id))
    resp = client.post("/api/admin/impersonate", headers=admin_headers,
                       json={"role": "logistics", "company_id": company_id})
    assert resp.status_code == 200
    imp_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = client.get("/api/auth/me", headers=imp_headers)
    assert me.status_code == 200
    assert me.json()["impersonated"] is True
    assert me.json()["role"] == "logistics"
    # GET przechodzi, mutacje 403
    assert client.get("/api/containers", headers=imp_headers).status_code == 200
    post = client.post("/api/containers", headers=imp_headers,
                       json={"container_no": "IMPU1234567"})
    assert post.status_code == 403
    patch = client.patch("/api/users/1", headers=imp_headers, json={"full_name": "x"})
    assert patch.status_code == 403
    with SessionLocal() as db:
        gets = db.scalars(select(AuditLog).where(
            AuditLog.entity_type == "impersonation", AuditLog.field == "get")).all()
        assert gets  # każdy GET w podglądzie zostawia ślad z prawdziwym adminem
        assert all(g.user_id is not None for g in gets)
        assert db.scalar(select(AuditLog).where(
            AuditLog.entity_type == "impersonation", AuditLog.field == "start"))


def test_impersonation_token_dies_after_admin_demotion(client, admin_headers):
    """Audyt 2026-09-23: zdegradowany admin nie zachowuje podglądu „jako admin"."""
    created = client.post("/api/users", headers=admin_headers, json={
        "login": "admin2", "password": "haslo1234", "role": "admin",
        "view_all_companies": True})
    assert created.status_code == 201, created.text
    resp = client.post("/api/admin/impersonate", headers=login(client, "admin2", "haslo1234"),
                       json={"role": "admin"})
    imp_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    assert client.get("/api/containers", headers=imp_headers).status_code == 200
    assert client.patch(f"/api/users/{created.json()['id']}", headers=admin_headers,
                        json={"role": "logistics"}).status_code == 200
    assert client.get("/api/containers", headers=imp_headers).status_code == 401


# --- #91 uprawnienia per magazyn ---

def test_logistics_scoped_to_allowed_warehouses(client, admin_headers):
    with SessionLocal() as db:
        company = db.scalar(select(Company))
        wh1 = Warehouse(name="W14-MAG-A", company_id=company.id)
        wh2 = Warehouse(name="W14-MAG-B", company_id=company.id)
        db.add_all([wh1, wh2])
        db.flush()
        db.add_all([
            Container(container_no="WHAU0000001", company_id=company.id,
                      warehouse_id=wh1.id),
            Container(container_no="WHBU0000001", company_id=company.id,
                      warehouse_id=wh2.id),
        ])
        db.commit()
        wh1_id, company_id = wh1.id, company.id
    created = client.post("/api/users", headers=admin_headers,
                          json={"login": "logmag", "password": "haslo1234",
                                "role": "logistics", "company_id": company_id})
    uid = created.json()["id"]
    resp = client.patch(f"/api/users/{uid}", headers=admin_headers,
                        json={"allowed_warehouse_ids": [wh1_id]})
    assert resp.status_code == 200
    assert resp.json()["allowed_warehouse_ids"] == [wh1_id]
    h = login(client, "logmag", "haslo1234")
    nos = {c["container_no"] for c in client.get("/api/containers", headers=h).json()}
    assert "WHAU0000001" in nos
    assert "WHBU0000001" not in nos
    # pusta lista = wszystkie (dotychczasowe zachowanie)
    client.patch(f"/api/users/{uid}", headers=admin_headers,
                 json={"allowed_warehouse_ids": []})
    nos = {c["container_no"] for c in client.get("/api/containers", headers=h).json()}
    assert {"WHAU0000001", "WHBU0000001"} <= nos


# --- #48 panel System + #47 weryfikacja backupu ---

def test_system_panel_admin_only(client, admin_headers):
    resp = client.get("/api/admin/system", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] == "ok"
    assert "uptime_s" in body and "client_errors_24h" in body
    assert "uploads_size_mb" in body and "run_background_jobs" in body
    # nie-admin: 403
    client.post("/api/users", headers=admin_headers,
                json={"login": "zwykly", "password": "haslo1234", "role": "logistics",
                      "view_all_companies": True})
    h = login(client, "zwykly", "haslo1234")
    assert client.get("/api/admin/system", headers=h).status_code == 403


def test_verify_backup_skips_on_sqlite(client, admin_headers):
    resp = client.post("/api/admin/system/verify-backup", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "skip"
    # wynik widoczny w panelu System
    body = client.get("/api/admin/system", headers=admin_headers).json()
    assert body["backup_verify"]["status"] == "skip"


def test_backup_codes_hashed_in_db(client):
    headers = login(client)
    _, codes = _enable_2fa(client, headers)
    with SessionLocal() as db:
        raw = db.scalar(select(User).where(User.login == "admin")).totp_backup_codes
        hashes = json.loads(raw)
        assert len(hashes) == 10
        assert not set(codes) & set(hashes)  # w bazie tylko hashe, nie kody

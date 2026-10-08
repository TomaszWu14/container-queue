"""Testy utwardzenia: sesje, ochrona admina, walidacje, ISO 6346."""
from app.iso6346 import validate


def test_password_reset_flow(client, admin_headers):
    """Reset hasła: token jednorazowy ustawia nowe hasło i unieważnia sesje."""
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import User
    from app.security import create_password_reset_token

    # konto spedytora z e-mailem
    forwarders = client.get("/api/forwarders", headers=admin_headers).json()
    fid = forwarders[0]["id"]
    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.spedalfa", "password": "start1234", "role": "forwarder",
        "forwarder_id": fid, "email": "sped@spedalfa.example"})

    # anty-enumeracja: 202 zarówno dla istniejącego, jak i nieistniejącego adresu
    assert client.post("/api/auth/forgot-password",
                       json={"email": "sped@spedalfa.example"}).status_code == 202
    assert client.post("/api/auth/forgot-password",
                       json={"email": "nikt@nigdzie.example"}).status_code == 202

    # token zdobywamy bezpośrednio (w testach SMTP wyłączony — brak maila)
    with SessionLocal() as db:
        uid = db.scalar(select(User.id).where(User.login == "sped.spedalfa"))
        raw = create_password_reset_token(db, uid)

    # zły token → 400
    assert client.post("/api/auth/reset-password",
                       json={"token": "x" * 20, "password": "nowe12345"}).status_code == 400

    # poprawny reset
    ok = client.post("/api/auth/reset-password",
                     json={"token": raw, "password": "nowe12345"})
    assert ok.status_code == 200, ok.text

    # ten sam token nie zadziała drugi raz (jednorazowość)
    assert client.post("/api/auth/reset-password",
                       json={"token": raw, "password": "inne12345"}).status_code == 400

    # nowe hasło działa, stare nie
    assert client.post("/api/auth/login",
                       data={"username": "sped.spedalfa", "password": "nowe12345"}).status_code == 200
    assert client.post("/api/auth/login",
                       data={"username": "sped.spedalfa", "password": "start1234"}).status_code == 401


def test_default_forwarders_seeded(client, admin_headers):
    names = {f["name"] for f in client.get("/api/forwarders", headers=admin_headers).json()}
    assert {"SPEDALFA", "Spedgamma", "Spedomega", "Speddelta"} <= names


def test_logout_invalidates_access_token(client, admin_headers):
    # ważny token działa
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 200
    # wylogowanie podbija wersję sesji (cookie refresh ustawione przy logowaniu)
    assert client.post("/api/auth/logout").status_code == 204
    # stary access token przestaje być ważny
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 401


def test_cannot_demote_last_admin(client, admin_headers):
    me = client.get("/api/auth/me", headers=admin_headers).json()
    resp = client.patch(f"/api/users/{me['id']}", headers=admin_headers,
                        json={"role": "logistics"})
    assert resp.status_code == 400, resp.text


def test_cannot_deactivate_last_admin(client, admin_headers):
    me = client.get("/api/auth/me", headers=admin_headers).json()
    resp = client.patch(f"/api/users/{me['id']}", headers=admin_headers,
                        json={"is_active": False})
    assert resp.status_code == 400, resp.text


def test_update_company_duplicate_code_conflict(client, admin_headers):
    companies = client.get("/api/companies", headers=admin_headers).json()
    first, second = companies[0], companies[1]
    resp = client.patch(f"/api/companies/{first['id']}", headers=admin_headers,
                        json={"name": first["name"], "code": second["code"]})
    assert resp.status_code == 409, resp.text


def test_forwarder_user_requires_forwarder_id(client, admin_headers):
    resp = client.post("/api/users", headers=admin_headers, json={
        "login": "sped.bezid", "password": "haslo123", "role": "forwarder"})
    assert resp.status_code == 422, resp.text


def test_non_admin_user_requires_company(client, admin_headers):
    resp = client.post("/api/users", headers=admin_headers, json={
        "login": "log.bezspolki", "password": "haslo123", "role": "logistics"})
    assert resp.status_code == 422, resp.text


def test_wrong_email_rejected(client, admin_headers):
    resp = client.post("/api/users", headers=admin_headers, json={
        "login": "ktos", "password": "haslo123", "role": "logistics",
        "view_all_companies": True, "email": "to-nie-email"})
    assert resp.status_code == 422, resp.text


def test_iso6346_rejects_wrong_checkdigit():
    # zła cyfra kontrolna (reszta 10 z cyfrą 0 jest dozwolona — test_iso6346_remainder10.py)
    ok, _ = validate("CSQU3054380")   # poprawny ma cyfrę 3
    assert not ok


def test_unknown_api_path_returns_404_not_index(client, admin_headers):
    resp = client.get("/api/nie-ma-takiego", headers=admin_headers)
    assert resp.status_code == 404


def test_sentry_before_send_scrubs_pii():
    from app.main import _sentry_before_send
    event = {"request": {
        "data": {"driver_id_no": "AB123", "driver_phone": "600", "notes": "ok"},
        "cookies": {"timporye_access": "jwt"},
        "headers": {"Authorization": "Bearer x", "User-Agent": "ff"},
        "query_string": "token=secret"}, "extra": {"password": "p", "safe": "v"}}
    out = _sentry_before_send(event, None)
    assert out["request"]["data"]["driver_id_no"] == "[Filtered]"
    assert out["request"]["data"]["driver_phone"] == "[Filtered]"
    assert out["request"]["data"]["notes"] == "ok"          # nie-wrażliwe zostają
    assert out["request"]["cookies"] == "[Filtered]"        # cookies maskowane w całości
    assert out["request"]["headers"]["Authorization"] == "[Filtered]"
    assert out["request"]["headers"]["User-Agent"] == "ff"
    assert "query_string" not in out["request"]
    assert out["extra"]["password"] == "[Filtered]"
    assert out["extra"]["safe"] == "v"


def test_sentry_before_send_redacts_free_text_pii():
    """B4/RODO: PII w wolnym tekście (komunikat wyjątku, log, breadcrumb) też maskowane."""
    from app.main import _sentry_before_send
    event = {
        "exception": {"values": [{"value": "Błąd dla jan.kowalski@example.com tel 600700800"}]},
        "logentry": {"message": "kontakt: ola@firma.pl / 500-600-700"},
        "breadcrumbs": {"values": [{"message": "kierowca +48 600 700 800"}]},
    }
    out = _sentry_before_send(event, None)
    exc = out["exception"]["values"][0]["value"]
    assert "jan.kowalski@example.com" not in exc and "[email]" in exc
    assert "600700800" not in exc and "[number]" in exc
    assert "ola@firma.pl" not in out["logentry"]["message"]
    assert "600 700 800" not in out["breadcrumbs"]["values"][0]["message"]


def test_sentry_before_send_drops_frame_vars_and_log_params():
    """GDPR-003: zmienne lokalne ramek i parametry/sformatowany log nie wychodzą z PII."""
    from app.main import _sentry_before_send
    event = {
        "exception": {"values": [{"value": "x", "stacktrace": {"frames": [
            {"function": "notify", "vars": {"driver_phone": "'+48600999111'",
                                            "body": "DriverIn(email='jan@firma.pl')"}}]}}]},
        "logentry": {"message": "SMS do kierowcy %s nie wyszedł",
                     "formatted": "SMS do kierowcy +48600999111 nie wyszedł",
                     "params": ["+48600999111", "jan@firma.pl"]},
    }
    out = str(_sentry_before_send(event, None))
    assert "600999111" not in out and "jan@firma.pl" not in out
    assert "notify" in out   # sama ramka (funkcja) zostaje — diagnostyka nadal działa


def test_invite_generates_random_temp_password(client, admin_headers):
    """B6 v2: zaproszenie dostaje LOSOWE hasło per użytkownik (nie wspólny sekret
    z konfiguracji), zwracane jednorazowo w odpowiedzi; reset-invite losuje nowe."""
    def invite(login):
        resp = client.post("/api/users", headers=admin_headers, json={
            "login": login, "email": f"{login}@example.com", "role": "logistics",
            "view_all_companies": True, "send_invite": True})
        assert resp.status_code == 201, resp.text
        return resp.json()

    u1, u2 = invite("zaproszony1"), invite("zaproszony2")
    assert u1["temp_password"] and u2["temp_password"]
    assert u1["temp_password"] != u2["temp_password"]   # per user, nie wspólne
    assert u1["must_change_password"] is True

    # hasło działa przy logowaniu
    login = client.post("/api/auth/login", data={
        "username": "zaproszony1", "password": u1["temp_password"]})
    assert login.status_code == 200, login.text

    # hasło NIE wraca w zwykłym listingu userów
    users = client.get("/api/users", headers=admin_headers).json()
    assert all(not u.get("temp_password") for u in users)

    # reset-invite: nowe losowe hasło, stare przestaje działać
    reset = client.post(f"/api/users/{u1['id']}/reset-invite", headers=admin_headers)
    assert reset.status_code == 200, reset.text
    new_pw = reset.json()["temp_password"]
    assert new_pw and new_pw != u1["temp_password"]
    assert client.post("/api/auth/login", data={
        "username": "zaproszony1", "password": u1["temp_password"]}).status_code == 401
    assert client.post("/api/auth/login", data={
        "username": "zaproszony1", "password": new_pw}).status_code == 200


def test_password_hashing_bcrypt_backward_compatible():
    """Migracja passlib → czyste bcrypt: format $2b$, zgodność wsteczna, długie hasła."""
    from app.security import hash_password, verify_password

    # istniejący hash z ery passlib (format $2b$) musi się nadal weryfikować
    legacy = "$2b$12$/wYPz809rKOCb.704ajNe.HY/e5bbp8fbIdi282ndjkiMaUtpNqtm"
    assert verify_password("Legacy_Pass_2024", legacy) is True
    assert verify_password("zle", legacy) is False

    # nowy hash: format zgodny + round-trip
    h = hash_password("MojeHaslo123")
    assert h.startswith("$2b$")
    assert verify_password("MojeHaslo123", h) is True
    assert verify_password("MojeHaslo124", h) is False

    # hasło > 72 bajtów nie wywala (bcrypt 5.x rzucałby ValueError bez przycięcia)
    long_pw = "x" * 200
    assert verify_password(long_pw, hash_password(long_pw)) is True

    # uszkodzony hash → False, nie wyjątek
    assert verify_password("cokolwiek", "nie-jest-hashem") is False

"""Zamówienia specjalnej troski: dopasowanie do kontenerów, 2 wyzwalacze ryzyka,
izolacja per spółka."""
import datetime

from app.models import today_pl
from tests.conftest import forwarder, login

VALID_NO = "MSDU0806613"
OTHER_NO = "TCLU5779674"


def _company_id(client, headers, code="BOREALIS"):
    companies = client.get("/api/companies", headers=headers).json()
    return next(c["id"] for c in companies if c["code"] == code)


def _make_order(client, headers, company_id, **overrides):
    body = {"name": "Zamówienie testowe", "order_refs": "4500617421",
            "company_id": company_id}
    body.update(overrides)
    resp = client.post("/api/customer-orders", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_container(client, headers, company_id, container_no=VALID_NO, **overrides):
    body = {"container_no": container_no, "company_id": company_id}
    body.update(overrides)
    resp = client.post("/api/containers", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_matches_containers_by_order_ref(client, admin_headers):
    company_id = _company_id(client, admin_headers)
    _make_container(client, admin_headers, company_id, order_numbers="4500617421")
    order = _make_order(client, admin_headers, company_id)
    got = client.get("/api/customer-orders", headers=admin_headers).json()
    found = next(o for o in got if o["id"] == order["id"])
    assert found["matched_count"] >= 1


def test_trigger_etd_missed(client, admin_headers):
    company_id = _company_id(client, admin_headers)
    yesterday = today_pl() - datetime.timedelta(days=1)
    _make_container(client, admin_headers, company_id, order_numbers="4500617421",
                    status="W_TRANSPORCIE")
    order = _make_order(client, admin_headers, company_id, max_etd=yesterday.isoformat())
    got = client.get("/api/customer-orders", headers=admin_headers).json()
    found = next(o for o in got if o["id"] == order["id"])
    assert found["trigger_etd_missed"] is True
    assert found["at_risk"] is True


def test_trigger_forecast_late(client, admin_headers):
    company_id = _company_id(client, admin_headers)
    eta = today_pl() + datetime.timedelta(days=10)
    deadline = eta + datetime.timedelta(days=1)  # < eta + buffer(5) -> spóźni się
    _make_container(client, admin_headers, company_id, order_numbers="4500617421",
                    eta=eta.isoformat())
    order = _make_order(client, admin_headers, company_id, deadline=deadline.isoformat(),
                        buffer_days=5)
    got = client.get("/api/customer-orders", headers=admin_headers).json()
    found = next(o for o in got if o["id"] == order["id"])
    assert found["trigger_forecast_late"] is True
    assert found["at_risk"] is True


def test_no_risk_when_on_track(client, admin_headers):
    company_id = _company_id(client, admin_headers)
    future_max_etd = today_pl() + datetime.timedelta(days=30)
    _make_container(client, admin_headers, company_id, order_numbers="4500617421")
    order = _make_order(client, admin_headers, company_id, max_etd=future_max_etd.isoformat())
    got = client.get("/api/customer-orders", headers=admin_headers).json()
    found = next(o for o in got if o["id"] == order["id"])
    assert found["at_risk"] is False


def test_company_isolation(client, admin_headers):
    company_a = _company_id(client, admin_headers, "BOREALIS")
    company_b = _company_id(client, admin_headers, "COBALT")
    _make_container(client, admin_headers, company_a, container_no=VALID_NO,
                    order_numbers="4500617421")
    _make_container(client, admin_headers, company_b, container_no=OTHER_NO,
                    order_numbers="4500617421")
    order_a = _make_order(client, admin_headers, company_a)

    # order spółki A widzi tylko kontener spółki A
    got = client.get("/api/customer-orders", headers=admin_headers).json()
    found = next(o for o in got if o["id"] == order_a["id"])
    numbers = [m["container_no"] for m in found["matched"]]
    assert numbers == [VALID_NO]

    # użytkownik przypisany do spółki B nie widzi zamówienia spółki A
    resp = client.post("/api/users", headers=admin_headers, json={
        "login": "logi_b", "password": "haslo1234", "role": "logistics",
        "company_id": company_b})
    assert resp.status_code == 201, resp.text
    login_b = client.post("/api/auth/login",
                          data={"username": "logi_b", "password": "haslo1234"})
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}
    got_b = client.get("/api/customer-orders", headers=headers_b).json()
    assert all(o["id"] != order_a["id"] for o in got_b)


def test_delete_customer_order(client, admin_headers):
    company_id = _company_id(client, admin_headers)
    order = _make_order(client, admin_headers, company_id)
    resp = client.delete(f"/api/customer-orders/{order['id']}", headers=admin_headers)
    assert resp.status_code == 204
    resp = client.patch(f"/api/customer-orders/{order['id']}", headers=admin_headers,
                        json={"name": "x", "company_id": company_id})
    assert resp.status_code == 404


def test_ref_matches_whole_token_not_substring(client, admin_headers):
    """„4500617421” nie może łapać „45000174210” (ILIKE %ref% był za szeroki);
    pasuje jako całe numery na liście rozdzielonej przecinkami/spacjami/średnikami."""
    company_id = _company_id(client, admin_headers)
    _make_container(client, admin_headers, company_id, container_no=VALID_NO,
                    order_numbers="45000174210")
    _make_container(client, admin_headers, company_id, container_no=OTHER_NO,
                    order_numbers="111; 4500617421, 222")
    order = _make_order(client, admin_headers, company_id)
    got = client.get("/api/customer-orders", headers=admin_headers).json()
    assert next(o for o in got if o["id"] == order["id"])["matched_count"] == 1


# --- izolacja przez wspólne helpery deps (audyt 2026-09-23, P4) ---

def test_create_with_unknown_company_is_404(client, admin_headers):
    """resolve_company_id: nieistniejąca spółka to 404, nie rekord z wiszącym company_id."""
    for url, body in (("/api/customer-orders", {"name": "X", "company_id": 999999}),
                      ("/api/customers", {"name": "X", "company_id": 999999})):
        resp = client.post(url, headers=admin_headers, json=body)
        assert resp.status_code == 404, (url, resp.text)


def test_account_without_company_denied_on_lists(client):
    """scope_company: konto bez spółki (bez view_all) → 403 fail-closed, jak inne listy."""
    from app.database import SessionLocal
    from app.models import Role, User
    from app.security import hash_password
    from tests.conftest import login
    with SessionLocal() as db:
        db.add(User(login="logi-nocomp", hashed_password=hash_password("pass12345"),
                    role=Role.logistics, company_id=None, view_all_companies=False))
        db.commit()
    headers = login(client, "logi-nocomp", "pass12345")
    for url in ("/api/customer-orders", "/api/customers"):
        assert client.get(url, headers=headers).status_code == 403, url


def test_at_risk_order_feeds_dashboard_signal(client, admin_headers):
    # D13: T1 zamówienia specjalnej troski -> sygnał 'special_care' w action_feed Wieży
    company_id = _company_id(client, admin_headers)
    c = _make_container(client, admin_headers, company_id, order_numbers="4500617421",
                        status="W_TRANSPORCIE")
    max_etd = today_pl() - datetime.timedelta(days=3)
    _make_order(client, admin_headers, company_id, name="Troska", max_etd=max_etd.isoformat())
    feed = client.get("/api/stats/dashboard", headers=admin_headers).json()["action_feed"]
    sig = next(s for s in feed if s["type"] == "special_care")
    assert sig["container_id"] == c["id"]
    assert sig["summary_params"] == {"name": "Troska", "days": 3}


def test_special_care_signal_hidden_from_non_editors(client, admin_headers):
    # moduł specjalnej troski = Editors (admin/logistyka); partner zewnętrzny (spedytor)
    # nie może zobaczyć sygnału 'special_care' (nazwa zamówienia) w Co dziś ani na Wieży
    company_id = _company_id(client, admin_headers)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.troska", "password": "haslo123", "role": "forwarder",
        "forwarder_id": spedalfa, "email": "troska@example.com"})
    _make_container(client, admin_headers, company_id, order_numbers="4500617421",
                    status="W_TRANSPORCIE", forwarder_id=spedalfa)
    max_etd = today_pl() - datetime.timedelta(days=3)
    _make_order(client, admin_headers, company_id, name="Troska", max_etd=max_etd.isoformat())
    fwd = login(client, "sped.troska", "haslo123")
    inbox = client.get("/api/inbox", headers=fwd).json()["signals_top"]
    feed = client.get("/api/stats/dashboard", headers=fwd).json()["action_feed"]
    assert not [s for s in inbox + feed if s["type"] == "special_care"]
    admin_inbox = client.get("/api/inbox", headers=admin_headers).json()["signals_top"]
    assert any(s["type"] == "special_care" for s in admin_inbox)


def test_queue_flag_customer_order(client, admin_headers):
    """Flaga „pod klienta" w kolejce: kontener z PO z zamówienia specjalnej troski
    dostaje nazwę klienta; inny kontener — nic (test T3, 2026-09-24)."""
    company_id = _company_id(client, admin_headers)
    hit = _make_container(client, admin_headers, company_id, order_numbers="4500617421\n4500617412")
    miss = _make_container(client, admin_headers, company_id, container_no=OTHER_NO,
                           order_numbers="45000174210")   # ref pasuje tylko jako cały numer
    _make_order(client, admin_headers, company_id, customer_name="Klient ABC")
    rows = {c["id"]: c for c in client.get("/api/containers", headers=admin_headers).json()}
    assert rows[hit["id"]]["customer_order"] == "Klient ABC"
    assert rows[miss["id"]]["customer_order"] is None

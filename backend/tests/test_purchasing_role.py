"""#13 — rola `purchasing` (dział zakupów).

Siatka: rola widzi swoją spółkę, edytuje WYŁĄCZNIE purchasing_status, nie ma
dostępu do Odprawy ani Wycen (jawnie, bez dziedziczenia), a scoping firmowy
działa cross-company (403/404). Buduje na testach izolacji z PR-1 (D1).
"""
import pytest


def _company_id(client, headers, code):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _make_user(client, admin_headers, login_name, role, company_id):
    r = client.post("/api/users", headers=admin_headers, json={
        "login": login_name, "password": "haslo123", "role": role,
        "company_id": company_id, "view_all_companies": False})
    assert r.status_code == 201, r.text
    resp = client.post("/api/auth/login",
                       data={"username": login_name, "password": "haslo123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _container_in(client, admin_headers, company_id, no="MSDU0806613"):
    r = client.post("/api/containers", headers=admin_headers,
                    json={"container_no": no, "company_id": company_id})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture()
def setup(client, admin_headers):
    """A = BOREALIS (zakupowiec pracuje tu), B = COBALT (obca spółka)."""
    a = _company_id(client, admin_headers, "BOREALIS")
    b = _company_id(client, admin_headers, "COBALT")
    buyer = _make_user(client, admin_headers, "zakupy.a", "purchasing", a)
    return a, b, buyer


def test_container_out_exposes_purchasing_status(client, admin_headers, setup):
    a, _b, _buyer = setup
    cid = _container_in(client, admin_headers, a)
    r = client.get(f"/api/containers/{cid}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["purchasing_status"] == "BRAK"   # domyślnie brak stanu obiegu


def test_purchasing_sets_status_own_company(client, admin_headers, setup):
    a, _b, buyer = setup
    cid = _container_in(client, admin_headers, a, no="MSKU0000006")
    r = client.put(f"/api/purchasing/containers/{cid}/status", headers=buyer,
                   json={"purchasing_status": "ZAMOWIONE"})
    assert r.status_code == 200, r.text
    assert r.json()["purchasing_status"] == "ZAMOWIONE"
    # utrwalone
    assert client.get(f"/api/containers/{cid}", headers=admin_headers) \
        .json()["purchasing_status"] == "ZAMOWIONE"


def test_purchasing_cannot_set_status_cross_company(client, admin_headers, setup):
    _a, b, buyer = setup
    cid_b = _container_in(client, admin_headers, b, no="TRHU1306972")
    r = client.put(f"/api/purchasing/containers/{cid_b}/status", headers=buyer,
                   json={"purchasing_status": "ZAMOWIONE"})
    assert r.status_code in (403, 404), \
        f"IDOR: zakupowiec A zmienił status kontenera spółki B ({r.status_code})"


def test_purchasing_cannot_patch_other_fields(client, admin_headers, setup):
    """Edytuje WYŁĄCZNIE purchasing_status — generyczny PATCH (rola edytora) go nie wpuszcza."""
    a, _b, buyer = setup
    cid = _container_in(client, admin_headers, a, no="MSNU2506240")
    r = client.patch(f"/api/containers/{cid}", headers=buyer, json={"notes": "hej"})
    assert r.status_code == 403, f"zakupowiec zmodyfikował inne pole kontenera ({r.status_code})"


def test_purchasing_denied_customs_status(client, admin_headers, setup):
    """Brak dostępu do Odprawy — jawnie (customs_side nie zawiera purchasing)."""
    a, _b, buyer = setup
    cid = _container_in(client, admin_headers, a, no="MSCU8004349")
    r = client.post(f"/api/customs/containers/{cid}/status", headers=buyer,
                    json={"customs_status": "ODPRAWIONY"})
    assert r.status_code == 403, f"zakupowiec dostał się do statusu odprawy ({r.status_code})"


def test_purchasing_denied_quotes(client, admin_headers, setup):
    """Brak dostępu do Wycen — jawnie (deny-lista ViewerNoPurchasing), bez dziedziczenia."""
    _a, _b, buyer = setup
    r = client.get("/api/transport-jobs", headers=buyer)
    assert r.status_code == 403, f"zakupowiec odczytał wyceny ({r.status_code})"


def test_purchasing_list_scoped_to_company(client, admin_headers, setup):
    a, b, buyer = setup
    mine = _container_in(client, admin_headers, a, no="MSCU8004349")
    theirs = _container_in(client, admin_headers, b, no="MSDU0806613")
    listed = {c["id"] for c in client.get("/api/containers", headers=buyer).json()}
    assert mine in listed
    assert theirs not in listed, "zakupowiec zobaczył kontener obcej spółki"

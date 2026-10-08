"""D1 PR-1 — testy izolacji „spółka B nie widzi zasobów spółki A".

Uruchamiane na NIEZMIENIONYM kodzie handlerów, żeby udowodnić stan faktyczny:
jeśli któryś świeci na czerwono, mamy istniejący IDOR (nie refaktor, tylko bezp.).
Priorytet: wektor avizo — Container.id.in_(body.container_ids) z surowych ID klienta.
"""
import pytest
from sqlalchemy import select


def _company_id(client, headers, code):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _make_scoped_user(client, admin_headers, login_name, company_id):
    """Logistyk zawężony do jednej spółki (view_all_companies=False)."""
    r = client.post("/api/users", headers=admin_headers, json={
        "login": login_name, "password": "haslo123", "role": "logistics",
        "company_id": company_id, "view_all_companies": False})
    assert r.status_code == 201, r.text
    resp = client.post("/api/auth/login",
                       data={"username": login_name, "password": "haslo123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture()
def two_companies(client, admin_headers):
    """A = BOREALIS (zasoby), B = COBALT (intruz). Zwraca (a_id, b_id, headers_b)."""
    a = _company_id(client, admin_headers, "BOREALIS")
    b = _company_id(client, admin_headers, "COBALT")
    headers_b = _make_scoped_user(client, admin_headers, "intruz.b", b)
    return a, b, headers_b


def _container_in(client, admin_headers, company_id, no="MSDU0806613"):
    r = client.post("/api/containers", headers=admin_headers,
                    json={"container_no": no, "company_id": company_id})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_container_detail_isolated(client, admin_headers, two_companies):
    a, _b, headers_b = two_companies
    cid = _container_in(client, admin_headers, a)
    r = client.get(f"/api/containers/{cid}", headers=headers_b)
    assert r.status_code in (403, 404), f"IDOR: B odczytał kontener A ({r.status_code})"


def test_container_list_excludes_other_company(client, admin_headers, two_companies):
    a, _b, headers_b = two_companies
    cid = _container_in(client, admin_headers, a, no="MSKU0000006")
    listed = {c["id"] for c in client.get("/api/containers", headers=headers_b).json()}
    assert cid not in listed, "IDOR: lista B zawiera kontener A"


def test_sent_links_isolated(client, admin_headers, two_companies):
    a, _b, headers_b = two_companies
    cid = _container_in(client, admin_headers, a, no="TRHU1306972")
    r = client.get(f"/api/containers/{cid}/sent-links", headers=headers_b)
    assert r.status_code in (403, 404), f"IDOR: B odczytał sent-links kontenera A ({r.status_code})"


def test_avizo_rejects_cross_company_container_ids(client, admin_headers, two_companies,
                                                   monkeypatch):
    """NAJWAŻNIEJSZY: send_avizo bierze container_ids prosto z body — B nie może
    wysłać awizacji dla kontenera spółki A. Ustawiamy smtp_host, żeby przejść za guard
    SMTP i faktycznie dotknąć kontroli dostępu (check_container_access jest PRZED wysyłką)."""
    from app.config import settings
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    a, _b, headers_b = two_companies
    cid = _container_in(client, admin_headers, a, no="MSNU2506240")
    r = client.post("/api/avizo/send", headers=headers_b,
                    json={"container_ids": [cid], "note": "", "send_warehouse_info": False})
    assert r.status_code in (403, 404), \
        f"IDOR avizo: B wysłał/objął awizacją kontener A ({r.status_code}: {r.text[:200]})"


def test_get_scoped_helper_enforces(client, admin_headers, two_companies):
    """Fundament D1: get_scoped() sam z siebie blokuje cross-company (przed migracją)."""
    from fastapi import HTTPException

    from app.database import SessionLocal
    from app.deps import get_scoped
    from app.models import Container, User
    a, _b, _hb = two_companies
    cid = _container_in(client, admin_headers, a, no="MSCU8004349")
    with SessionLocal() as db:
        user_b = db.scalar(select(User).where(User.login == "intruz.b"))
        with pytest.raises(HTTPException) as exc:
            get_scoped(db, Container, cid, user_b)
        assert exc.value.status_code in (403, 404)

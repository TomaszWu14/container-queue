"""Potwierdzenia DLT: tokenowy link z maila wywołania — sekwencja statusów,
idempotencja, dezaktywacja tokenu po realizacji, notyfikacje raz, jednolite 404."""
import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Notification
from app.routers import pallets


@pytest.fixture(autouse=True)
def _mock_powerbi(monkeypatch):
    monkeypatch.setattr(settings, "powerbi_provider", "mock")
    monkeypatch.setattr(settings, "powerbi_cache_ttl_min", 0)


def _send_call(client, headers, monkeypatch):
    """Tworzy wywołanie z autem, wysyła je (mock mail) i zwraca (call_id, token)."""
    monkeypatch.setattr(settings, "dlt_call_emails", "dlt@dlt.pl")
    sent = {}
    monkeypatch.setattr(pallets, "send_html_email",
                        lambda to, subject, html, **kw: sent.update(html=html))
    company_id = client.get("/api/companies", headers=headers).json()[0]["id"]
    call = client.post("/api/pallet-calls", headers=headers, json={
        "company_id": company_id, "allow_over_dlt": True,
        "lines": [{"produkt": "DEMO-SKU-X", "ilosc_pal": 5, "truck_no": 1,
                   "hu_numbers": "HU001,HU002"}]}).json()
    r = client.post(f"/api/pallet-calls/{call['id']}/send", headers=headers)
    assert r.status_code == 200, r.text
    token = sent["html"].split("/dlt/")[1].split('"')[0]
    return call["id"], token


def _dlt_notifications(db):
    return list(db.scalars(select(Notification).where(Notification.kind == "dlt")))


def test_full_flow_prepared_shipped(client, admin_headers, db_session, monkeypatch):
    call_id, token = _send_call(client, admin_headers, monkeypatch)

    # strona read-only: auta -> pozycje -> HU/ilości, bez danych wrażliwych
    info = client.get(f"/api/dlt/{token}")
    assert info.status_code == 200, info.text
    data = info.json()
    assert data["status"] == "sent"
    assert data["trucks"][0]["ordinal"] == 1
    line = data["trucks"][0]["lines"][0]
    assert line["produkt"] == "DEMO-SKU-X" and line["hu_numbers"] == "HU001,HU002"

    # Przygotowane: status + audyt + dzwonek (raz)
    assert client.post(f"/api/dlt/{token}/prepared").status_code == 200
    call = client.get(f"/api/pallet-calls/{call_id}", headers=admin_headers).json()
    assert call["status"] == "przygotowane"
    n_after_prepared = len(_dlt_notifications(db_session))
    assert n_after_prepared >= 1

    # idempotencja: drugi klik nie dubluje powiadomień
    assert client.post(f"/api/dlt/{token}/prepared").status_code == 200
    db_session.expire_all()
    assert len(_dlt_notifications(db_session)) == n_after_prepared

    # Wysłane: status + dezaktywacja tokenu
    assert client.post(f"/api/dlt/{token}/shipped").status_code == 200
    call = client.get(f"/api/pallet-calls/{call_id}", headers=admin_headers).json()
    assert call["status"] == "wyslane_z_dlt"
    assert client.get(f"/api/dlt/{token}").status_code == 404
    assert client.post(f"/api/dlt/{token}/shipped").status_code == 404
    db_session.expire_all()
    assert len(_dlt_notifications(db_session)) == 2 * n_after_prepared


def test_shipped_before_prepared_409(client, admin_headers, monkeypatch):
    _, token = _send_call(client, admin_headers, monkeypatch)
    assert client.post(f"/api/dlt/{token}/shipped").status_code == 409


def test_unknown_token_uniform_404(client):
    assert client.get("/api/dlt/deadbeef").status_code == 404
    assert client.post("/api/dlt/deadbeef/prepared").status_code == 404
    assert client.post("/api/dlt/deadbeef/shipped").status_code == 404


def test_resend_deactivates_old_token(client, admin_headers, monkeypatch):
    call_id, token1 = _send_call(client, admin_headers, monkeypatch)
    # ponowna wysyłka generuje świeży token i wygasza stary
    sent = {}
    monkeypatch.setattr(pallets, "send_html_email",
                        lambda to, subject, html, **kw: sent.update(html=html))
    r = client.post(f"/api/pallet-calls/{call_id}/send", headers=admin_headers)
    assert r.status_code == 200, r.text
    token2 = sent["html"].split("/dlt/")[1].split('"')[0]
    assert token1 != token2
    assert client.get(f"/api/dlt/{token1}").status_code == 404
    assert client.get(f"/api/dlt/{token2}").status_code == 200

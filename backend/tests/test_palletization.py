"""#46: proxy paletyzacji do serwisu zewnętrznego — best-effort, wyłączone gdy brak konfiguracji."""
import httpx

from app.config import settings


def _make_container(client, headers):
    companies = client.get("/api/companies", headers=headers).json()
    company_id = companies[0]["id"]
    resp = client.post("/api/containers", headers=headers,
                       json={"container_no": "MSDU0806613", "company_id": company_id})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_palletization_disabled_when_not_configured(client, admin_headers):
    container_id = _make_container(client, admin_headers)
    resp = client.get(f"/api/containers/{container_id}/palletization", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"configured": False}


def test_palletization_proxies_api(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "pallet_api_url", "https://pallets.example/api/v2")
    monkeypatch.setattr(settings, "pallet_api_token", "secret")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"items": []}

    def fake_get(url, params=None, headers=None, timeout=None):
        assert url == "https://pallets.example/api/v2/handling-units"
        assert headers["X-API-Key"] == "secret"
        return FakeResponse()

    monkeypatch.setattr("app.routers.containers.httpx.get", fake_get)

    container_id = _make_container(client, admin_headers)
    resp = client.get(f"/api/containers/{container_id}/palletization", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"configured": True, "data": {"items": []}}


def test_palletization_best_effort_on_failure(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "pallet_api_url", "https://pallets.example/api/v2")

    def fake_get(url, params=None, headers=None, timeout=None):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.routers.containers.httpx.get", fake_get)

    container_id = _make_container(client, admin_headers)
    resp = client.get(f"/api/containers/{container_id}/palletization", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"configured": True, "error": "Serwis paletyzacji niedostępny."}

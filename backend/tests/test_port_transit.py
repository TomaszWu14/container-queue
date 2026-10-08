"""Sezonowy (miesięczny) transit time portów: API słownika + fallback."""
from app.models import Port, PortTransitTime
from app.planning import transit_days_for


def _shanghai(client, headers) -> dict:
    ports = client.get("/api/ports", headers=headers).json()
    return next(p for p in ports if p["name"] == "Shanghai")


def test_monthly_transit_saved_and_read_back(client, admin_headers):
    port = _shanghai(client, admin_headers)
    response = client.patch(f"/api/ports/{port['id']}",
                            json={**port, "monthly_transit": {"1": 50, "9": 65}},
                            headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["monthly_transit"] == {"1": 50, "9": 65}
    # odczyt z listy, nie tylko z odpowiedzi zapisu
    assert _shanghai(client, admin_headers)["monthly_transit"] == {"1": 50, "9": 65}


def test_monthly_transit_is_fully_replaced_on_save(client, admin_headers):
    port = _shanghai(client, admin_headers)
    client.patch(f"/api/ports/{port['id']}", json={**port, "monthly_transit": {"1": 50, "2": 52}},
                 headers=admin_headers)
    client.patch(f"/api/ports/{port['id']}", json={**port, "monthly_transit": {"1": 51}},
                 headers=admin_headers)
    assert _shanghai(client, admin_headers)["monthly_transit"] == {"1": 51}


def test_invalid_month_is_rejected(client, admin_headers):
    port = _shanghai(client, admin_headers)
    response = client.patch(f"/api/ports/{port['id']}",
                            json={**port, "monthly_transit": {"13": 50}}, headers=admin_headers)
    assert response.status_code == 422


def test_monthly_transit_requires_auth(client):
    response = client.patch("/api/ports/1", json={"name": "X", "monthly_transit": {"1": 5}})
    assert response.status_code in (401, 403)


def test_transit_days_for_prefers_month():
    port = Port(name="X", transit_time_days=30)
    port.transit_rows = [PortTransitTime(month=9, days=65)]
    assert transit_days_for(port, 9) == 65


def test_transit_days_for_falls_back_to_default():
    port = Port(name="X", transit_time_days=30)
    port.transit_rows = [PortTransitTime(month=9, days=65)]
    assert transit_days_for(port, 11) == 30, "listopada nie ma w danych klienta"


def test_transit_days_for_returns_none_without_any_value():
    port = Port(name="X", transit_time_days=None)
    port.transit_rows = []
    assert transit_days_for(port, 11) is None
    assert transit_days_for(None, 11) is None


def test_port_with_monthly_transit_can_be_deleted(client, admin_headers):
    """Profil sezonowy jest własnością portu (cascade), nie odwołaniem blokującym."""
    created = client.post("/api/ports", json={"name": "Testowy port", "country": "CN",
                                              "monthly_transit": {"1": 40}},
                          headers=admin_headers)
    assert created.status_code == 201, created.text
    assert created.json()["monthly_transit"] == {"1": 40}
    assert client.delete(f"/api/ports/{created.json()['id']}",
                         headers=admin_headers).status_code == 204

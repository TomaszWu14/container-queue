"""Audyt DB-005: dwa formularze otwarte na tym samym stanie — drugi zapis dostaje 409
zamiast po cichu nadpisać pierwszy."""


def _container(client, admin_headers):
    company_id = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    r = client.post("/api/containers", headers=admin_headers,
                    json={"container_no": "TCNU0000011", "company_id": company_id})
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_second_save_on_stale_state_is_409(client, admin_headers):
    c = _container(client, admin_headers)
    url, seen = f"/api/containers/{c['id']}", c["updated_at"]
    first = client.patch(url, headers=admin_headers, json={"notes": "A", "expected_updated_at": seen})
    assert first.status_code == 200, first.text
    second = client.patch(url, headers=admin_headers, json={"notes": "B", "expected_updated_at": seen})
    assert second.status_code == 409
    assert client.get(url, headers=admin_headers).json()["notes"] == "A"


def test_save_on_fresh_state_and_legacy_client_pass(client, admin_headers):
    c = _container(client, admin_headers)
    url = f"/api/containers/{c['id']}"
    fresh = client.patch(url, headers=admin_headers, json={"notes": "A", "expected_updated_at": c["updated_at"]})
    assert fresh.status_code == 200
    assert client.patch(url, headers=admin_headers, json={"notes": "B"}).status_code == 200


def test_driver_save_on_stale_state_is_409(client, admin_headers):
    """Dane kierowcy: dwie osoby na tym samym stanie — druga dostaje 409, nie nadpisuje."""
    c = _container(client, admin_headers)
    url, seen = f"/api/containers/{c['id']}/driver", c["updated_at"]
    first = client.patch(url, headers=admin_headers,
                         json={"truck_no": "WA111", "expected_updated_at": seen})
    assert first.status_code == 200, first.text
    second = client.patch(url, headers=admin_headers,
                          json={"truck_no": "KR222", "expected_updated_at": seen})
    assert second.status_code == 409
    assert client.get(f"/api/containers/{c['id']}", headers=admin_headers).json()["truck_no"] == "WA111"
    # odpowiedź pierwszego zapisu niesie nowy updated_at — kolejny zapis z nim przechodzi
    third = client.patch(url, headers=admin_headers,
                         json={"truck_no": "PO333", "expected_updated_at": first.json()["updated_at"]})
    assert third.status_code == 200, third.text
    assert client.patch(url, headers=admin_headers, json={"truck_no": "X"}).status_code == 200


def test_no_op_save_returns_fresh_updated_at(client, admin_headers):
    """Zapis bez zmian pól też „zajmuje” stan — zwrócony updated_at musi pasować do bazy."""
    c = _container(client, admin_headers)
    url = f"/api/containers/{c['id']}"
    r = client.patch(url, headers=admin_headers, json={"expected_updated_at": c["updated_at"]})
    assert r.status_code == 200, r.text
    again = client.patch(url, headers=admin_headers,
                         json={"notes": "Z", "expected_updated_at": r.json()["updated_at"]})
    assert again.status_code == 200, again.text

"""Dashboard zwraca action_feed: jedna posortowana lista sygnałów w zakresie usera."""


def _company_id(client, headers, code):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
               if c["code"] == code)


def test_dashboard_returns_action_feed(client, admin_headers):
    acme_id = _company_id(client, admin_headers, "ACME")
    ports = client.get("/api/ports", headers=admin_headers).json()
    # kontener bez ETA i w porcie → co najmniej sygnał missing_eta
    c = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MEDU1234562", "company_id": acme_id,
        "port_id": ports[0]["id"], "status": "W_PORCIE"}).json()
    data = client.get("/api/stats/dashboard", headers=admin_headers).json()
    assert "action_feed" in data
    assert any(s["container_id"] == c["id"] for s in data["action_feed"])

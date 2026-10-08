"""Klient (odbiorca) jako znacznik: słownik klientów per spółka i przypięcie do kontenera.
Odbiorcy nie mają dostępu do aplikacji (decyzja 2026-10-07) — portal kliencki usunięty."""
VALID_NO = "MSDU0806613"
OTHER_NO = "TCLU5779674"


def _company(client, headers, code="BOREALIS"):
    companies = client.get("/api/companies", headers=headers).json()
    return next(c["id"] for c in companies if c["code"] == code)


def test_customer_marker_on_container(client, admin_headers):
    company = _company(client, admin_headers)
    cust = client.post("/api/customers", headers=admin_headers, json={
        "name": "Klient A", "contact": "a@example.com", "company_id": company}).json()
    cont = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": company}).json()
    resp = client.put(f"/api/containers/{cont['id']}/customer", headers=admin_headers,
                      json={"customer_id": cust["id"]})
    assert resp.status_code == 200 and resp.json() == {"customer_id": cust["id"]}
    # portal kliencki nie istnieje — ani link per klient, ani publiczny podgląd
    assert client.post(f"/api/customers/{cust['id']}/share-link",
                       headers=admin_headers).status_code in (404, 405)
    assert client.get("/api/public/portal/abcdefghijklmnopqrstuvwxyz").status_code == 404


def test_customer_company_isolation_and_roles(client, admin_headers):
    company_a = _company(client, admin_headers, "BOREALIS")
    company_b = _company(client, admin_headers, "ACME")
    cust = client.post("/api/customers", headers=admin_headers, json={
        "name": "Klient X", "company_id": company_a}).json()
    cont = client.post("/api/containers", headers=admin_headers, json={
        "container_no": OTHER_NO, "company_id": company_b}).json()
    # klient z innej spółki niż kontener → 422
    assert client.put(f"/api/containers/{cont['id']}/customer", headers=admin_headers,
                      json={"customer_id": cust["id"]}).status_code == 422
    # endpointy panelu wymagają uwierzytelnienia (TestClient trzyma cookie admina —
    # nadpisujemy nagłówkiem z błędnym tokenem)
    bad = {"Authorization": "Bearer bad-token"}
    assert client.get("/api/customers", headers=bad).status_code == 401

"""Rola `sales` (decyzja usera 2026-09-27): tylko odczyt kolejki, karty kontenera, kalendarza,
śledzenia i Specjalnej troski — w zakresie swojej spółki, bez kosztów i bez zapisu."""
from tests.conftest import login
from tests.test_api import VALID_NO, _company_id


def test_sales_reads_own_company_only_without_writes_or_costs(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    other = next(c["id"] for c in client.get("/api/companies", headers=admin_headers).json()
                 if c["id"] != borealis)
    assert client.post("/api/users", headers=admin_headers, json={
        "login": "sprzedaz.a", "password": "haslo123", "role": "sales", "company_id": borealis,
        "full_name": "Anna Sprzedaż", "email": "sprzedaz@example.com"}).status_code == 201
    own = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis}).json()
    client.patch(f"/api/containers/{own['id']}/driver", headers=admin_headers, json={
        "driver_name": "Jan", "driver_id_no": "ABC123", "truck_no": "", "trailer_no": "",
        "driver_phone": "600100200"})
    foreign = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "TCLU5779674", "company_id": other}).json()
    h = login(client, "sprzedaz.a", "haslo123")

    # odczyt: swoja spółka tak, cudza 404; PII kierowcy zamaskowane
    view = client.get(f"/api/containers/{own['id']}", headers=h)
    assert view.status_code == 200
    assert view.json()["driver_id_no"] == "" and view.json()["driver_phone"] == ""
    # 2026-10-05: także nazwisko kierowcy i numery pojazdu (PII) — sprzedaż ich nie potrzebuje
    assert view.json()["driver_name"] == "" and view.json()["truck_no"] == ""
    assert client.get(f"/api/containers/{foreign['id']}", headers=h).status_code == 404
    assert [c["id"] for c in client.get("/api/containers", headers=h).json()] == [own["id"]]
    for url in ("/api/queue", "/api/calendar/year?rok=2026", "/api/tracking/vessels",
                "/api/customer-orders", f"/api/containers/{own['id']}/timeline"):
        assert client.get(url, headers=h).status_code == 200, url

    # osobista obserwacja kontenera (subskrypcja powiadomień, nie zmiana danych) — tak
    assert client.post(f"/api/containers/{own['id']}/watch", headers=h, json={}).status_code == 200
    assert client.post(f"/api/containers/{foreign['id']}/watch", headers=h, json={}).status_code == 404
    # zapis danych: nic
    assert client.patch(f"/api/containers/{own['id']}", headers=h,
                        json={"notes": "x"}).status_code == 403
    assert client.post(f"/api/containers/{own['id']}/status", headers=h,
                       json={"status": "W_PORCIE"}).status_code == 403
    assert client.post("/api/customer-orders", headers=h, json={
        "name": "X", "company_id": borealis}).status_code == 403
    # koszty: pulpit (demurrage €), wyceny, faktury frachtowe — zamknięte
    for url in ("/api/stats/dashboard", "/api/transport-jobs", "/api/freight-invoices",
                "/api/purchase-orders", "/api/users"):
        assert client.get(url, headers=h).status_code == 403, url

    # handlowiec może być „Odpowiedzialnym” w Specjalnej trosce
    names = {r["name"] for r in client.get("/api/customer-orders/responsibles",
                                           headers=admin_headers).json()}
    assert "Anna Sprzedaż" in names

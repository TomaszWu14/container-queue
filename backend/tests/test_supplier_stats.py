"""#39: KPI karty dostawcy — liczone w zakresie usera (scope_containers)."""
import datetime
import io

from openpyxl import Workbook

from app.models import Container, ContainerStatus


def _company_id(client, headers, code):
    companies = client.get("/api/companies", headers=headers).json()
    return next(c["id"] for c in companies if c["code"] == code)


def _container(client, headers, no, company_id, supplier_id):
    response = client.post("/api/containers", headers=headers,
                           json={"container_no": no, "company_id": company_id,
                                "supplier_id": supplier_id})
    assert response.status_code == 201, response.text
    return response.json()


def test_supplier_stats_counts_active_ontime_and_transit(client, admin_headers, db_session):
    acme = _company_id(client, admin_headers, "ACME")
    supplier = client.post("/api/suppliers", headers=admin_headers,
                           json={"name": "Dostawca KPI", "company_id": acme}).json()

    # aktywny (niezrealizowany)
    _container(client, admin_headers, "TGBU6784203", acme, supplier["id"])
    # zakończony, na czas (atd <= eta), transit 10 dni
    c2 = _container(client, admin_headers, "CSQU3054383", acme, supplier["id"])
    # zakończony, spóźniony (atd > eta), transit 20 dni
    c3 = _container(client, admin_headers, "MEDU9573834", acme, supplier["id"])

    # etd/status realizacji nie da się ustawić przez API (etd liczy tracking, status
    # ZREALIZOWANY nie jest wśród przejść /status) — ustawiamy wprost w bazie
    row2 = db_session.get(Container, c2["id"])
    row2.status = ContainerStatus.ZREALIZOWANY
    row2.eta, row2.etd, row2.atd = (datetime.date(2026, 1, 20), datetime.date(2026, 1, 1),
                                    datetime.date(2026, 1, 20))
    row3 = db_session.get(Container, c3["id"])
    row3.status = ContainerStatus.ZREALIZOWANY
    row3.eta, row3.etd, row3.atd = (datetime.date(2026, 1, 10), datetime.date(2026, 1, 1),
                                    datetime.date(2026, 1, 21))
    db_session.commit()

    stats = client.get(f"/api/suppliers/{supplier['id']}/stats", headers=admin_headers)
    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert body["active_containers"] == 1
    assert body["on_time_pct"] == 50.0
    assert body["avg_transit_days"] == 19.5
    assert len(body["recent_containers"]) == 3


def test_supplier_stats_scoped_out_for_other_company(client, admin_headers):
    acme = _company_id(client, admin_headers, "ACME")
    borealis = _company_id(client, admin_headers, "BOREALIS")
    supplier = client.post("/api/suppliers", headers=admin_headers,
                           json={"name": "Dostawca Obcy", "company_id": borealis}).json()
    _container(client, admin_headers, "MSCU8004349", borealis, supplier["id"])

    acme_user = client.post("/api/users", headers=admin_headers, json={
        "login": "acme.viewer", "password": "haslo123", "role": "logistics",
        "company_id": acme, "view_all_companies": False, "warehouse_id": None})
    assert acme_user.status_code == 201, acme_user.text
    from tests.conftest import login
    acme_headers = login(client, "acme.viewer", "haslo123")

    # dostawca innej spółki: 404 (izolacja per spółka, jak przy pozostałych słownikach)
    resp = client.get(f"/api/suppliers/{supplier['id']}/stats", headers=acme_headers)
    assert resp.status_code == 404


def test_import_po_updates_existing_containers_only(client, admin_headers):
    acme = _company_id(client, admin_headers, "ACME")
    existing = client.post("/api/containers", headers=admin_headers,
                           json={"container_no": "MSKU7026492", "company_id": acme}).json()

    wb = Workbook()
    ws = wb.active
    ws.append(["container_no", "order_numbers"])
    ws.append(["MSKU7026492", "PO-100, PO-101"])
    ws.append(["NOPE0000000", "PO-999"])  # nieistniejący kontener -> pominięty
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    resp = client.post("/api/containers/import-po", headers=admin_headers,
                       files={"file": ("po.xlsx", buf,
                                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["matched"] == 1, body
    assert body["skipped"] == 1

    updated = client.get(f"/api/containers/{existing['id']}", headers=admin_headers).json()
    assert "PO-100" in updated["order_numbers"]
    assert "PO-101" in updated["order_numbers"]

    # nie tworzy nowych kontenerów
    all_nos = {c["container_no"] for c in
               client.get("/api/containers", headers=admin_headers).json()}
    assert "NOPE0000000" not in all_nos

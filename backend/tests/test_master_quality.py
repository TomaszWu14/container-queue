"""Walidator jakości master data (#16) + stęchłe importy (#17)."""
import io

from openpyxl import Workbook

from app.master_quality import import_freshness
from app.models import ContainerPort, MaterialUnit
from app.notifications import check_stale_import_alerts


def _issue(payload, key):
    return next(i for i in payload["issues"] if i["key"] == key)


def _marm_xlsx(rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['Materiał', 'Jedn. miary', 'Licznik', 'Mianownik'])
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_quality_report_finds_issues(client, admin_headers, db_session):
    companies = client.get("/api/companies", headers=admin_headers).json()
    cid = companies[0]["id"]
    # dostawca bez kodu SAP i kraju + duplikat nazwy (case-insensitive)
    client.post("/api/suppliers", headers=admin_headers,
                json={"name": "Shanghai Tools", "company_id": cid})
    client.post("/api/suppliers", headers=admin_headers,
                json={"name": "SHANGHAI TOOLS", "company_id": cid})
    # port kontenerowy bez współrzędnych + materiał bez PAL i bez wymiarów
    db_session.add(ContainerPort(code="XXTST", name="Testport"))
    db_session.add(MaterialUnit(material_no="100200", unit="KAR"))
    db_session.commit()

    payload = client.get("/api/master-data/quality", headers=admin_headers).json()
    assert _issue(payload, "suppliers_no_sap")["count"] >= 2
    assert _issue(payload, "suppliers_dup_names")["count"] == 2
    cports = _issue(payload, "cports_no_coords")
    assert cports["count"] == 1 and cports["items"][0]["label"] == "XXTST Testport"
    assert _issue(payload, "materials_no_pal")["count"] == 1
    assert _issue(payload, "units_no_dims")["count"] == 1   # KAR bez wymiarów
    assert cports["tab"] == "cports"


def test_quality_requires_editor_role(client, admin_headers):
    client.post("/api/users", headers=admin_headers, json={
        "login": "zakupy1", "password": "haslo-zakupy-123", "role": "purchasing",
        "view_all_companies": True})
    from tests.conftest import login
    headers = login(client, "zakupy1", "haslo-zakupy-123")
    assert client.get("/api/master-data/quality", headers=headers).status_code == 403


def test_import_freshness_tracks_marm_import(client, admin_headers, db_session):
    response = client.post("/api/import/material-units?dry_run=false", headers=admin_headers,
                           files={"file": ("marm.xlsx", _marm_xlsx([["100300", "PAL", 40, 1]]),
                                           "application/vnd.ms-excel")})
    assert response.status_code == 200, response.text
    fresh = {f["type"]: f for f in import_freshness(db_session)}
    assert fresh["marm"]["age_days"] == 0 and fresh["marm"]["stale"] is False
    assert fresh["ekko"]["last_at"] is None and fresh["ekko"]["stale"] is True


def test_stale_import_alert_once_per_day(client, db_session):
    # świeża baza: wszystkie typy „nigdy" → alert do admina; drugi przebieg cichy
    sent = check_stale_import_alerts(db_session)
    assert sent >= 1
    assert check_stale_import_alerts(db_session) == 0


def test_quality_flags_containers_without_po_and_eta(client, admin_headers, db_session):
    import datetime

    from app.models import Container, ContainerStatus
    cid = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    db_session.add_all([
        # w morzu, bez PO i bez ETA → oba problemy
        Container(company_id=cid, container_no="NOPO1111111", order_numbers="  ",
                  status=ContainerStatus.W_TRANSPORCIE),
        # kompletny → żaden
        Container(company_id=cid, container_no="FULL2222222", order_numbers="4500012345",
                  status=ContainerStatus.W_PORCIE, eta=datetime.date(2026, 10, 1)),
        # jeszcze w produkcji: ETA nieznane to norma, brak PO już nie
        Container(company_id=cid, container_no="PROD3333333",
                  status=ContainerStatus.W_PRODUKCJI),
        # dostarczony: nic już nie zgłaszamy
        Container(company_id=cid, container_no="DONE4444444",
                  status=ContainerStatus.DOSTARCZONY),
    ])
    db_session.commit()

    payload = client.get("/api/master-data/quality", headers=admin_headers).json()
    no_po = {i["label"] for i in _issue(payload, "containers_no_po")["items"]}
    no_eta = {i["label"] for i in _issue(payload, "containers_no_eta")["items"]}
    assert no_po == {"NOPO1111111", "PROD3333333"}
    assert no_eta == {"NOPO1111111"}

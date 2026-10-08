"""GET /api/calendar/year — agregat widoku rocznego (dzień awizacji × magazyn)."""
import datetime

from app.models import Container, Warehouse
from tests.conftest import login

D = datetime.date


def _seed(db_session, admin_headers, client):
    companies = client.get("/api/companies", headers=admin_headers).json()
    if len(companies) < 2:
        companies.append(client.post("/api/companies", headers=admin_headers,
                                     json={"name": "Druga Spółka", "code": "DRUGA"}).json())
    a, b = companies[0]["id"], companies[1]["id"]
    dlt = Warehouse(name="DLT", company_id=a)
    db_session.add(dlt)
    db_session.flush()
    rows = [(a, dlt.id, D(2031, 3, 2)), (a, dlt.id, D(2031, 3, 2)), (a, None, D(2031, 3, 2)),
            (a, dlt.id, D(2031, 7, 9)), (b, None, D(2031, 3, 2)),
            (a, dlt.id, D(2030, 12, 31)), (a, None, None)]     # poza rokiem / bez daty
    for i, (company, wh, day) in enumerate(rows):
        db_session.add(Container(container_no=f"YEAR{i:07d}", company_id=company,
                                 warehouse_id=wh, notify_date=day))
    db_session.commit()
    return a


def _counts(body):
    return {(r["day"], r["warehouse"]): r["count"] for r in body["days"]}


def test_year_aggregates_per_day_and_warehouse(client, admin_headers, db_session):
    _seed(db_session, admin_headers, client)
    r = client.get("/api/calendar/year?rok=2031", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["year"] == 2031 and body["today"]
    assert _counts(body) == {("2031-03-02", "DLT"): 2, ("2031-03-02", None): 2,
                             ("2031-07-09", "DLT"): 1}


def test_year_company_isolation(client, admin_headers, db_session):
    a = _seed(db_session, admin_headers, client)
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.rok", "password": "haslo123", "role": "logistics",
        "company_id": a, "view_all_companies": False})
    body = client.get("/api/calendar/year?rok=2031", headers=login(client, "log.rok", "haslo123")).json()
    # kontener spółki B (bez magazynu, 2031-03-02) nie wchodzi do liczby
    assert _counts(body)[("2031-03-02", None)] == 1


def test_year_without_data(client, admin_headers):
    r = client.get("/api/calendar/year?rok=2099", headers=admin_headers)
    assert r.status_code == 200 and r.json()["days"] == []
    assert client.get("/api/calendar/year?rok=abc", headers=admin_headers).status_code == 422

"""Testy #49 (ostrzeżenie o konflikcie awizacji dostawcy) i #50 (auto-propozycja daty)."""
from app.models import today_pl
import datetime

from app.holidays import is_free_day


def _next_working(day: datetime.date) -> datetime.date:
    while is_free_day(day, "PL"):
        day += datetime.timedelta(days=1)
    return day


def _company_id(client, headers, code):
    companies = client.get("/api/companies", headers=headers).json()
    return next(c["id"] for c in companies if c["code"] == code)


def _setup(client, headers, limit=None):
    borealis = _company_id(client, headers, "BOREALIS")
    payload = {"name": "Borealis", "company_id": borealis, "country": "PL"}
    if limit is not None:
        payload["default_daily_limit"] = limit
    wh = client.post("/api/warehouses", headers=headers, json=payload).json()
    sup = client.post("/api/suppliers", headers=headers, json={
        "name": "Dostawca K", "company_id": borealis}).json()
    return borealis, wh, sup


def _container(client, headers, no, company_id, **extra):
    resp = client.post("/api/containers", headers=headers,
                       json={"container_no": no, "company_id": company_id, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _next_weekday(anchor: datetime.date, weekday: int) -> datetime.date:
    return anchor + datetime.timedelta(days=(weekday - anchor.weekday()) % 7 or 7)


def test_notify_conflict_warning(client, admin_headers):
    borealis, wh, sup = _setup(client, admin_headers)
    day = _next_weekday(today_pl() + datetime.timedelta(days=7), 0)  # pon.
    common = {"warehouse_id": wh["id"], "supplier_id": sup["id"]}
    _container(client, admin_headers, "TESU0000008", borealis,
               notify_date=day.isoformat(), **common)
    c2 = _container(client, admin_headers, "TESU0000013", borealis, **common)
    # 1 inny kontener z tą datą → BEZ ostrzeżenia
    resp = client.patch(f"/api/containers/{c2['id']}", headers=admin_headers,
                        json={"notify_date": day.isoformat()})
    assert resp.status_code == 200 and not resp.json().get("notify_conflict")
    # inny magazyn z tą samą datą — nie liczy się do konfliktu
    other_wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "Inny", "company_id": borealis, "country": "PL"}).json()
    _container(client, admin_headers, "TESU0000034", borealis,
               notify_date=day.isoformat(), warehouse_id=other_wh["id"],
               supplier_id=sup["id"])
    # trzeci kontener: już ≥2 INNE z tą datą i magazynem → ostrzeżenie, nie blokada
    c3 = _container(client, admin_headers, "TESU0000029", borealis, **common)
    resp = client.patch(f"/api/containers/{c3['id']}", headers=admin_headers,
                        json={"notify_date": day.isoformat()})
    assert resp.status_code == 200
    assert resp.json()["notify_conflict"] == 2
    assert resp.json()["notify_date"] == day.isoformat()  # zapis przeszedł mimo ostrzeżenia


def test_suggest_notify_date_skips_free_and_full_days(client, admin_headers):
    borealis, wh, sup = _setup(client, admin_headers, limit=1)
    # ETA w środę: +3 dni bufora = sobota → propozycja przeskakuje na poniedziałek
    eta = _next_weekday(today_pl() + datetime.timedelta(days=7), 2)
    monday = _next_working(eta + datetime.timedelta(days=3))  # sob. → 1. dzień roboczy
    c = _container(client, admin_headers, "TESU0000008", borealis,
                   warehouse_id=wh["id"], supplier_id=sup["id"], eta=eta.isoformat())
    resp = client.get(f"/api/containers/{c['id']}/suggest-notify-date",
                      headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"date": monday.isoformat(), "eta": eta.isoformat(),
                           "buffer_days": 3}
    # poniedziałek zapełniony do limitu (liczy się tylko POTWIERDZONE) → wtorek
    blocker = _container(client, admin_headers, "TESU0000013", borealis,
                         warehouse_id=wh["id"], notify_date=monday.isoformat())
    client.post(f"/api/containers/{blocker['id']}/plan/confirm", headers=admin_headers,
                json={"delivery_date": monday.isoformat()})
    resp = client.get(f"/api/containers/{c['id']}/suggest-notify-date",
                      headers=admin_headers)
    tuesday = _next_working(monday + datetime.timedelta(days=1))
    assert resp.json()["date"] == tuesday.isoformat()
    # wyjątek kalendarza magazynu: wtorek nieroboczy → środa
    client.put("/api/calendar", headers=admin_headers, json={
        "warehouse_id": wh["id"], "day": tuesday.isoformat(), "is_working": False})
    resp = client.get(f"/api/containers/{c['id']}/suggest-notify-date",
                      headers=admin_headers)
    assert resp.json()["date"] == _next_working(
        tuesday + datetime.timedelta(days=1)).isoformat()


def test_suggest_notify_date_without_warehouse(client, admin_headers):
    borealis, _, _ = _setup(client, admin_headers)
    eta = _next_weekday(today_pl() + datetime.timedelta(days=7), 0)
    c = _container(client, admin_headers, "TESU0000055", borealis, eta=eta.isoformat())
    # bez magazynu: brak limitu, tylko dni wolne PL (pon.+3 = czwartek, roboczy)
    resp = client.get(f"/api/containers/{c['id']}/suggest-notify-date",
                      headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["date"] == _next_working(
        eta + datetime.timedelta(days=3)).isoformat()

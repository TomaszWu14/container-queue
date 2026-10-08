"""B2 — analiza rozładunków / kolejka bez N+1 na limitach i kalendarzu.

Potwierdza, że:
- liczby zapytań o daily_limits/calendar_days NIE skalują się z liczbą dni
  (dawniej 1 SELECT na dzień×magazyn) — dowód eliminacji N+1,
- wyniki (limity: nadpisanie vs domyślny, over, is_free_day) pozostają poprawne.
Korektność samej kolejki dodatkowo pilnuje istniejący test_queue_limits_and_free_days.
"""
import datetime

from sqlalchemy import event

from app.database import engine


def _company_id(client, headers, code):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
               if c["code"] == code)


class _Counter:
    def __init__(self, *tables):
        self.tables = tables
        self.counts = dict.fromkeys(tables, 0)

    def __enter__(self):
        def _on(conn, cursor, statement, params, context, executemany):
            low = statement.lower()
            for t in self.tables:
                if f" {t}" in low or f'"{t}"' in low:
                    self.counts[t] += 1
        self._fn = _on
        event.listen(engine, "before_cursor_execute", _on)
        return self

    def __exit__(self, *a):
        event.remove(engine, "before_cursor_execute", self._fn)


def test_analysis_limits_batched_one_query(client, admin_headers):
    acme = _company_id(client, admin_headers, "ACME")
    wh = [client.post("/api/warehouses", headers=admin_headers, json={
              "name": f"WH{i}", "company_id": acme, "country": "PL",
              "default_daily_limit": 2}).json() for i in range(2)]
    d0 = datetime.date(2026, 7, 6)
    # kontenery w kilku dniach, po obu magazynach
    nums = ["MSDU0806613", "CSQU3054383", "TGBU6784203", "TCLU1234563", "TEMU1234567"]
    for i, number in enumerate(nums):
        client.post("/api/containers", headers=admin_headers, json={
            "container_no": number, "company_id": acme,
            "warehouse_id": wh[i % 2]["id"],
            "notify_date": (d0 + datetime.timedelta(days=i)).isoformat()})
    # nadpisanie limitu na jeden dzień/magazyn
    client.put("/api/limits", headers=admin_headers, json={
        "warehouse_id": wh[0]["id"], "day": d0.isoformat(), "limit": 9})

    url = (f"/api/analysis/unloading?company_code=ACME"
           f"&date_from={d0}&date_to={d0 + datetime.timedelta(days=10)}")
    with _Counter("daily_limits") as c:
        data = client.get(url, headers=admin_headers).json()
    # 11 dni × 2 magazyny = 22 par; dawniej 22 zapytania — teraz JEDNO
    assert c.counts["daily_limits"] == 1

    days = {d["day"]: d for d in data["days"]}
    wh0 = wh[0]["id"]
    d0_wh0 = next(w for w in days[d0.isoformat()]["warehouses"] if w["warehouse_id"] == wh0)
    assert d0_wh0["limit"] == 9          # nadpisanie
    other = d0 + datetime.timedelta(days=2)
    other_wh0 = next(w for w in days[other.isoformat()]["warehouses"] if w["warehouse_id"] == wh0)
    assert other_wh0["limit"] == 2       # domyślny


def test_queue_calendar_and_limits_batched(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "T", "company_id": borealis, "country": "PL", "default_daily_limit": 1}).json()
    monday = datetime.date(2026, 7, 6)
    for number in ["MSDU0806613", "CSQU3054383"]:
        client.post("/api/containers", headers=admin_headers, json={
            "container_no": number, "company_id": borealis,
            "warehouse_id": wh["id"], "notify_date": monday.isoformat()})
    client.put("/api/limits", headers=admin_headers, json={
        "warehouse_id": wh["id"], "day": monday.isoformat(), "limit": 10})
    client.put("/api/calendar", headers=admin_headers, json={
        "warehouse_id": wh["id"], "day": datetime.date(2026, 7, 11).isoformat(),
        "is_working": True, "note": "sobota robocza"})

    url = (f"/api/queue?warehouse_id={wh['id']}"
           f"&date_from={monday}&date_to={monday + datetime.timedelta(days=6)}")
    with _Counter("daily_limits", "calendar_days") as c:
        queue = client.get(url, headers=admin_headers).json()
    # okno 7 dni: dawniej 7×(limit+kalendarz)=14 zapytań; teraz po jednym na tabelę
    assert c.counts["daily_limits"] == 1
    assert c.counts["calendar_days"] == 1

    by_day = {d["day"]: d for d in queue}
    assert by_day[monday.isoformat()]["limit"] == 10           # nadpisanie
    assert not by_day[monday.isoformat()]["over_limit"]        # 2 <= 10
    assert not by_day["2026-07-11"]["is_free_day"]             # sobota robocza (wyjątek)
    assert by_day["2026-07-07"]["limit"] == 1                  # domyślny

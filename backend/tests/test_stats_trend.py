"""#56 trend transit time + #58 prognoza obłożenia: agregacje i scope."""
import datetime

from app.database import SessionLocal
from app.models import Container, ContainerStatus, Port, today_pl
from tests.conftest import login

VALID = ["MSDU0806613", "CSQU3054383", "TGHU9876537", "CSNU0110266"]


def _company_id(client, headers, code):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _container(client, headers, no, company_id, **extra):
    body = {"container_no": no, "company_id": company_id, **extra}
    resp = client.post("/api/containers", headers=headers, json=body)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _finish(cid, etd, atd, port_name=None):
    """Ustaw ETD/ATD/port i status zakończony bezpośrednio w DB."""
    with SessionLocal() as db:
        c = db.get(Container, cid)
        c.etd, c.atd, c.status = etd, atd, ContainerStatus.ZREALIZOWANY
        if port_name:
            port = db.query(Port).filter_by(name=port_name).first() or Port(name=port_name)
            db.add(port)
            db.flush()
            c.port_id = port.id
        db.commit()


def test_transit_trend_aggregates_and_ports(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    today = today_pl()
    m = today.replace(day=15) - datetime.timedelta(days=60)  # ~2 mies. temu, w oknie 12 mies.
    key = f"{m.year:04d}-{m.month:02d}"

    a = _container(client, admin_headers, VALID[0], borealis)
    b = _container(client, admin_headers, VALID[1], borealis)
    _finish(a["id"], m - datetime.timedelta(days=30), m, "Shanghai")   # 30 dni
    _finish(b["id"], m - datetime.timedelta(days=40), m, "Ningbo")     # 40 dni

    data = client.get("/api/stats/transit-trend", headers=admin_headers).json()
    point = next(p for p in data["overall"] if p["month"] == key)
    assert point["count"] == 2
    assert point["avg_days"] == 35.0
    ports = {p["port"]: p["points"] for p in data["by_port"]}
    assert ports["Shanghai"][0]["avg_days"] == 30.0
    assert ports["Ningbo"][0]["avg_days"] == 40.0


def test_transit_trend_scope_excludes_other_company(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    acme = _company_id(client, admin_headers, "ACME")
    today = today_pl()
    c = _container(client, admin_headers, VALID[2], acme)
    _finish(c["id"], today - datetime.timedelta(days=25), today)

    client.post("/api/users", headers=admin_headers, json={
        "login": "log.borealis", "password": "haslo123", "role": "logistics",
        "company_id": borealis})
    hdrs = login(client, "log.borealis", "haslo123")
    data = client.get("/api/stats/transit-trend", headers=hdrs).json()
    assert sum(p["count"] for p in data["overall"]) == 0  # cudza spółka niewidoczna


def test_occupancy_forecast_buckets_and_scope(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    acme = _company_id(client, admin_headers, "ACME")
    today = today_pl()
    # tydzień 1: dwa kontenery (10+5 palet), tydzień 3: jeden bez palet
    _container(client, admin_headers, VALID[0], borealis,
               notify_date=(today + datetime.timedelta(days=1)).isoformat(),
               pallet_count=10)
    _container(client, admin_headers, VALID[1], borealis,
               notify_date=(today + datetime.timedelta(days=6)).isoformat(),
               pallet_count=5)
    _container(client, admin_headers, VALID[2], borealis,
               notify_date=(today + datetime.timedelta(days=15)).isoformat())
    # poza oknem 28 dni — nie liczy się
    _container(client, admin_headers, VALID[3], borealis,
               notify_date=(today + datetime.timedelta(days=40)).isoformat())

    data = client.get("/api/stats/occupancy-forecast", headers=admin_headers).json()
    weeks = data["weeks"]
    assert len(weeks) == 4
    assert weeks[0]["week_start"] == today.isoformat()
    assert weeks[0]["containers"] == 2 and weeks[0]["pallets"] == 15
    assert weeks[1]["containers"] == 0
    assert weeks[2]["containers"] == 1 and weeks[2]["pallets"] == 0

    # scope: użytkownik BOREALIS nie widzi kontenerów ACME
    _container(client, admin_headers, "MSKU1788607", acme,
               notify_date=(today + datetime.timedelta(days=2)).isoformat(),
               pallet_count=99)
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.borealis2", "password": "haslo123", "role": "logistics",
        "company_id": borealis})
    hdrs = login(client, "log.borealis2", "haslo123")
    mine = client.get("/api/stats/occupancy-forecast", headers=hdrs).json()["weeks"]
    assert mine[0]["containers"] == 2 and mine[0]["pallets"] == 15

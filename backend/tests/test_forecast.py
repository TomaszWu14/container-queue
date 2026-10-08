"""Prognoza obciążenia magazynów (Analityka F2): endpoint + alert przekroczeń."""
import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Container, ContainerStatus, Notification, today_pl
from app.notifications import check_forecast_alerts
from tests.conftest import login

VALID = ["MSDU0806613", "CSQU3054383", "TGHU9876537", "CSNU0110266"]


def _setup(client, admin_headers, limit=2):
    companies = client.get("/api/companies", headers=admin_headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "MAG-F2", "company_id": borealis, "default_daily_limit": limit}).json()
    return borealis, wh


def _container(client, headers, no, company_id, wh_id, notify_date, pallets=None):
    body = {"container_no": no, "company_id": company_id, "warehouse_id": wh_id,
            "notify_date": notify_date}
    if pallets is not None:
        body["pallet_count"] = pallets
    resp = client.post("/api/containers", headers=headers, json=body)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def test_forecast_counts_and_pallet_estimates(client, admin_headers):
    borealis, wh = _setup(client, admin_headers)
    tomorrow = (today_pl() + datetime.timedelta(days=1)).isoformat()

    # historia: zakończony kontener z paletami → średnia dostawcy/globalna = 20
    hist = _container(client, admin_headers, VALID[0], borealis, wh["id"],
                      (today_pl() - datetime.timedelta(days=10)).isoformat(),
                      pallets=20)
    with SessionLocal() as db:
        c = db.get(Container, hist["id"])
        c.status = ContainerStatus.ZREALIZOWANY
        db.commit()

    # przyszłość: jeden z paletami (12), jeden bez (→ szacunek 20)
    _container(client, admin_headers, VALID[1], borealis, wh["id"], tomorrow, pallets=12)
    _container(client, admin_headers, VALID[2], borealis, wh["id"], tomorrow)

    data = client.get("/api/analysis/forecast?company_code=BOREALIS",
                      headers=admin_headers).json()
    w = next(x for x in data["warehouses"] if x["id"] == wh["id"])
    day = next(d for d in w["days"] if d["date"] == tomorrow)
    assert day["containers"] == 2
    assert day["limit"] == 2 and day["over"] is False
    assert day["pallets"] == 32 and day["pallets_estimated"] is True

    # rola magazynu nie ma dostępu do prognozy
    client.post("/api/users", headers=admin_headers, json={
        "login": "mag.f2", "password": "haslo123", "role": "warehouse",
        "company_id": borealis, "warehouse_id": wh["id"]})
    mag = login(client, "mag.f2", "haslo123")
    assert client.get("/api/analysis/forecast?company_code=BOREALIS",
                      headers=mag).status_code == 403


def test_forecast_overload_alert(client, admin_headers):
    borealis, wh = _setup(client, admin_headers, limit=1)
    tomorrow = (today_pl() + datetime.timedelta(days=1)).isoformat()
    _container(client, admin_headers, VALID[1], borealis, wh["id"], tomorrow)
    _container(client, admin_headers, VALID[2], borealis, wh["id"], tomorrow)  # 2 > limit 1

    assert check_forecast_alerts(db=SessionLocal()) >= 1
    assert check_forecast_alerts(db=SessionLocal()) == 0   # dedup dzienny
    with SessionLocal() as db:
        alerts = db.scalars(select(Notification).where(
            Notification.kind == "forecast-overload")).all()
        assert alerts and "MAG-F2" in alerts[0].title

    # w granicach limitu nie alarmuje (świeży magazyn z limitem 5)
    wh2 = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "MAG-OK", "company_id": borealis, "default_daily_limit": 5}).json()
    _container(client, admin_headers, VALID[3], borealis, wh2["id"], tomorrow)
    check_forecast_alerts(db=SessionLocal())
    with SessionLocal() as db:
        assert not [a for a in db.scalars(select(Notification).where(
            Notification.kind == "forecast-overload")).all() if "MAG-OK" in a.title]


def _overload_titles(name):
    with SessionLocal() as db:
        return [a.title for a in db.scalars(select(Notification).where(
            Notification.kind == "forecast-overload")).all() if name in a.title]


def test_forecast_limit_per_warehouse_not_per_company_and_skips_transit(
        client, admin_headers):
    """Reguła jak w kolejce: limit magazynu liczony łącznie dla wszystkich spółek,
    kontenery tranzytowe (is_transit) nie liczą się do dziennego limitu."""
    from app.models import Company
    borealis, wh = _setup(client, admin_headers, limit=2)
    wh_transit = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "MAG-TRANZYT", "company_id": borealis, "default_daily_limit": 2}).json()
    tomorrow = today_pl() + datetime.timedelta(days=1)
    with SessionLocal() as db:
        other = db.scalars(select(Company).where(Company.id != borealis)).first()
        # MAG-F2: 1 BOREALIS + 2 innej spółki = 3 > 2 (per spółka żadna grupa nie przekracza)
        for no, co in (("AAAU1000001", borealis), ("AAAU1000002", other.id),
                       ("AAAU1000003", other.id)):
            db.add(Container(container_no=no, company_id=co, warehouse_id=wh["id"],
                             notify_date=tomorrow))
        # MAG-TRANZYT: 2 zwykłe + 1 tranzyt = w limicie
        for no, transit in (("AAAU2000001", False), ("AAAU2000002", False),
                            ("AAAU2000003", True)):
            db.add(Container(container_no=no, company_id=borealis, notify_date=tomorrow,
                             warehouse_id=wh_transit["id"], is_transit=transit))
        db.commit()

    check_forecast_alerts(db=SessionLocal())
    assert any("3 rozładunków" in t for t in _overload_titles("MAG-F2"))
    assert not _overload_titles("MAG-TRANZYT")

"""W1 kolejka: fill-summary (batch % wypełnienia) + kolizje transportowe (paczka
TransportJob z dostawami tego samego dnia w różnych magazynach)."""
from app.models import today_pl
import datetime

from sqlalchemy import select

from app.models import (
    Container,
    ContainerType,
    MaterialUnit,
    Order,
    OrderItem,
    TransportJob,
    TransportJobContainer,
)
from tests.conftest import login

VALID = ["MSDU0806613", "CSQU3054383", "TGHU9876537", "CSNU0110266", "MSKU5696108"]


def _company_id(client, headers, code="BOREALIS"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _container(client, headers, no, company_id, **extra):
    resp = client.post("/api/containers", headers=headers,
                       json={"container_no": no, "company_id": company_id, **extra})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _seed_packing(client, headers, db_session, no, company_id):
    """Kontener z typem 20'DV + pozycją z wymiarami MARM (jak test_container_packing)."""
    cid = _container(client, headers, no, company_id)["id"]
    order = Order(number=f"Z-{no}", company_id=company_id,
                  container_type_id=db_session.scalars(select(ContainerType).where(
                      ContainerType.name == "20'DV")).one().id)
    db_session.add(order)
    db_session.flush()
    if not db_session.scalar(select(OrderItem).where(
            OrderItem.order_number == "4500022222")):
        db_session.add(OrderItem(company_id=company_id, order_number="4500022222",
                                 material="200300", quantity="3", unit="KAR"))
        db_session.add(MaterialUnit(material_no="200300", unit="KAR", length=600,
                                    width=400, height=300, dimension_unit="MM"))
    db_session.query(Container).filter(Container.id == cid).update(
        {"order_id": order.id, "order_numbers": "4500022222"})
    db_session.commit()
    return cid


def test_fill_summary_batch(client, admin_headers, db_session):
    company_id = _company_id(client, admin_headers)
    with_data = _seed_packing(client, admin_headers, db_session, VALID[0], company_id)
    bare = _container(client, admin_headers, VALID[1], company_id)["id"]

    r = client.get(f"/api/containers/fill-summary?ids={with_data},{bare},999999",
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body[str(with_data)] and body[str(with_data)] > 0   # policzony %
    assert body[str(bare)] is None                             # brak danych → null
    assert "999999" not in body                                # obcy/nieistniejący znika


def test_fill_summary_forbidden_for_warehouse(client, admin_headers):
    company_id = _company_id(client, admin_headers)
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "MAG-W1-U", "company_id": company_id}).json()
    r = client.post("/api/users", headers=admin_headers, json={
        "login": "mag.w1", "password": "haslo123", "role": "warehouse",
        "company_id": company_id, "warehouse_id": wh["id"]})
    assert r.status_code in (200, 201), r.text
    mag = login(client, "mag.w1", "haslo123")
    assert client.get("/api/containers/fill-summary?ids=1",
                      headers=mag).status_code == 403


def _job_with(db_session, number, container_ids):
    job = TransportJob(number=number)
    db_session.add(job)
    db_session.flush()
    for cid in container_ids:
        db_session.add(TransportJobContainer(job_id=job.id, container_id=cid))
    db_session.commit()
    return job.id


def test_transport_conflict_detected_and_warned_on_save(client, admin_headers, db_session):
    company_id = _company_id(client, admin_headers)
    day = (today_pl() + datetime.timedelta(days=2)).isoformat()
    wh_a = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "MAG-W1-A", "company_id": company_id}).json()
    wh_b = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "MAG-W1-B", "company_id": company_id}).json()
    c1 = _container(client, admin_headers, VALID[2], company_id,
                    warehouse_id=wh_a["id"], notify_date=day)
    c2 = _container(client, admin_headers, VALID[3], company_id,
                    warehouse_id=wh_a["id"], notify_date=day)
    _job_with(db_session, "TJ-W1-1", [c1["id"], c2["id"]])

    # ten sam magazyn → bez kolizji
    r = client.get("/api/containers/transport-conflicts", headers=admin_headers).json()
    assert all(x["container_id"] not in (c1["id"], c2["id"]) for x in r["conflicts"])

    # zapis magazynu rozjeżdża paczkę → ostrzeżenie w odpowiedzi PATCH (nie blokada)
    upd = client.patch(f"/api/containers/{c2['id']}", headers=admin_headers,
                       json={"warehouse_id": wh_b["id"]})
    assert upd.status_code == 200, upd.text
    assert upd.json()["transport_conflict"] == ["MAG-W1-A", "MAG-W1-B"]

    # ...i jest widoczne w zbiorczym endpoincie dla obu kontenerów
    r = client.get("/api/containers/transport-conflicts", headers=admin_headers).json()
    hit = {x["container_id"]: x for x in r["conflicts"]}
    assert c1["id"] in hit and c2["id"] in hit
    assert hit[c1["id"]]["job_number"] == "TJ-W1-1"
    assert hit[c1["id"]]["warehouses"] == ["MAG-W1-A", "MAG-W1-B"]

    # inna data = inny dzień dostawy → kolizja znika
    upd = client.patch(f"/api/containers/{c2['id']}", headers=admin_headers, json={
        "notify_date": (today_pl() + datetime.timedelta(days=3)).isoformat()})
    assert upd.status_code == 200
    assert upd.json()["transport_conflict"] is None
    r = client.get("/api/containers/transport-conflicts", headers=admin_headers).json()
    assert all(x["container_id"] not in (c1["id"], c2["id"]) for x in r["conflicts"])

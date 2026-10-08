"""Wyceny a izolacja: zlecenie z kontenerami dwóch spółek (albo spoza magazynów logistyka)
ujawniało logistykowi spółki A oferty/ceny/kontenery spółki B. Teraz: nie da się utworzyć
zlecenia mieszanego, a zlecenie widać tylko, gdy WSZYSTKIE jego kontenery są w zakresie."""
from app.database import SessionLocal
from app.models import Container, TransportJob, TransportJobContainer, Warehouse
from tests.conftest import forwarder, login
from tests.test_quotes import _company_id, _container


def _job(client, headers, container_ids):
    spedalfa = forwarder(client, headers, "SPEDALFA")["id"]
    return client.post("/api/transport-jobs", headers=headers, json={
        "container_ids": container_ids, "forwarder_ids": [spedalfa],
        "pickup_location": "A", "delivery_location": "B"})


def _logistics(client, admin_headers, company_id, warehouses=None):
    uid = client.post("/api/users", headers=admin_headers, json={
        "login": "log.zakres", "password": "haslo123", "role": "logistics",
        "company_id": company_id, "view_all_companies": False}).json()["id"]
    if warehouses:
        client.patch(f"/api/users/{uid}", headers=admin_headers,
                     json={"allowed_warehouse_ids": warehouses})
    return login(client, "log.zakres", "haslo123")


def test_job_with_two_companies_is_rejected(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    acme = _company_id(client, admin_headers, "ACME")
    ct = _container(client, admin_headers, "MSDU0806613", borealis)
    cz = _container(client, admin_headers, "CSQU3054383", acme)
    r = _job(client, admin_headers, [ct, cz])
    assert r.status_code == 422 and "spółki" in r.json()["detail"]
    assert _job(client, admin_headers, [ct]).status_code == 201


def test_legacy_mixed_job_hidden_from_scoped_logistics(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    acme = _company_id(client, admin_headers, "ACME")
    ct = _container(client, admin_headers, "MSDU0806613", borealis)
    cz = _container(client, admin_headers, "CSQU3054383", acme)
    job = _job(client, admin_headers, [ct]).json()
    with SessionLocal() as db:   # zlecenie mieszane sprzed poprawki
        db.add(TransportJobContainer(job_id=job["id"], container_id=cz))
        db.commit()
    log_h = _logistics(client, admin_headers, borealis)
    assert job["id"] not in [j["id"] for j in client.get("/api/transport-jobs", headers=log_h).json()]
    assert client.get(f"/api/transport-jobs/{job['id']}", headers=log_h).status_code == 404
    assert client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).status_code == 200


def test_job_outside_allowed_warehouses_hidden(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    with SessionLocal() as db:
        wa, wb = Warehouse(name="RFQ-MAG-A", company_id=borealis), Warehouse(name="RFQ-MAG-B", company_id=borealis)
        db.add_all([wa, wb])
        db.flush()
        ca = Container(container_no="MSDU0806613", company_id=borealis, warehouse_id=wa.id)
        cb = Container(container_no="CSQU3054383", company_id=borealis, warehouse_id=wb.id)
        db.add_all([ca, cb])
        db.commit()
        wa_id, ca_id, cb_id = wa.id, ca.id, cb.id
    job_a = _job(client, admin_headers, [ca_id]).json()
    job_b = _job(client, admin_headers, [cb_id]).json()
    log_h = _logistics(client, admin_headers, borealis, warehouses=[wa_id])
    ids = [j["id"] for j in client.get("/api/transport-jobs", headers=log_h).json()]
    assert job_a["id"] in ids and job_b["id"] not in ids
    assert client.get(f"/api/transport-jobs/{job_b['id']}", headers=log_h).status_code == 404
    assert client.get(f"/api/transport-jobs/{job_a['id']}", headers=log_h).status_code == 200
    with SessionLocal() as db:
        assert db.get(TransportJob, job_b["id"]) is not None

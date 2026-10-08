import datetime

from app.models import AuditLog, PurchaseOrder, TrackedVessel, TrackingEvent, VesselPortCall

from .conftest import login


def _mk_container(client, admin_headers, **extra):
    payload = {"container_no": "CSNU0110266", "company_id": 1, **extra}
    r = client.post("/api/containers", headers=admin_headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_timeline_merges_and_sorts_sources(client, admin_headers, db_session):
    c = _mk_container(client, admin_headers,
                      vessel="MV DEMO ATLAS", eta="2099-01-10", notify_date="2099-01-14")
    cid = c["id"]
    db_session.add(PurchaseOrder(company_id=1, order_no="PO-1", container_id=cid,
                                 etd=datetime.date(2025, 12, 1), port_of_departure="Ningbo"))
    db_session.add(TrackingEvent(container_id=cid, event_code="DEPART",
                                 description="Vessel departure", location="Ningbo",
                                 occurred_at=datetime.datetime(2025, 12, 2, 8, 0)))
    v = TrackedVessel(name="MV DEMO ATLAS")
    db_session.add(v); db_session.flush()
    db_session.add(VesselPortCall(vessel_id=v.id, port="Singapore",
                                  arrived_at=datetime.datetime(2025, 12, 10, 6, 0),
                                  departed_at=datetime.datetime(2025, 12, 11, 2, 0)))
    db_session.add(AuditLog(entity_type="containers", entity_id=cid, field="status",
                            old_value="ZAPOWIEDZIANY", new_value="W_TRANSPORCIE",
                            created_at=datetime.datetime(2025, 12, 2, 9, 0)))
    db_session.commit()

    entries = client.get(f"/api/containers/{cid}/timeline",
                         headers=admin_headers).json()
    kinds = [e["kind"] for e in entries]
    # wszystkie źródła obecne
    assert {"order", "carrier", "vessel", "system", "planned"} <= set(kinds)
    # sort chronologiczny (None na końcu)
    ats = [e["at"] for e in entries if e["at"]]
    assert ats == sorted(ats)
    # przyszłe ETA/awizacja jako planned + estimated (+ okno demurrage z ETA)
    planned = [e for e in entries if e["kind"] == "planned"]
    assert {p["code"] for p in planned} == {"ETA", "NOTIFY", "DEMURRAGE"}
    assert all(p["estimated"] for p in planned)


def test_timeline_demurrage_from_eta_is_estimated(client, admin_headers):
    # brak faktycznego przybycia → start z ETA, wpis szacowany, wolne dni z defaultu (5)
    c = _mk_container(client, admin_headers, eta="2099-01-10")
    entries = client.get(f"/api/containers/{c['id']}/timeline",
                         headers=admin_headers).json()
    dem = next(e for e in entries if e["code"] == "DEMURRAGE")
    assert dem["estimated"] is True
    assert dem["at"].startswith("2099-01-15")   # ETA + 5 dni wolnych (default)
    assert "5 dni od 2099-01-10" in dem["title"]


def test_timeline_demurrage_from_discharge_event(client, admin_headers, db_session):
    # faktyczny wyładunek (DISCHARGE) wygrywa z ETA; nadpisane wolne dni kontenera
    c = _mk_container(client, admin_headers, eta="2099-01-10")
    client.patch(f"/api/containers/{c['id']}", headers=admin_headers,
                 json={"demurrage_free_days": 3})
    db_session.add(TrackingEvent(container_id=c["id"], event_code="DISCHARGE",
                                 description="Discharged", location="Gdansk",
                                 occurred_at=datetime.datetime(2099, 1, 8, 10, 0)))
    db_session.commit()
    entries = client.get(f"/api/containers/{c['id']}/timeline",
                         headers=admin_headers).json()
    dem = next(e for e in entries if e["code"] == "DEMURRAGE")
    assert dem["estimated"] is False
    assert dem["at"].startswith("2099-01-11")   # wyładunek 01-08 + 3 dni wolne


def test_timeline_no_eta_no_demurrage_entry(client, admin_headers):
    c = _mk_container(client, admin_headers)
    entries = client.get(f"/api/containers/{c['id']}/timeline",
                         headers=admin_headers).json()
    assert not any(e["code"] == "DEMURRAGE" for e in entries)


def test_timeline_no_tracking_gives_system_history_only(client, admin_headers, db_session):
    c = _mk_container(client, admin_headers)
    db_session.add(AuditLog(entity_type="containers", entity_id=c["id"], field="status",
                            old_value=None, new_value="ZAPOWIEDZIANY"))
    db_session.commit()
    entries = client.get(f"/api/containers/{c['id']}/timeline",
                         headers=admin_headers).json()
    assert entries and all(e["kind"] == "system" for e in entries)


def test_timeline_isolation_other_company(client, admin_headers):
    # user innej firmy nie widzi kontenera — wzorzec z test_isolation.py:
    # firma 2 + user viewer w firmie 2, kontener w firmie 1
    c = _mk_container(client, admin_headers)
    comp = client.post("/api/companies", headers=admin_headers,
                       json={"name": "Obca", "code": "OBC"}).json()
    r = client.post("/api/users", headers=admin_headers,
                    json={"login": "obcy", "password": "obcy1234!", "role": "logistics",
                          "company_id": comp["id"], "view_all_companies": False})
    assert r.status_code == 201, r.text
    other = login(client, "obcy", "obcy1234!")
    r = client.get(f"/api/containers/{c['id']}/timeline", headers=other)
    assert r.status_code in (403, 404)

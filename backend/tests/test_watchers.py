"""„Śledzone przez…": lista obserwujących kontener/statek, filtr ról, izolacja statku."""
from app.database import SessionLocal
from app.models import Container, Role, TrackedVessel, User, Warehouse
from app.routers.watchers import can_see_watcher
from app.security import hash_password
from tests.conftest import login


def _company_id(client, headers, code="ACME"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _user(login_name, role, company_id, full_name="", warehouse_id=None):
    with SessionLocal() as db:
        u = User(login=login_name, hashed_password=hash_password("pass12345"),
                 role=role, company_id=company_id, view_all_companies=False,
                 full_name=full_name, email="", warehouse_id=warehouse_id)
        db.add(u)
        db.commit()
        return u.id


def _container(client, headers, no, company_id, vessel="", warehouse_id=None):
    r = client.post("/api/containers", headers=headers, json={
        "container_no": no, "company_id": company_id, "vessel": vessel})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    if warehouse_id is not None:
        with SessionLocal() as db:
            c = db.get(Container, cid)
            c.warehouse_id = warehouse_id
            db.commit()
    return cid


def test_container_watchers_list_for_internal(client):
    admin = login(client)
    acme = _company_id(client, admin)
    cid = _container(client, admin, "TGBU6784203", acme)
    _user("logi1", Role.logistics, acme, full_name="Jan Kowalski")
    logi = login(client, "logi1", "pass12345")

    client.post(f"/api/containers/{cid}/watch", headers=admin, json={"reason": "Reklamacja"})
    client.post(f"/api/containers/{cid}/watch", headers=logi, json={})

    data = client.get(f"/api/containers/{cid}/watchers", headers=logi).json()
    assert data["watching"] is True
    assert [w["reason"] for w in data["watchers"]] == ["Reklamacja", ""]
    assert data["watchers"][1]["name"] == "Jan Kowalski"
    assert data["watchers"][0]["created_at"]


def test_warehouse_sees_other_watchers(client):
    """Magazynier z dostępem do kontenera widzi też innych obserwujących (decyzja 2026-09-25)."""
    admin = login(client)
    acme = _company_id(client, admin)
    with SessionLocal() as db:
        w = Warehouse(name="W1", company_id=acme)
        db.add(w)
        db.commit()
        wid = w.id
    cid = _container(client, admin, "MSDU0806613", acme, warehouse_id=wid)
    uid = _user("magazyn1", Role.warehouse, acme, warehouse_id=wid)
    wh = login(client, "magazyn1", "pass12345")
    client.post(f"/api/containers/{cid}/watch", headers=admin, json={"reason": "Pilne"})
    client.post(f"/api/containers/{cid}/watch", headers=wh, json={})

    body = client.get(f"/api/containers/{cid}/watchers", headers=wh)
    assert body.status_code == 200, body.text
    payload = body.json()
    assert payload["watching"] is True
    assert [w["reason"] for w in payload["watchers"]] == ["Pilne", ""]
    assert payload["watchers"][1]["user_id"] == uid


def test_vessel_watch_toggle_and_scope(client, db_session):
    admin = login(client)
    acme = _company_id(client, admin)
    borealis = _company_id(client, admin, "BOREALIS")
    _container(client, admin, "TGBU6784203", borealis, vessel="MV OBSERWOWANA")
    vessel = TrackedVessel(name="MV OBSERWOWANA")
    db_session.add(vessel)
    db_session.commit()

    r = client.post(f"/api/tracking/vessels/{vessel.id}/watch", headers=admin,
                    json={"reason": "Ryzyko opóźnienia"})
    assert r.json() == {"watching": True}
    data = client.get(f"/api/tracking/vessels/{vessel.id}/watchers", headers=admin).json()
    assert data["watching"] is True
    assert data["watchers"][0]["reason"] == "Ryzyko opóźnienia"

    # user ACME nie ma ładunku na tym statku → 404 (get_vessel_visible)
    _user("logi2", Role.logistics, acme)
    logi = login(client, "logi2", "pass12345")
    assert client.get(f"/api/tracking/vessels/{vessel.id}/watchers",
                      headers=logi).status_code == 404
    assert client.post(f"/api/tracking/vessels/{vessel.id}/watch", headers=logi,
                       json={}).status_code == 404

    # drugi POST zdejmuje obserwację
    assert client.post(f"/api/tracking/vessels/{vessel.id}/watch", headers=admin,
                       json={}).json() == {"watching": False}


def test_vessel_watchers_scoped_to_own_company(client, db_session):
    """I1: statek wspólny dla dwóch spółek — internal-role bez view_all_companies widzi
    tylko obserwujących własnej spółki (plus siebie), nie nazwisk/powodów obcej spółki."""
    admin = login(client)
    acme = _company_id(client, admin)
    borealis = _company_id(client, admin, "BOREALIS")
    _container(client, admin, "TGBU6784203", acme, vessel="MV WSPOLNY")
    _container(client, admin, "MSDU0806613", borealis, vessel="MV WSPOLNY")
    vessel = TrackedVessel(name="MV WSPOLNY")
    db_session.add(vessel)
    db_session.commit()

    _user("logi-z", Role.logistics, acme, full_name="Acme Logi")
    _user("logi-t", Role.logistics, borealis, full_name="Borealis Logi")
    logi_z = login(client, "logi-z", "pass12345")
    logi_t = login(client, "logi-t", "pass12345")

    client.post(f"/api/tracking/vessels/{vessel.id}/watch", headers=logi_z,
               json={"reason": "Acme"})
    client.post(f"/api/tracking/vessels/{vessel.id}/watch", headers=logi_t,
               json={"reason": "Borealis"})

    data_z = client.get(f"/api/tracking/vessels/{vessel.id}/watchers", headers=logi_z).json()
    assert [w["reason"] for w in data_z["watchers"]] == ["Acme"]

    data_t = client.get(f"/api/tracking/vessels/{vessel.id}/watchers", headers=logi_t).json()
    assert [w["reason"] for w in data_t["watchers"]] == ["Borealis"]

    data_admin = client.get(f"/api/tracking/vessels/{vessel.id}/watchers", headers=admin).json()
    assert sorted(w["reason"] for w in data_admin["watchers"]) == ["Acme", "Borealis"]


def test_can_see_watcher_false_when_both_company_id_none():
    """M7: dwaj userzy bez company_id (None == None) nie mogą być „tą samą spółką"."""
    viewer = User(id=1, role=Role.logistics, company_id=None, view_all_companies=False)
    target = User(id=2, role=Role.logistics, company_id=None, view_all_companies=False)
    assert can_see_watcher(viewer, target) is False

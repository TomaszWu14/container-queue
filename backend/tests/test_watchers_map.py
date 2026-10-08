"""Obserwujący doklejeni do mapy i listy statków — jednym zapytaniem, wg reguły widoczności."""
from app.database import SessionLocal
from app.models import Role, TrackedVessel, User
from app.security import hash_password
from tests.conftest import login


def _company_id(client, headers, code="ACME"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _user(login_name, role, company_id):
    with SessionLocal() as db:
        u = User(login=login_name, hashed_password=hash_password("pass12345"), role=role,
                 company_id=company_id, view_all_companies=False, email="")
        db.add(u)
        db.commit()
        return u.id


def test_vessels_list_has_watchers(client, db_session):
    h = login(client)
    acme = _company_id(client, h)
    client.post("/api/containers", headers=h, json={
        "container_no": "TGBU6784203", "company_id": acme, "vessel": "MV MAPA"})
    v = TrackedVessel(name="MV MAPA", lat=10.0, lon=20.0)
    db_session.add(v)
    db_session.commit()
    client.post(f"/api/tracking/vessels/{v.id}/watch", headers=h, json={"reason": "x"})

    vessels = client.get("/api/tracking/vessels", headers=h).json()
    mine = next(x for x in vessels if x["id"] == v.id)
    assert len(mine["watchers"]) == 1
    assert set(mine["watchers"][0]) == {"user_id", "name", "has_avatar"}


def test_map_points_have_watchers_key(client):
    h = login(client)
    data = client.get("/api/tracking/map", headers=h).json()
    for p in data["points"] + data["unlocated"]:
        assert "watchers" in p


def test_vessel_watchers_not_leaked_across_companies_on_list(client, db_session):
    """I3: statek z ładunkiem BOREALIS i ACME, obserwowany przez usera BOREALIS —
    logistyk ACME (bez view_all_companies) widzi statek na liście, ale watchers=[]."""
    admin = login(client)
    acme = _company_id(client, admin)
    borealis = _company_id(client, admin, "BOREALIS")
    client.post("/api/containers", headers=admin, json={
        "container_no": "TGBU6784203", "company_id": acme, "vessel": "MV WYCIEK"})
    client.post("/api/containers", headers=admin, json={
        "container_no": "MSDU0806613", "company_id": borealis, "vessel": "MV WYCIEK"})
    v = TrackedVessel(name="MV WYCIEK")
    db_session.add(v)
    db_session.commit()

    borealis_uid = _user("logi-borealis", Role.logistics, borealis)
    borealis_h = login(client, "logi-borealis", "pass12345")
    client.post(f"/api/tracking/vessels/{v.id}/watch", headers=borealis_h, json={"reason": "x"})

    _user("logi-acme", Role.logistics, acme)
    acme_h = login(client, "logi-acme", "pass12345")
    vessels = client.get("/api/tracking/vessels", headers=acme_h).json()
    mine = next(x for x in vessels if x["id"] == v.id)
    assert mine["watchers"] == []

    vessels_admin = client.get("/api/tracking/vessels", headers=admin).json()
    mine_admin = next(x for x in vessels_admin if x["id"] == v.id)
    assert [w["user_id"] for w in mine_admin["watchers"]] == [borealis_uid]

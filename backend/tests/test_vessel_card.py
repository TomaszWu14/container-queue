"""Karta statku: wymiary z AIS, cargo (izolacja), flaga „specjalny", zdjęcie statku."""
import json

from sqlalchemy import select

from app.database import SessionLocal
from app.models import OrderItem, Role, TrackedVessel, User
from app.security import hash_password
from app.tracking.ais import handle_message
from tests.conftest import login

# minimalny poprawny PNG (sygnatura wystarcza walidacji magic bytes)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _mk_vessel(db, name, **kw):
    vessel = TrackedVessel(name=name, **kw)
    db.add(vessel)
    db.commit()
    return vessel


def _company_id(client, headers, code="ACME"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _mk_container(client, headers, no, vessel, company_id, **extra):
    resp = client.post("/api/containers", headers=headers, json={
        "container_no": no, "vessel": vessel, "company_id": company_id, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _scoped_user(login_name, company_id, role=Role.logistics, **kw):
    with SessionLocal() as db:
        db.add(User(login=login_name, hashed_password=hash_password("pass12345"),
                    role=role, company_id=company_id, view_all_companies=False, **kw))
        db.commit()


# --- wymiary z AIS ShipStaticData ---

def test_static_data_sets_dimensions(db_session):
    vessel = _mk_vessel(db_session, "MV WYMIARY")
    raw = json.dumps({
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": 111000111, "ShipName": "MV WYMIARY"},
        "Message": {"ShipStaticData": {
            "Destination": "PL GDN",
            "Dimension": {"A": 200, "B": 100, "C": 20, "D": 25}}},
    })
    assert handle_message(db_session, raw, {vessel.name: vessel}) is True
    assert vessel.length_m == 300
    assert vessel.beam_m == 45


def test_static_data_zero_dimensions_do_not_overwrite(db_session):
    vessel = _mk_vessel(db_session, "MV ZERA", length_m=300, beam_m=45)
    raw = json.dumps({
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": 111000112, "ShipName": "MV ZERA"},
        "Message": {"ShipStaticData": {"Dimension": {"A": 0, "B": 0, "C": 0, "D": 0}}},
    })
    handle_message(db_session, raw, {vessel.name: vessel})
    assert (vessel.length_m, vessel.beam_m) == (300, 45)


# --- cargo: izolacja per-zasób ---

def test_cargo_scoped_to_user_companies(client, db_session):
    headers = login(client)
    acme = _company_id(client, headers, "ACME")
    borealis = _company_id(client, headers, "BOREALIS")
    _mk_container(client, headers, "TGBU6784203", "MV CARGO", acme,
                  order_numbers="45001234")
    _mk_container(client, headers, "MSDU0806613", "MV CARGO", borealis)
    vessel = _mk_vessel(db_session, "MV CARGO")
    db_session.add(OrderItem(company_id=acme, order_number="45001234", position="10",
                             material="REF001", description="Rękawice", quantity="500",
                             unit="SZT"))
    db_session.commit()

    # admin (view_all) widzi oba kontenery + pozycje
    data = client.get(f"/api/tracking/vessels/{vessel.id}/cargo", headers=headers).json()
    assert {c["container_no"] for c in data["containers"]} \
        == {"TGBU6784203", "MSDU0806613"}
    acme_c = next(c for c in data["containers"] if c["container_no"] == "TGBU6784203")
    assert data["items_visible"] is True
    assert acme_c["items"] == [{"material": "REF001", "description": "Rękawice",
                                 "quantity": "500", "unit": "SZT"}]

    # user spółki BOREALIS widzi tylko swój kontener
    _scoped_user("log-borealis", borealis)
    hdr2 = login(client, "log-borealis", "pass12345")
    data2 = client.get(f"/api/tracking/vessels/{vessel.id}/cargo", headers=hdr2).json()
    assert [c["container_no"] for c in data2["containers"]] == ["MSDU0806613"]

    # statek bez kontenerów usera → 404 (nie zdradzamy istnienia)
    other = _mk_vessel(db_session, "MV OBCY")
    assert client.get(f"/api/tracking/vessels/{other.id}/cargo",
                      headers=hdr2).status_code == 404


def test_cargo_hides_items_for_warehouse(client, db_session):
    headers = login(client)
    acme = _company_id(client, headers)
    wh = client.post("/api/warehouses", headers=headers,
                     json={"name": "MAG-T", "company_id": acme})
    assert wh.status_code in (200, 201), wh.text
    wh_id = wh.json()["id"]
    _mk_container(client, headers, "TGBU6784203", "MV MAGAZYN", acme,
                  order_numbers="45009999", warehouse_id=wh_id)
    vessel = _mk_vessel(db_session, "MV MAGAZYN")
    db_session.add(OrderItem(company_id=acme, order_number="45009999", position="10",
                             material="REF002", quantity="1", unit="SZT"))
    db_session.commit()
    _scoped_user("wh-user", acme, role=Role.warehouse, warehouse_id=wh_id)
    hdr = login(client, "wh-user", "pass12345")
    data = client.get(f"/api/tracking/vessels/{vessel.id}/cargo", headers=hdr).json()
    assert data["items_visible"] is False
    assert data["containers"][0]["items"] == []   # dane handlowe niewidoczne


# --- flaga „specjalny" ---

def test_special_toggle_editors_only(client):
    headers = login(client)
    acme = _company_id(client, headers)
    c = _mk_container(client, headers, "TGBU6784203", "MV FLAGA", acme)
    assert c["is_special"] is False
    r1 = client.post(f"/api/containers/{c['id']}/special", headers=headers)
    assert r1.status_code == 200 and r1.json()["is_special"] is True
    # toggle jest idempotentnym przełącznikiem
    assert client.post(f"/api/containers/{c['id']}/special",
                       headers=headers).json()["is_special"] is False
    # rola czytająca (purchasing) nie może flagować
    _scoped_user("zakupy", acme, role=Role.purchasing)
    hdr = login(client, "zakupy", "pass12345")
    assert client.post(f"/api/containers/{c['id']}/special",
                       headers=hdr).status_code == 403


def test_special_visible_in_tracking_map(client, db_session):
    from app.models import TrackingEvent
    headers = login(client)
    acme = _company_id(client, headers)
    c = _mk_container(client, headers, "TGBU6784203", "MV MAPA", acme,
                      rf_number="RF123")
    db_session.add(TrackingEvent(container_id=c["id"], event_code="DEPART",
                                 description="Wypłynięcie", location="GDANSK"))
    db_session.commit()
    client.post(f"/api/containers/{c['id']}/special", headers=headers)
    data = client.get("/api/tracking/map", headers=headers).json()
    entry = next(p for p in data["points"] + data["unlocated"] if p["id"] == c["id"])
    assert entry["is_special"] is True


# --- zdjęcie statku ---

def test_vessel_photo_upload_and_download(client, db_session, tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    headers = login(client)
    acme = _company_id(client, headers)
    _mk_container(client, headers, "TGBU6784203", "MV FOTO", acme)
    vessel = _mk_vessel(db_session, "MV FOTO")

    # śmieci zamiast obrazu → 422 (walidacja sygnatury, nie Content-Type)
    resp = client.post(f"/api/tracking/vessels/{vessel.id}/photo", headers=headers,
                       files={"file": ("foto.jpg", b"nie-obraz", "image/jpeg")})
    assert resp.status_code == 422

    resp = client.post(f"/api/tracking/vessels/{vessel.id}/photo", headers=headers,
                       files={"file": ("foto.png", PNG, "image/png")})
    assert resp.status_code == 201, resp.text

    got = client.get(f"/api/tracking/vessels/{vessel.id}/photo", headers=headers)
    assert got.status_code == 200
    assert got.content.startswith(b"\x89PNG")
    with SessionLocal() as db:
        v = db.scalar(select(TrackedVessel).where(TrackedVessel.id == vessel.id))
        assert v.photo and (tmp_path / "vessels" / v.photo).is_file()

    # upload tylko dla admina
    _scoped_user("log-foto", acme)
    hdr = login(client, "log-foto", "pass12345")
    assert client.post(f"/api/tracking/vessels/{vessel.id}/photo", headers=hdr,
                       files={"file": ("f.png", PNG, "image/png")}).status_code == 403


def test_vessels_endpoint_exposes_dims_and_photo_flag(client, db_session):
    headers = login(client)
    acme = _company_id(client, headers)
    _mk_container(client, headers, "TGBU6784203", "MV PARAM", acme)
    _mk_vessel(db_session, "MV PARAM", length_m=366, beam_m=51, photo="v1_abc.jpg")
    data = client.get("/api/tracking/vessels", headers=headers).json()
    v = next(x for x in data if x["name"] == "MV PARAM")
    assert (v["length_m"], v["beam_m"], v["has_photo"]) == (366, 51, True)

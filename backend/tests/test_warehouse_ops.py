"""Moduły magazynu W10: propozycje awizacji, brama, czas rozładunku, zdjęcia, obsada."""
import datetime
import itertools

from app.database import SessionLocal
from app.iso6346 import check_digit
from app.models import AuditLog, AvizoItem, AvizoRequest, Company, Forwarder, today_pl
from app.routers.avizo import _hash_token

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
_SERIAL = itertools.count(808833)


def _valid_no() -> str:
    while True:
        base = f"MSDU{next(_SERIAL)}"
        digit = check_digit(base)
        if digit < 10:   # cyfra kontrolna 10 = numer poza ISO 6346, pomijamy serial
            return f"{base}{digit}"


def _mk_container(client, headers, **extra):
    company_id = client.get("/api/companies", headers=headers).json()[0]["id"]
    payload = {"container_no": _valid_no(), "company_id": company_id, **extra}
    payload.pop("status", None)
    r = client.post("/api/containers", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _mk_avizo(container_id: int, raw: str = "cafe" * 12) -> int:
    with SessionLocal() as db:
        company = db.query(Company).first()
        forwarder = db.query(Forwarder).first()
        avizo = AvizoRequest(
            token=_hash_token(raw), company_id=company.id, forwarder_id=forwarder.id,
            expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=1))
        db.add(avizo)
        db.flush()
        db.add(AvizoItem(request_id=avizo.id, container_id=container_id))
        db.commit()
        return avizo.id


# --- #59 propozycja zmiany awizacji ---

def test_avizo_proposal_flow_accept(client, admin_headers):
    c = _mk_container(client, admin_headers)
    raw = "cafe" * 12
    _mk_avizo(c["id"], raw)
    day = (today_pl() + datetime.timedelta(days=3)).isoformat()

    # walidacja godziny
    bad = client.post(f"/api/avizo/{raw}/propose", json={
        "container_id": c["id"], "date": day, "time": "25:99"})
    assert bad.status_code == 422

    r = client.post(f"/api/avizo/{raw}/propose", json={
        "container_id": c["id"], "date": day, "time": "08:30", "note": "wcześniej"})
    assert r.status_code == 201, r.text

    # propozycja widoczna na publicznym linku i na liście logistyki
    pub = client.get(f"/api/avizo/{raw}").json()
    assert pub["proposals"][0]["status"] == "pending"
    lst = client.get("/api/avizo-proposals", headers=admin_headers).json()
    prop = next(p for p in lst if p["container_id"] == c["id"])
    assert prop["proposed_time"] == "08:30"

    # akceptacja jednym klikiem zmienia notify_date + audyt
    acc = client.post(f"/api/avizo-proposals/{prop['id']}/accept", headers=admin_headers)
    assert acc.status_code == 200 and acc.json()["status"] == "accepted"
    fresh = client.get(f"/api/containers/{c['id']}", headers=admin_headers).json()
    assert fresh["notify_date"] == day and fresh["slot_time"] == "08:30"  # bez okien: godzina bez rezerwacji
    with SessionLocal() as db:
        audit = db.query(AuditLog).filter_by(
            entity_type="containers", entity_id=c["id"], field="avizo_proposal").all()
        assert any(a.new_value == "accepted" for a in audit)
    # ponowna decyzja → 409
    assert client.post(f"/api/avizo-proposals/{prop['id']}/accept",
                       headers=admin_headers).status_code == 409


def test_avizo_proposal_reject_reason_visible_on_link(client, admin_headers):
    c = _mk_container(client, admin_headers)
    raw = "beef" * 12
    _mk_avizo(c["id"], raw)
    day = (today_pl() + datetime.timedelta(days=5)).isoformat()
    client.post(f"/api/avizo/{raw}/propose", json={"container_id": c["id"], "date": day})
    prop = client.get("/api/avizo-proposals", headers=admin_headers).json()[0]
    r = client.post(f"/api/avizo-proposals/{prop['id']}/reject",
                    headers=admin_headers, json={"reason": "magazyn pełny"})
    assert r.status_code == 200
    pub = client.get(f"/api/avizo/{raw}").json()
    assert pub["proposals"][0]["status"] == "rejected"
    assert pub["proposals"][0]["reject_reason"] == "magazyn pełny"


def test_avizo_proposal_past_date_rejected(client, admin_headers):
    c = _mk_container(client, admin_headers)
    raw = "dead" * 12
    _mk_avizo(c["id"], raw)
    r = client.post(f"/api/avizo/{raw}/propose", json={
        "container_id": c["id"], "date": "2020-01-01"})
    assert r.status_code == 422


# --- #60 kolejka bramy ---

def test_gate_queue_and_idempotent_checkin(client, admin_headers):
    today = today_pl().isoformat()
    c = _mk_container(client, admin_headers, notify_date=today)
    with SessionLocal() as db:
        from app.models import Container
        db.get(Container, c["id"]).truck_no = "WGM 1234A"
        db.commit()
    r = client.get("/api/gate", headers=admin_headers)
    assert r.status_code == 200
    item = next(i for i in r.json()["items"] if i["id"] == c["id"])
    assert item["truck_no"] == "WGM 1234A" and item["checked_in_at"] is None

    first = client.post(f"/api/gate/{c['id']}/checkin", headers=admin_headers)
    assert first.status_code == 200 and first.json()["already"] is False
    second = client.post(f"/api/gate/{c['id']}/checkin", headers=admin_headers)
    assert second.json()["already"] is True   # idempotentny w dniu
    with SessionLocal() as db:
        rows = db.query(AuditLog).filter_by(
            entity_type="containers", entity_id=c["id"], field="gate-checkin").all()
        assert len(rows) == 1
    item = next(i for i in client.get("/api/gate", headers=admin_headers).json()["items"]
                if i["id"] == c["id"])
    assert item["checked_in_at"] is not None


def test_gate_checkin_sets_ramp_and_delay_entered_in_app(client, admin_headers):
    """2026-10-07 (nic bez logowania): przyjazd i spóźnienie kierowcy wpisuje brama/logistyka —
    przyjazd = PODSTAWIONY jak „Przyjechałem” kierowcy; spóźnienie HH:MM, okno 30 min."""
    c = _mk_container(client, admin_headers, notify_date=today_pl().isoformat())
    assert client.post(f"/api/gate/{c['id']}/checkin", headers=admin_headers).status_code == 200
    item = next(i for i in client.get("/api/gate", headers=admin_headers).json()["items"]
                if i["id"] == c["id"])
    assert item["ramp_stage"] == "PODSTAWIONY"

    url = f"/api/gate/{c['id']}/delay"
    assert client.post(url, headers=admin_headers, json={"eta_time": "jutro"}).status_code == 422
    assert client.post(url, headers=admin_headers, json={"eta_time": "14:30"}).status_code == 200
    assert client.post(url, headers=admin_headers, json={"eta_time": "14:30"}).status_code == 200
    assert client.post(url, headers=admin_headers, json={"eta_time": "15:00"}).status_code == 429
    with SessionLocal() as db:
        rows = db.query(AuditLog).filter_by(entity_type="containers", entity_id=c["id"],
                                            field="driver-delayed").all()
        assert [(r.new_value, r.note) for r in rows] == [("14:30", "wpisane w aplikacji")]
        assert rows[0].user_id is not None


# --- #61 pomiar czasu rozładunku ---

def test_unload_start_stop(client, admin_headers):
    c = _mk_container(client, admin_headers)
    # stop bez startu → 409
    assert client.post(f"/api/containers/{c['id']}/unload/stop",
                       headers=admin_headers).status_code == 409
    start = client.post(f"/api/containers/{c['id']}/unload/start", headers=admin_headers)
    assert start.status_code == 200
    # drugi start w trakcie → 409
    assert client.post(f"/api/containers/{c['id']}/unload/start",
                       headers=admin_headers).status_code == 409
    stop = client.post(f"/api/containers/{c['id']}/unload/stop", headers=admin_headers)
    assert stop.status_code == 200 and "duration_minutes" in stop.json()

    fresh = client.get(f"/api/containers/{c['id']}", headers=admin_headers).json()
    assert fresh["unload_started_at"] and fresh["unload_finished_at"]


# --- #64 zdjęcia z rozładunku + reklamacja z prefillu ---

def test_unload_photo_upload_and_complaint(client, admin_headers):
    c = _mk_container(client, admin_headers)
    # nie-obraz odrzucony po magic bytes
    bad = client.post(f"/api/containers/{c['id']}/unload-photos", headers=admin_headers,
                      files={"file": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 422
    ok = client.post(f"/api/containers/{c['id']}/unload-photos", headers=admin_headers,
                     files={"file": ("foto.png", PNG, "image/png")})
    assert ok.status_code == 201, ok.text
    photo_id = ok.json()["id"]
    lst = client.get(f"/api/containers/{c['id']}/unload-photos", headers=admin_headers)
    assert [p["id"] for p in lst.json()] == [photo_id]

    made = client.post(f"/api/unload-photos/{photo_id}/complaint", headers=admin_headers,
                       json={"description": "uszkodzony karton"})
    assert made.status_code == 201, made.text
    complaint = client.get(f"/api/complaints/{made.json()['complaint_id']}",
                           headers=admin_headers).json()
    assert complaint["container_id"] == c["id"]
    assert complaint["description"] == "uszkodzony karton"
    assert complaint["photo_count"] == 1   # zdjęcie podpięte do draftu


# --- #66 predykcja obsady ---

def test_staffing_forecast(client, admin_headers, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "staffing_pallets_per_person", 40)
    tomorrow = (today_pl() + datetime.timedelta(days=1)).isoformat()
    _mk_container(client, admin_headers,
                  notify_date=tomorrow, pallet_count=90)
    r = client.get("/api/warehouse/staffing", headers=admin_headers)
    assert r.status_code == 200
    day1 = r.json()["days"][0]
    assert day1["day"] == tomorrow
    assert day1["container_pallets"] == 90
    assert day1["suggested_people"] == 3    # ceil(90/40)

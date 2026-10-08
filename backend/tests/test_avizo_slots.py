"""#13 — sloty awizacji: wolne okna magazynu w portalu spedycji, rezerwacja bez kolizji.

Od awizacji dwuetapowej: formularz etapu 1 jest jednorazowy i tylko PROPONUJE slot
(sprawdzany na wolne miejsca), rezerwacja następuje przy zatwierdzeniu przez logistykę."""
import datetime

from app import avizo_workflow as wf
from app.database import SessionLocal
from app.models import AvizoChangeProposal, AvizoItem, AvizoRequest, Company, Container, Forwarder, User, Warehouse
from app.routers.avizo import _hash_token
from app.slots import free_slots

# dzień awizacji zawsze w przyszłości (stała data 2026-10-05 zaczęła łamać walidację
# „data nie może być z przeszłości” i wywracała CI); poniedziałek ≥ 7 dni naprzód — dni
# robocze DAY+1/+2/+5 jak w pierwotnym układzie testów
_today = datetime.date.today()
DAY = _today + datetime.timedelta(days=7 + (-_today.weekday()) % 7)


def _setup(raw: str, cap: int = 1):
    with SessionLocal() as db:
        co = db.query(Company).first()
        fw = db.query(Forwarder).first()
        wh = Warehouse(name=f"WH-SLOT-{raw[:4]}", company_id=co.id,
                       slot_windows="07:00,09:00", slot_capacity=cap)
        db.add(wh)
        db.flush()
        a = Container(container_no=f"SLTA{raw[:3]}0001", company_id=co.id, warehouse_id=wh.id, notify_date=DAY)
        b = Container(container_no=f"SLTB{raw[:3]}0001", company_id=co.id, warehouse_id=wh.id, notify_date=DAY)
        db.add_all([a, b])
        db.flush()
        req = AvizoRequest(token=_hash_token(raw), company_id=co.id, forwarder_id=fw.id,
                           expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=1))
        db.add(req)
        db.flush()
        db.add_all([AvizoItem(request_id=req.id, container_id=a.id),
                    AvizoItem(request_id=req.id, container_id=b.id)])
        db.commit()
        return wh.id, a.id, b.id, req.id


def _approve(req_id):
    with SessionLocal() as db:
        admin = db.query(User).filter_by(login="admin").one()
        wf.approve(db, db.get(AvizoRequest, req_id), admin, "http://test")


def _item(cid, slot="", **kw):
    return {"container_id": cid, "decision": "confirmed", "slot_time": slot, **kw}


def test_slots_listed_booked_and_collision_rejected(client):
    raw = "slot" * 12
    wh_id, a_id, b_id, req_id = _setup(raw)
    body = client.get(f"/api/avizo/{raw}").json()
    item = next(i for i in body["items"] if i["container_id"] == a_id)
    assert item["slots"] == [{"time": "07:00", "free": 1}, {"time": "09:00", "free": 1}]

    # dwa kontenery na jedno okno o pojemności 1 w tym samym formularzu → 409, nic nie zapisane
    clash = client.post(f"/api/avizo/{raw}", json={"items": [_item(a_id, "07:00"),
                                                             _item(b_id, "07:00")]})
    assert clash.status_code == 409
    assert clash.json()["detail"]["code"] == "slot_taken"  # maszynowy kod dla frontu
    assert "07:00" in clash.json()["detail"]["message"]
    ok = client.post(f"/api/avizo/{raw}", json={"items": [_item(a_id, "07:00"), _item(b_id)]})
    assert ok.status_code == 200, ok.text
    with SessionLocal() as db:   # przed zatwierdzeniem slot tylko zaproponowany
        assert db.get(Container, a_id).slot_time == ""
    # formularz jednorazowy
    assert client.post(f"/api/avizo/{raw}", json={"items": [_item(a_id), _item(b_id)]}).status_code == 409
    _approve(req_id)
    with SessionLocal() as db:
        assert db.get(Container, a_id).slot_time == "07:00"
        wh = db.get(Warehouse, wh_id)
        assert free_slots(db, wh, DAY) == [{"time": "07:00", "free": 0}, {"time": "09:00", "free": 1}]


def test_approve_locks_warehouse_before_booking(client, monkeypatch):
    """Decyzja 5: rezerwacja slotu blokuje wiersz magazynu (SELECT … FOR UPDATE) przed
    sprawdzeniem wolnego miejsca — równoległe zatwierdzenia na Postgresie idą po kolei."""
    from sqlalchemy import event

    from app.database import engine

    raw = "lock" * 12
    wh_id, a_id, b_id, req_id = _setup(raw)
    assert client.post(f"/api/avizo/{raw}",
                       json={"items": [_item(a_id, "07:00"), _item(b_id)]}).status_code == 200
    locked = []

    def spy(conn, clauseelement, multiparams, params, execution_options):
        if getattr(clauseelement, "_for_update_arg", None) is not None:
            locked.append(str(clauseelement))

    event.listen(engine, "before_execute", spy)
    try:
        _approve(req_id)
    finally:
        event.remove(engine, "before_execute", spy)
    assert any("warehouses" in sql for sql in locked), locked


def test_slots_endpoint_for_other_day_and_foreign_container(client):
    raw = "sday" * 12
    _, a_id, _, _ = _setup(raw, cap=2)
    r = client.get(f"/api/avizo/{raw}/slots", params={"container_id": a_id, "date": (DAY + datetime.timedelta(days=1)).isoformat()})
    assert r.status_code == 200 and r.json() == [{"time": "07:00", "free": 2}, {"time": "09:00", "free": 2}]
    assert client.get(f"/api/avizo/{raw}/slots",
                      params={"container_id": 999999, "date": (DAY + datetime.timedelta(days=1)).isoformat()}).status_code == 404


def test_warehouse_without_windows_has_no_slots(client):
    with SessionLocal() as db:
        assert free_slots(db, Warehouse(name="x", company_id=1), DAY) == []


def test_date_change_releases_slot(client):
    """Przesunięcie kontenera na inny dzień (np. w kolejce) zwalnia jego slot."""
    raw = "move" * 12
    wh_id, a_id, b_id, req_id = _setup(raw)
    new_day = (DAY + datetime.timedelta(days=2)).isoformat()
    # zmiana terminu + slot w jednym potwierdzeniu — po zatwierdzeniu slot zostaje (ustawiany po dacie)
    assert client.post(f"/api/avizo/{raw}", json={"items": [
        _item(a_id, "09:00", decision="date_change", proposed_date=new_day),
        _item(b_id)]}).status_code == 200
    _approve(req_id)
    with SessionLocal() as db:
        c = db.get(Container, a_id)
        assert c.notify_date.isoformat() == new_day and c.slot_time == "09:00"
        c.notify_date = DAY + datetime.timedelta(days=5)
        db.commit()
        assert db.get(Container, a_id).slot_time == ""


def _accept_proposal(client, headers, raw, cid, day, time):
    r = client.post(f"/api/avizo/{raw}/propose",
                    json={"container_id": cid, "date": day.isoformat(), "time": time})
    assert r.status_code == 201, r.text
    return client.post(f"/api/avizo-proposals/{r.json()['id']}/accept", headers=headers)


def test_accept_proposal_books_proposed_slot(client, admin_headers):
    """Audyt 2026-09-23: akceptacja propozycji zmiany awizacji rezerwuje proponowaną
    godzinę (jak zatwierdzenie etapu 1), zamiast zostawić kontener bez slotu."""
    raw = "prop" * 12
    _, a_id, b_id, _ = _setup(raw)
    with SessionLocal() as db:
        db.get(Container, b_id).slot_time = "07:00"   # 07:00 dnia DAY zajęte (cap 1)
        db.commit()
    nxt = DAY + datetime.timedelta(days=1)
    # zmiana dnia + godzina → slot zapisany po dacie (listener czyści go przy zmianie dnia)
    assert _accept_proposal(client, admin_headers, raw, a_id, nxt, "09:00").status_code == 200
    # zajęty slot → 409, kontener bez zmian
    assert _accept_proposal(client, admin_headers, raw, a_id, DAY, "07:00").status_code == 409
    # sama godzina (ten sam dzień) też zmienia slot
    assert _accept_proposal(client, admin_headers, raw, b_id, DAY, "09:00").status_code == 200
    with SessionLocal() as db:
        a, b = db.get(Container, a_id), db.get(Container, b_id)
        assert (a.notify_date, a.slot_time) == (nxt, "09:00")
        assert (b.notify_date, b.slot_time) == (DAY, "09:00")


def test_proposal_time_vs_warehouse_windows(client, admin_headers):
    """Review #528: godzina propozycji sprawdzana z oknami magazynu już przy zgłoszeniu;
    magazyn bez okien → godzina zapisana bez rezerwacji (nie 409 „zajęty”)."""
    raw = "wins" * 12
    wh_id, a_id, b_id, req_id = _setup(raw)
    # godzina spoza okien → 422 przy zgłoszeniu, propozycja nie powstaje
    r = client.post(f"/api/avizo/{raw}/propose",
                    json={"container_id": a_id, "date": DAY.isoformat(), "time": "14:15"})
    assert r.status_code == 422 and "okn" in r.json()["detail"]
    # propozycja sprzed walidacji (legacy) → 409 z komunikatem o oknach, nie „zajęty”
    with SessionLocal() as db:
        p = AvizoChangeProposal(request_id=req_id, container_id=a_id,
                                proposed_date=DAY, proposed_time="14:15")
        db.add(p)
        db.commit()
        pid = p.id
    r = client.post(f"/api/avizo-proposals/{pid}/accept", headers=admin_headers)
    assert r.status_code == 409 and "poza oknami" in r.json()["detail"]
    # magazyn bez okien → dowolna godzina HH:MM, zapis bez rezerwacji
    with SessionLocal() as db:
        db.get(Warehouse, wh_id).slot_windows = ""
        db.commit()
    nxt = DAY + datetime.timedelta(days=2)
    assert _accept_proposal(client, admin_headers, raw, b_id, nxt, "14:15").status_code == 200
    with SessionLocal() as db:
        b = db.get(Container, b_id)
        assert (b.notify_date, b.slot_time) == (nxt, "14:15")


def test_warehouse_change_releases_slot(client):
    """Slot liczony per (magazyn, dzień, okno): przeniesienie do innego magazynu zwalnia slot,
    inaczej nowy magazyn dostaje nadrezerwację okna (free=-1). Dotyczy FK i relacji."""
    with SessionLocal() as db:
        co = db.query(Company).first()
        wa, wb = (Warehouse(name=f"WH-MV-{n}", company_id=co.id, slot_windows="08:00",
                            slot_capacity=1) for n in "AB")
        db.add_all([wa, wb])
        db.flush()
        # slot podany razem z magazynem przy tworzeniu — nie może zostać skasowany
        x = Container(container_no="SLTX0000001", company_id=co.id, warehouse_id=wb.id,
                      notify_date=DAY, slot_time="08:00")
        y = Container(container_no="SLTY0000001", company_id=co.id, slot_time="08:00",
                      warehouse_id=wa.id, notify_date=DAY)
        db.add_all([x, y])
        db.commit()
        assert (x.slot_time, y.slot_time) == ("08:00", "08:00")
        y.warehouse_id = wa.id           # ten sam magazyn — slot zostaje
        db.commit()
        assert y.slot_time == "08:00"
        y.warehouse_id = wb.id           # zmiana FK (PATCH, sync z Excela)
        db.commit()
        assert y.slot_time == ""
        assert free_slots(db, wb, DAY) == [{"time": "08:00", "free": 0}]
        x.warehouse = wa                 # zmiana przez relację (endpoint nazwy magazynu)
        db.commit()
        assert x.slot_time == ""

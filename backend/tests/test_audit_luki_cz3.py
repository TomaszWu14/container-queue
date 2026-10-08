"""OBS-003 cz. 3: dawne „luki” w śladzie audytowym — kto utworzył wpis słownika, zmienił
ustawienia, kalendarz magazynu albo cele zapasu. Strażnik (test_audit_coverage) sprawdza, że
audyt jest wołany; tu sprawdzamy, że wpis faktycznie ląduje w audit_log z autorem."""
from sqlalchemy import select

from app.models import AuditLog, CalendarDay, Carrier, Company, MaterialStockTarget, User, Warehouse
from tests.conftest import login


def _entries(db, model, field=None):
    db.expire_all()
    q = select(AuditLog).where(AuditLog.entity_type == model.__tablename__)
    if field:
        q = q.where(AuditLog.field == field)
    return db.scalars(q.order_by(AuditLog.id)).all()


def _admin_id(db):
    return db.scalar(select(User.id).where(User.login == "admin"))


def test_created_dictionary_entries_are_audited(client, db_session):
    h = login(client)
    assert client.post("/api/companies", headers=h,
                       json={"name": "Spółka Audyt", "code": "AUD"}).status_code == 201
    assert client.post("/api/carriers", headers=h, json={"name": "Armator Audyt"}).status_code == 201
    company = _entries(db_session, Company, "created")[-1]
    assert (company.new_value, company.user_id) == ("Spółka Audyt", _admin_id(db_session))
    assert _entries(db_session, Carrier, "created")[-1].new_value == "Armator Audyt"


def test_settings_change_records_only_changed_keys(client, db_session):
    h = login(client)
    current = client.get("/api/settings", headers=h).json()
    body = {**current, "complaint_prefix": "RKL"}
    assert client.put("/api/settings", headers=h, json=body).status_code == 200
    rows = db_session.scalars(select(AuditLog).where(AuditLog.entity_type == "app_settings")).all()
    assert [(r.field, r.old_value, r.new_value) for r in rows] == [
        ("complaint_prefix", current["complaint_prefix"], "RKL")]


def test_calendar_day_create_and_change_audited(client, db_session):
    h = login(client)
    company_id = client.get("/api/companies", headers=h).json()[0]["id"]
    resp = client.post("/api/warehouses", headers=h,
                       json={"name": "Magazyn Audyt", "company_id": company_id})
    assert resp.status_code == 201, resp.text
    warehouse_id = resp.json()["id"]
    assert _entries(db_session, Warehouse, "created")[-1].new_value == "Magazyn Audyt"
    day ={"warehouse_id": warehouse_id, "day": "2026-12-24", "is_working": False, "note": "Wigilia"}
    assert client.put("/api/calendar", headers=h, json=day).status_code == 200
    assert client.put("/api/calendar", headers=h,
                      json={**day, "is_working": True}).status_code == 200
    assert _entries(db_session, CalendarDay, "created")[-1].new_value == "2026-12-24 wolny"
    change = _entries(db_session, CalendarDay, "is_working")[-1]
    assert (change.old_value, change.new_value) == ("False", "True")


def test_stock_target_lifecycle_audited(client, db_session):
    h = login(client)
    target = client.post("/api/stock-targets", headers=h,
                         json={"material_no": "MAT-1", "days": 10}).json()
    client.post("/api/stock-targets", headers=h, json={"material_no": "MAT-1", "days": 20})
    assert client.delete(f"/api/stock-targets/{target['id']}", headers=h).status_code == 204
    fields = [(r.field, r.old_value, r.new_value) for r in _entries(db_session, MaterialStockTarget)]
    assert fields == [("created", None, "MAT-1: 10 dni"), ("days", "10", "20"),
                      ("delete", "MAT-1: 20 dni", None)]


def test_checklist_result_change_audited_on_container(client, db_session):
    from tests.test_complaints_w11 import _company_id, _container
    h = login(client)
    cid = _container(client, h, "MSDU0806613", _company_id(client, h))
    point = client.post("/api/checklist-points", headers=h, json={"name": "Plomba"}).json()
    for result in ("OK", "OK", "NOK"):       # drugi zapis bez zmiany = bez wpisu
        client.put(f"/api/containers/{cid}/checklist", headers=h,
                   json={"items": [{"point_id": point["id"], "result": result}]})
    db_session.expire_all()
    rows = db_session.scalars(select(AuditLog).where(
        AuditLog.entity_type == "containers", AuditLog.entity_id == cid,
        AuditLog.field == "checklist").order_by(AuditLog.id)).all()
    assert [(r.old_value, r.new_value, r.note) for r in rows] == [
        (None, "OK", "Plomba: "), ("OK", "NOK", "Plomba: ")]

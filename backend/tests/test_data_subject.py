"""GDPR-005: prawa osoby — eksport danych (art. 15) i anonimizacja kierowcy (art. 17) przez
admina, ze śladem w audycie (kto i po jakich kryteriach — bez samych wartości)."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog, Company, Container, Message, Notification, SmsMessage, User
from tests.conftest import login

URL = "/api/admin/data-subject"


def _user_with_data(client, admin_headers) -> int:
    r = client.post("/api/users", headers=admin_headers, json={
        "login": "jan.rodo", "password": "haslo123", "role": "logistics",
        "email": "Jan.Rodo@example.com", "full_name": "Jan Rodo", "view_all_companies": True})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    with SessionLocal() as db:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        c = Container(company_id=company.id, container_no="MSKU7026499")
        db.add(c)
        db.flush()
        db.add(Message(container_id=c.id, user_id=uid, body="wiadomość Jana"))
        db.add(Notification(user_id=uid, kind="eta", title="ETA", body="zmiana"))
        db.add(AuditLog(entity_type="containers", entity_id=c.id, field="notes",
                        old_value="", new_value="notatka Jana", user_id=uid))
        db.commit()
    return uid


def _driver_container(no="MSKU7026499", phone="600 100 200") -> int:
    with SessionLocal() as db:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        c = Container(company_id=company.id, container_no=no, driver_name="Adam Kierowca",
                      driver_phone=phone, driver_id_no="ABC123456", truck_no="WX1")
        db.add(c)
        db.flush()
        db.add(SmsMessage(container_id=c.id, phone="+48600100200", body="TIMPORYE: dostawa"))
        db.commit()
        return c.id


def test_export_user_by_email(client, admin_headers):
    uid = _user_with_data(client, admin_headers)
    r = client.get(URL, params={"email": "jan.rodo@EXAMPLE.com"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["criteria"] == ["email"] and data["driver"] is None
    [user] = data["users"]
    assert user["account"]["id"] == uid and user["account"]["full_name"] == "Jan Rodo"
    assert [m["body"] for m in user["messages"]["items"]] == ["wiadomość Jana"]
    assert [n["title"] for n in user["notifications"]["items"]] == ["ETA"]
    assert [a["new_value"] for a in user["audit_entries"]["items"]] == ["notatka Jana"]
    with SessionLocal() as db:
        row = db.scalar(select(AuditLog).where(AuditLog.entity_type == "data_subject"))
        assert row.field == "export" and row.new_value == "email"
        assert "example.com" not in (row.note + (row.new_value or ""))


def test_export_driver_by_phone_ignores_formatting(client, admin_headers):
    cid = _driver_container()
    r = client.get(URL, params={"phone": "+48 600-100-200"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    driver = r.json()["driver"]
    assert [c["id"] for c in driver["containers"]] == [cid]
    assert driver["containers"][0]["driver_id_no"] == "ABC123456"
    assert [s["phone"] for s in driver["sms"]] == ["+48600100200"]


def test_criteria_validation_and_admin_only(client, admin_headers):
    for params in ({}, {"name": "Ja"}, {"phone": "12"}, {"email": "bez-malpy"}):
        assert client.get(URL, params=params, headers=admin_headers).status_code == 422, params
    assert client.post("/api/users", headers=admin_headers, json={
        "login": "logistyk", "password": "haslo123", "role": "logistics",
        "view_all_companies": True}).status_code == 201
    hdr = login(client, "logistyk", "haslo123")
    assert client.get(URL, params={"email": "a@b.pl"}, headers=hdr).status_code == 403
    assert client.post(f"{URL}/anonymize-driver", json={"phone": "600100200"},
                       headers=hdr).status_code == 403


def test_anonymize_driver_clears_data_and_copies(client, admin_headers):
    cid = _driver_container()
    other = _driver_container(no="TCLU1234567", phone="")
    r = client.post(f"{URL}/anonymize-driver", json={"phone": "600100200"},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"containers": 1, "sms": 2}
    with SessionLocal() as db:
        c = db.get(Container, cid)
        assert (c.driver_name, c.driver_phone, c.driver_id_no, c.truck_no) == ("", "", "", "")
        assert db.get(Container, other).driver_name == "Adam Kierowca"   # inny numer — bez zmian
        assert all(s.phone == "" for s in db.scalars(select(SmsMessage)))
        admin = db.scalar(select(User).where(User.login == "admin"))
        changes = db.scalars(select(AuditLog).where(
            AuditLog.entity_type == "containers", AuditLog.entity_id == cid)).all()
        assert changes and all(a.user_id == admin.id for a in changes)
        assert db.scalar(select(AuditLog).where(AuditLog.field == "anonymize_driver"))
    again = client.get(URL, params={"phone": "600100200"}, headers=admin_headers).json()
    assert again["driver"]["containers"] == [] and again["driver"]["sms"] == []

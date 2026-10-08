"""N-13 / OBS-002: usunięcie konta = dezaktywacja + anonimizacja. Historia audytu
użytkownika zostaje, a samo usunięcie zostawia wpis `__deleted__` z autorem (adminem)."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog, RefreshToken, User
from tests.conftest import login


def test_delete_user_keeps_audit_and_anonymizes(client, admin_headers):
    r = client.post("/api/users", headers=admin_headers, json={
        "login": "dousuniecia", "email": "dousuniecia@example.com", "full_name": "Jan Kowalski",
        "password": "pass12345", "role": "logistics", "view_all_companies": True})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    hdr = login(client, "dousuniecia", "pass12345")
    with SessionLocal() as db:  # zmiana audytowana wykonana przez tego użytkownika
        db.add(AuditLog(entity_type="containers", entity_id=1, field="status",
                        old_value="a", new_value="b", user_id=uid))
        db.commit()

    r = client.delete(f"/api/users/{uid}", headers=admin_headers)
    assert r.status_code == 204, r.text

    with SessionLocal() as db:
        assert db.scalars(select(AuditLog).where(AuditLog.user_id == uid,
                                                 AuditLog.field == "status")).all()
        mark = db.scalars(select(AuditLog).where(
            AuditLog.entity_type == "users", AuditLog.entity_id == uid,
            AuditLog.field == "__deleted__")).one()
        assert mark.old_value == "dousuniecia"
        assert mark.user.login == "admin"
        u = db.get(User, uid)
        assert u is not None and u.is_active is False
        assert u.login == f"usuniety-{uid}"
        assert u.email == "" and u.full_name == ""
        assert not db.scalars(select(RefreshToken).where(
            RefreshToken.user_id == uid, RefreshToken.revoked.is_(False))).all()
    assert client.get("/api/auth/me", headers=hdr).status_code == 401
    assert client.post("/api/auth/login", data={
        "username": "dousuniecia", "password": "pass12345"}).status_code == 401

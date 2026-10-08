"""Ujednolicony przegląd audytu (#49): lista + filtry + tylko admin."""
from sqlalchemy import select

from app.audit import record
from app.models import Company, Role, User
from app.security import create_access_token

from .conftest import login


def test_audit_lists_and_filters(client, db_session):
    admin = db_session.scalars(select(User)).first()
    record(db_session, entity_type="freight_invoices", entity_id=7, field="status",
           old_value="NOWA", new_value="ZAAKCEPTOWANA", user=admin, note="ok")
    record(db_session, entity_type="containers", entity_id=3, field="status",
           old_value="A", new_value="B", user=admin)
    db_session.commit()
    hdr = login(client)

    assert len(client.get("/api/audit", headers=hdr).json()) >= 2

    fi = client.get("/api/audit?entity_type=freight_invoices", headers=hdr).json()
    assert fi and all(r["entity_type"] == "freight_invoices" for r in fi)
    assert fi[0]["new_value"] == "ZAAKCEPTOWANA" and fi[0]["user_login"] == "admin"

    q = client.get("/api/audit?q=ZAAKCEPTOWANA", headers=hdr).json()
    assert any(r["new_value"] == "ZAAKCEPTOWANA" for r in q)


def test_audit_admin_only(client, db_session):
    co = db_session.scalars(select(Company)).first()
    u = User(login="log-x", hashed_password="x", role=Role.logistics, company_id=co.id)
    db_session.add(u)
    db_session.commit()
    r = client.get("/api/audit", headers={"Authorization": f"Bearer {create_access_token(u)}"})
    assert r.status_code == 403

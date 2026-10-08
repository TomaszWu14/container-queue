"""Decyzja 2026-09-28 (audyt BIZ-004): ZREALIZOWANY ustawia logistyka po zamknięciu formalności;
magazyn potwierdza tylko rozładunek (DOSTARCZONY)."""
from sqlalchemy import select

from app.models import Company, Container, ContainerStatus, Role, User, Warehouse
from app.security import create_access_token


def test_warehouse_cannot_complete_but_logistics_can(client, db_session, admin_headers):
    co = db_session.scalars(select(Company)).first()
    wh = Warehouse(name="MAG-Z", company_id=co.id)
    db_session.add(wh)
    db_session.flush()
    c = Container(company_id=co.id, container_no="MSKU7654321", status=ContainerStatus.DOSTARCZONY,
                  warehouse_id=wh.id)
    u = User(login="mag-z", hashed_password="x", role=Role.warehouse, company_id=co.id, warehouse_id=wh.id)
    db_session.add_all([c, u])
    db_session.commit()
    url = f"/api/containers/{c.id}/status"
    r = client.post(url, headers={"Authorization": f"Bearer {create_access_token(u)}"},
                    json={"status": "ZREALIZOWANY", "note": ""})
    assert r.status_code == 403 and "logistyka" in r.json()["detail"]
    ok = client.post(url, headers=admin_headers, json={"status": "ZREALIZOWANY", "note": ""})
    assert ok.status_code == 200 and ok.json()["status"] == "ZREALIZOWANY"

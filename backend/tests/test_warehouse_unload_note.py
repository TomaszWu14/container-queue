"""Decyzja 2026-09-28 (audyt BIZ-002): magazyn może potwierdzić rozładunek kontenera, który nie jest
awizowany / w dostawie (przyjechał bez awizacji), ale tylko z notatką „dlaczego”."""
from sqlalchemy import select

from app.models import Company, Container, ContainerStatus, Role, User, Warehouse
from app.security import create_access_token


def _mk(db, status):
    co = db.scalars(select(Company)).first()
    wh = db.scalar(select(Warehouse).where(Warehouse.name == "MAG-T")) or Warehouse(name="MAG-T", company_id=co.id)
    db.add(wh)
    db.flush()
    c = Container(company_id=co.id, container_no=f"MSKU{len(status):06d}0"[:11], status=status, warehouse_id=wh.id)
    db.add(c)
    u = db.scalar(select(User).where(User.login == "mag-t")) or User(
        login="mag-t", hashed_password="x", role=Role.warehouse, company_id=co.id, warehouse_id=wh.id)
    db.add(u)
    db.commit()
    return c.id, {"Authorization": f"Bearer {create_access_token(u)}"}


def test_unload_without_avizo_needs_note(client, db_session):
    cid, hdr = _mk(db_session, ContainerStatus.W_PORCIE)
    url = f"/api/containers/{cid}/status"
    r = client.post(url, headers=hdr, json={"status": "DOSTARCZONY", "note": ""})
    assert r.status_code == 422 and "notatki" in r.json()["detail"]
    ok = client.post(url, headers=hdr, json={"status": "DOSTARCZONY", "note": "przyjechał bez awizacji"})
    assert ok.status_code == 200 and ok.json()["status"] == "DOSTARCZONY"


def test_unload_of_avizo_container_needs_no_note(client, db_session):
    cid, hdr = _mk(db_session, ContainerStatus.AWIZOWANY)
    r = client.post(f"/api/containers/{cid}/status", headers=hdr, json={"status": "DOSTARCZONY", "note": ""})
    assert r.status_code == 200, r.text

"""Admin: usuwanie kontenerów z kolejki + czyszczenie całej kolejki."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    Company,
    Container,
    Message,
    PurchaseOrder,
    User,
    WatchedContainer,
)
from tests.conftest import login


def _seed_container(no="MSKU7026499", order_numbers="4500624622"):
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        c = Container(company_id=company.id, container_no=no, order_numbers=order_numbers)
        db.add(c)
        db.flush()
        # dzieci: wiadomość (kasowana) + obserwacja (kasowana)
        admin = db.scalar(select(User).where(User.login == "admin"))
        db.add(Message(container_id=c.id, user_id=admin.id, body="test"))
        db.add(WatchedContainer(container_id=c.id, user_id=admin.id))
        # zamówienie zakupowe (odpinane, nie kasowane)
        db.add(PurchaseOrder(company_id=company.id, order_no="4500624622", container_id=c.id))
        db.commit()
        return c.id
    finally:
        db.close()


def test_delete_single_container_purges_children_unlinks_po(client):
    hdr = login(client)
    cid = _seed_container()
    resp = client.delete(f"/api/containers/{cid}", headers=hdr)
    assert resp.status_code == 204, resp.text
    db = SessionLocal()
    try:
        assert db.get(Container, cid) is None
        assert db.scalar(select(Message).where(Message.container_id == cid)) is None
        assert db.scalar(select(WatchedContainer).where(
            WatchedContainer.container_id == cid)) is None
        # zamówienie zakupowe przetrwało, tylko odpięte
        po = db.scalar(select(PurchaseOrder).where(PurchaseOrder.order_no == "4500624622"))
        assert po is not None and po.container_id is None
    finally:
        db.close()


def test_delete_purges_complaint_grandchildren(client):
    """complaint_problems/photos FK complaints.id bez kaskady — muszą zniknąć razem
    z kontenerem (na Postgresie inaczej FK violation; tu sprawdzamy że purge je obejmuje)."""
    from app.models import (
        Complaint,
        ComplaintPhoto,
        ComplaintProblem,
        ProblemType,
    )
    hdr = login(client)
    cid = _seed_container()
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        pt = ProblemType(name="Uszkodzenie")
        db.add(pt); db.flush()
        c = Complaint(number="REK-1", container_id=cid, company_id=company.id)
        db.add(c); db.flush()
        db.add(ComplaintProblem(complaint_id=c.id, problem_type_id=pt.id))
        db.add(ComplaintPhoto(complaint_id=c.id, filename="a.jpg", stored_name="x-a.jpg"))
        db.commit()
        comp_id = c.id
    finally:
        db.close()
    assert client.delete(f"/api/containers/{cid}", headers=hdr).status_code == 204
    db = SessionLocal()
    try:
        assert db.scalar(select(Complaint).where(Complaint.id == comp_id)) is None
        assert db.scalar(select(ComplaintProblem).where(
            ComplaintProblem.complaint_id == comp_id)) is None
        assert db.scalar(select(ComplaintPhoto).where(
            ComplaintPhoto.complaint_id == comp_id)) is None
    finally:
        db.close()


def test_clear_queue_requires_confirm(client):
    hdr = login(client)
    _seed_container(no="MSKU7026499")
    # bez confirm → 400, nic nie skasowane
    assert client.delete("/api/containers?company_code=ACME", headers=hdr).status_code == 400
    db = SessionLocal()
    try:
        assert db.scalar(select(Container).where(Container.container_no == "MSKU7026499"))
    finally:
        db.close()


def test_clear_queue_scoped_to_company(client):
    hdr = login(client)
    _seed_container(no="MSKU7026499")
    db = SessionLocal()
    try:
        borealis = db.scalar(select(Company).where(Company.code == "BOREALIS"))
        db.add(Container(company_id=borealis.id, container_no="TCLU1234567"))
        db.commit()
    finally:
        db.close()
    resp = client.delete("/api/containers?company_code=ACME&confirm=true", headers=hdr)
    assert resp.status_code == 200 and resp.json()["deleted"] == 1
    db = SessionLocal()
    try:
        assert db.scalar(select(Container).where(Container.container_no == "MSKU7026499")) is None
        # inna spółka nietknięta
        assert db.scalar(select(Container).where(Container.container_no == "TCLU1234567"))
    finally:
        db.close()


def test_delete_container_forbidden_for_non_admin(client):
    login(client)
    cid = _seed_container()
    # logistyk (editor) nie może kasować — tylko admin
    from app.models import Role
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        from app.security import hash_password
        db.add(User(login="log1", hashed_password=hash_password("pass12345"),
                    role=Role.logistics, company_id=company.id))
        db.commit()
    finally:
        db.close()
    hdr = login(client, "log1", "pass12345")
    assert client.delete(f"/api/containers/{cid}", headers=hdr).status_code == 403

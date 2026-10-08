"""Obieg akceptacji faktury transportowej (#42): NOWA→DO_AKCEPTACJI→ZAAKCEPTOWANA|ODRZUCONA."""
from sqlalchemy import select

from app.models import Company, Container, FreightInvoice, FreightInvoiceContainer

from .conftest import login


def _invoice(db):
    company = db.scalars(select(Company)).first()
    container = Container(company_id=company.id, container_no="MSCU7654321")
    db.add(container)
    db.flush()
    inv = FreightInvoice(company_id=company.id, bl_number="BL1", amount=1000, currency="EUR")
    inv.items = [FreightInvoiceContainer(container_id=container.id)]
    db.add(inv)
    db.commit()
    return inv.id


def test_submit_then_approve(client, db_session):
    iid = _invoice(db_session)
    hdr = login(client)   # admin — może tworzyć i zatwierdzać
    r = client.post(f"/api/freight-invoices/{iid}/submit", headers=hdr)
    assert r.status_code == 200 and r.json()["status"] == "DO_AKCEPTACJI"
    r = client.post(f"/api/freight-invoices/{iid}/approve", headers=hdr, json={"note": "ok"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ZAAKCEPTOWANA"
    assert body["approved_by_login"] == "admin" and body["approval_note"] == "ok"
    # ponowna akceptacja zablokowana — nie jest już w DO_AKCEPTACJI
    assert client.post(f"/api/freight-invoices/{iid}/approve", headers=hdr).status_code == 409


def test_reject_then_resubmit(client, db_session):
    iid = _invoice(db_session)
    hdr = login(client)
    client.post(f"/api/freight-invoices/{iid}/submit", headers=hdr)
    r = client.post(f"/api/freight-invoices/{iid}/reject", headers=hdr, json={"note": "zła kwota"})
    assert r.status_code == 200 and r.json()["status"] == "ODRZUCONA"
    assert r.json()["approval_note"] == "zła kwota"
    # odrzucona → można zgłosić ponownie
    r = client.post(f"/api/freight-invoices/{iid}/submit", headers=hdr)
    assert r.status_code == 200 and r.json()["status"] == "DO_AKCEPTACJI"


def test_cannot_approve_before_submit(client, db_session):
    iid = _invoice(db_session)
    hdr = login(client)
    # NOWA nie jest do akceptacji
    assert client.post(f"/api/freight-invoices/{iid}/approve", headers=hdr).status_code == 409


def test_notifications_submit_to_admin_decision_to_author(client, db_session):
    """#50 — zgłoszenie powiadamia admina, decyzja autora faktury (kindy w matrycy reguł)."""
    from app.models import Notification, Role, User
    from app.notifications import NOTIFY_KINDS
    from app.security import create_access_token
    assert {"freight_approval", "freight_decision"} <= set(NOTIFY_KINDS)
    iid = _invoice(db_session)
    inv = db_session.get(FreightInvoice, iid)
    author = User(login="log-fi", hashed_password="x", role=Role.logistics,
                  company_id=inv.company_id, email="")
    db_session.add(author)
    db_session.flush()
    inv.uploaded_by_id = author.id
    db_session.commit()
    author_id = author.id
    admin_id = db_session.scalar(select(User.id).where(User.login == "admin"))

    log_hdr = {"Authorization": f"Bearer {create_access_token(author)}"}
    assert client.post(f"/api/freight-invoices/{iid}/submit", headers=log_hdr).status_code == 200
    db_session.expire_all()
    to_admin = db_session.scalars(select(Notification).where(
        Notification.user_id == admin_id, Notification.kind == "freight_approval")).all()
    assert len(to_admin) == 1 and "BL1" in to_admin[0].title

    r = client.post(f"/api/freight-invoices/{iid}/reject", headers=login(client), json={"note": "zła kwota"})
    assert r.status_code == 200
    db_session.expire_all()
    to_author = db_session.scalars(select(Notification).where(
        Notification.user_id == author_id, Notification.kind == "freight_decision")).all()
    assert len(to_author) == 1 and "odrzucona" in to_author[0].title and to_author[0].body == "zła kwota"

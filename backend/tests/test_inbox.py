"""Inbox „Co dziś" (#47): sygnały + zadania decyzyjne cross-module (akceptacje faktur)."""
from sqlalchemy import select

from app.models import Company, FreightInvoice, Role, User, today_pl
from app.security import create_access_token

from .conftest import login


def test_inbox_shows_freight_approvals_for_admin(client, db_session):
    co = db_session.scalars(select(Company)).first()
    db_session.add(FreightInvoice(company_id=co.id, bl_number="BLX", amount=50,
                                  status="DO_AKCEPTACJI"))
    db_session.commit()
    r = client.get("/api/inbox", headers=login(client)).json()
    assert r["freight_approvals_count"] >= 1
    assert any(a["bl_number"] == "BLX" for a in r["freight_approvals"])
    assert "signals_count" in r and "signals_top" in r


def test_inbox_no_approvals_for_non_admin(client, db_session):
    co = db_session.scalars(select(Company)).first()
    db_session.add(FreightInvoice(company_id=co.id, bl_number="BLY", status="DO_AKCEPTACJI"))
    u = User(login="log-i", hashed_password="x", role=Role.logistics, company_id=co.id)
    db_session.add(u)
    db_session.commit()
    hdr = {"Authorization": f"Bearer {create_access_token(u)}"}
    r = client.get("/api/inbox", headers=hdr).json()
    assert r["freight_approvals"] == []


def _hdr(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def test_inbox_warehouse_tasks_unload_and_no_signals(client, db_session):
    """#26 — magazyn: rozładunek dziś/jutro + zaległe potwierdzenie; bez sygnałów (dane handlowe)."""
    import datetime
    from app.models import Container, ContainerStatus, Warehouse
    co = db_session.scalars(select(Company)).first()
    wh = Warehouse(name="WH-INBOX", company_id=co.id)
    db_session.add(wh)
    db_session.flush()
    today = today_pl()
    mk = lambda no, d, st=ContainerStatus.AWIZOWANY: Container(  # noqa: E731
        container_no=no, company_id=co.id, warehouse_id=wh.id, notify_date=d, status=st)
    db_session.add_all([
        mk("TODAY000001", today), mk("TMRW0000001", today + datetime.timedelta(days=1)),
        mk("LATE0000001", today - datetime.timedelta(days=2)),
        mk("FAR00000001", today + datetime.timedelta(days=5)),
        mk("DONE0000001", today, ContainerStatus.DOSTARCZONY),
    ])
    u = User(login="wh-inbox", hashed_password="x", role=Role.warehouse,
             company_id=co.id, warehouse_id=wh.id)
    db_session.add(u)
    db_session.commit()
    r = client.get("/api/inbox", headers=_hdr(u)).json()
    kinds = {t["container_no"]: t["kind"] for t in r["tasks"]}
    assert kinds == {"TODAY000001": "unload_today", "TMRW0000001": "unload_tomorrow",
                     "LATE0000001": "unload_confirm"}
    assert r["signals_top"] == [] and r["signals_count"] == 0


def test_inbox_forwarder_task_for_issued_order(client, db_session):
    from app.models import Container, Forwarder, TransportOrder, TransportOrderStatus
    co = db_session.scalars(select(Company)).first()
    fw = Forwarder(name="FW-INBOX")
    db_session.add(fw)
    db_session.flush()
    c = Container(container_no="FWDU0000001", company_id=co.id, forwarder_id=fw.id)
    db_session.add(c)
    db_session.flush()
    db_session.add_all([
        TransportOrder(container_id=c.id, company_id=co.id, forwarder_id=fw.id,
                       status=TransportOrderStatus.WYSTAWIONE),
        TransportOrder(container_id=c.id, company_id=co.id, forwarder_id=fw.id,
                       status=TransportOrderStatus.WYKONANE),
    ])
    u = User(login="fw-inbox", hashed_password="x", role=Role.forwarder, forwarder_id=fw.id)
    db_session.add(u)
    db_session.commit()
    r = client.get("/api/inbox?signals=false", headers=_hdr(u)).json()
    assert [t["kind"] for t in r["tasks"]] == ["order_respond"]
    assert r["tasks"][0]["container_no"] == "FWDU0000001"

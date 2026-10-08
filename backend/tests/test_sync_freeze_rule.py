import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company, Container, PlanningStatus
from app.routers.imports import reconcile_queue


def _company(db):
    return db.scalar(select(Company).where(Company.code == "BOREALIS"))


def _raw(no, eta_day, customs="", notify_day=None):
    return {
        "supplier": "ACME", "vessel": "MAERSK",
        "eta": datetime.datetime(2026, 9, eta_day),
        "transport": "kolej", "container_no": no, "order_numbers": "",
        "delivery_note": "", "purchase_note": "", "warehouse": "",
        "incoming_delivery_no": "", "rf_number": "", "forwarder": "",
        "document_flow": "", "customs_agency": "", "customs": customs,
        "notify_date": datetime.datetime(2026, 9, notify_day) if notify_day else None,
        "sent_required": "", "sent_number": "", "sent_status": "",
    }


def _get(db, company, no):
    return db.scalar(select(Container).where(Container.company_id == company.id,
                                             Container.container_no == no))


def test_sync_notify_date_change_resets_confirmed_plan():
    """Kontener uzgodniony ze spedycją (POTWIERDZONE) dostaje nową notify_date z Excela
    -> plan musi wrócić do PROPOZYCJA, inaczej udawałby dalej uzgodniony pod datą,
    której spedycja nigdy nie potwierdziła."""
    db = SessionLocal()
    try:
        company = _company(db)
        no = "MSKU9900014"
        reconcile_queue(db, company, [_raw(no, 1, notify_day=1)], None)
        db.flush()
        c = _get(db, company, no)
        c.planning_status = PlanningStatus.POTWIERDZONE
        db.flush()

        res = reconcile_queue(db, company, [_raw(no, 1, notify_day=5)], None)
        db.flush()

        changed = {f for f, _, _ in res[0]["changes"]}
        assert "notify_date" in changed
        assert c.notify_date == datetime.date(2026, 9, 5)
        assert c.planning_status == PlanningStatus.PROPOZYCJA
    finally:
        db.rollback()
        db.close()


def test_sync_notify_date_change_on_proposal_stays_proposal():
    """Bez wcześniejszego uzgodnienia (PROPOZYCJA) sync po prostu przestawia datę —
    zachowanie sprzed fixa, bez efektu ubocznego resetu."""
    db = SessionLocal()
    try:
        company = _company(db)
        no = "MSKU9900101"
        reconcile_queue(db, company, [_raw(no, 1, notify_day=1)], None)
        db.flush()
        c = _get(db, company, no)
        assert c.planning_status == PlanningStatus.PROPOZYCJA

        res = reconcile_queue(db, company, [_raw(no, 1, notify_day=5)], None)
        db.flush()

        changed = {f for f, _, _ in res[0]["changes"]}
        assert "notify_date" in changed
        assert c.notify_date == datetime.date(2026, 9, 5)
        assert c.planning_status == PlanningStatus.PROPOZYCJA
    finally:
        db.rollback()
        db.close()


def test_sync_without_notify_date_change_keeps_confirmed_plan():
    """Sync, który nie rusza notify_date (np. tylko eta), nie ma prawa dotknąć planu
    uzgodnionego ze spedycją."""
    db = SessionLocal()
    try:
        company = _company(db)
        no = "MSKU9900307"
        reconcile_queue(db, company, [_raw(no, 1, notify_day=1)], None)
        db.flush()
        c = _get(db, company, no)
        c.planning_status = PlanningStatus.POTWIERDZONE
        db.flush()

        res = reconcile_queue(db, company, [_raw(no, 9, notify_day=1)], None)
        db.flush()

        changed = {f for f, _, _ in res[0]["changes"]}
        assert "notify_date" not in changed
        assert "eta" in changed
        assert c.planning_status == PlanningStatus.POTWIERDZONE
    finally:
        db.rollback()
        db.close()

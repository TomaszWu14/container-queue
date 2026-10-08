"""Sync z Excela nie cofa statusu ustawionego w apce, którego arkusz nie umie wyliczyć
(ODPRAWA, W_DOSTAWIE, DOSTARCZONY, ZREALIZOWANY) — regresja z audytu 2026-09-23."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company, Container, ContainerStatus
from app.routers.imports import reconcile_queue
from tests.test_sync import _raw

NO = "MSKU7026492"


def _setup(db, app_status):
    company = db.scalar(select(Company).where(Company.code == "BOREALIS"))
    reconcile_queue(db, company, [_raw(NO, 1)], None)          # nowy -> W_PORCIE z arkusza
    db.flush()
    c = db.scalar(select(Container).where(Container.company_id == company.id,
                                          Container.container_no == NO))
    assert c.status == ContainerStatus.W_PORCIE
    c.status = app_status                                      # np. magazyn potwierdził rozładunek
    db.flush()
    return company, c


def test_two_syncs_do_not_revert_delivered(client):
    db = SessionLocal()
    try:
        company, c = _setup(db, ContainerStatus.DOSTARCZONY)
        for _ in range(3):                                     # sync 1: B<-A, sync 2+: dawniej E wygrywał
            reconcile_queue(db, company, [_raw(NO, 1)], None)
            db.flush()
            assert c.status == ContainerStatus.DOSTARCZONY
    finally:
        db.rollback(); db.close()


def test_excel_change_does_not_revert_app_status_in_conflict(client):
    """Arkusz zmienia dane tak, że wyliczony status też się zmienia (konflikt three-way)."""
    db = SessionLocal()
    try:
        company, c = _setup(db, ContainerStatus.W_DOSTAWIE)
        reconcile_queue(db, company, [_raw(NO, 1)], None)
        db.flush()
        reconcile_queue(db, company, [_raw(NO, 1, customs="odprawiony", notify_day=25)], None)
        db.flush()
        assert c.status == ContainerStatus.W_DOSTAWIE          # AWIZOWANY byłby krokiem wstecz
    finally:
        db.rollback(); db.close()


def test_bootstrap_does_not_revert_finished(client):
    db = SessionLocal()
    try:
        company, c = _setup(db, ContainerStatus.ZREALIZOWANY)
        c.sync_baseline = None                                 # stary kontener sprzed three-way
        db.flush()
        reconcile_queue(db, company, [_raw(NO, 1)], None)
        db.flush()
        assert c.status == ContainerStatus.ZREALIZOWANY
    finally:
        db.rollback(); db.close()


def test_forward_move_from_app_only_status_still_applies(client):
    """ODPRAWA -> AWIZOWANY (arkusz: odprawiony + data rozładunku) to krok w przód — przechodzi."""
    db = SessionLocal()
    try:
        company, c = _setup(db, ContainerStatus.ODPRAWA)
        reconcile_queue(db, company, [_raw(NO, 1, customs="odprawiony", notify_day=25)], None)
        db.flush()
        assert c.status == ContainerStatus.AWIZOWANY
    finally:
        db.rollback(); db.close()

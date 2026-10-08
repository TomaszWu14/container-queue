"""Usuwanie kontenera przy egzekwowanych FK (jak Postgres na produkcji).

SQLite domyślnie nie sprawdza FK — tu włączamy PRAGMA foreign_keys=ON na każdym
połączeniu, więc pominięta tabela-dziecko kończy się IntegrityError jak na prodzie."""
import datetime

import pytest
from sqlalchemy import event, select

from app.database import SessionLocal, engine
from app.models import (
    AvizoChangeProposal,
    ChecklistResult,
    Company,
    Container,
    DeliveryConfirmation,
    FreightInvoiceContainer,
    GoodsReceiptLine,
    SapOrder,
    UnloadPhoto,
)
from tests.conftest import login


def _fk_on(dbapi_conn, _record):
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


@pytest.fixture()
def enforce_fk(client):
    """Zwraca funkcję włączającą FK dla nowych połączeń (woła się ją PO seedzie)."""
    def enable():
        engine.dispose()
        event.listen(engine, "connect", _fk_on)
    yield enable
    if event.contains(engine, "connect", _fk_on):
        event.remove(engine, "connect", _fk_on)
    engine.dispose()


def _seed_children() -> int:
    """Kontener z rekordem w każdej tabeli-dziecku wskazanej w audycie 2026-09-23.
    Seed idzie PRZED włączeniem FK — pozostałe FK dzieci (avizo_requests itd.) mogą
    wisieć, bo kasowanie dziecka nie sprawdza jego własnych FK."""
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        c = Container(company_id=company.id, container_no="MSKU7026499")
        db.add(c)
        db.flush()
        db.add_all([
            ChecklistResult(container_id=c.id, point_id=1, result="OK"),
            GoodsReceiptLine(company_id=company.id, container_id=c.id, order_number="45"),
            UnloadPhoto(container_id=c.id, filename="a.jpg", stored_name="unl-x-a.jpg"),
            FreightInvoiceContainer(invoice_id=1, container_id=c.id),
            DeliveryConfirmation(request_id=1, container_id=c.id, decision="confirmed"),
            AvizoChangeProposal(request_id=1, container_id=c.id,
                                proposed_date=datetime.date(2026, 10, 1)),
            SapOrder(company_id=company.id, order_number="4500000001", container_id=c.id),
        ])
        db.commit()
        return c.id
    finally:
        db.close()


@pytest.mark.parametrize("via_clear_queue", [False, True])
def test_purge_covers_all_fk_children(client, enforce_fk, via_clear_queue):
    hdr = login(client)
    cid = _seed_children()
    enforce_fk()
    if via_clear_queue:
        resp = client.delete("/api/containers?company_code=ACME&confirm=true", headers=hdr)
        assert resp.status_code == 200, resp.text
    else:
        resp = client.delete(f"/api/containers/{cid}", headers=hdr)
        assert resp.status_code == 204, resp.text
    db = SessionLocal()
    try:
        assert db.get(Container, cid) is None
        # zamówienie SAP to rekord własny — przetrwało, tylko odpięte
        sap = db.scalar(select(SapOrder).where(SapOrder.order_number == "4500000001"))
        assert sap is not None and sap.container_id is None
        assert db.scalar(select(UnloadPhoto)) is None
    finally:
        db.close()

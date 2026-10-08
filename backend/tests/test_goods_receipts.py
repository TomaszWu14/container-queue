"""Przyjęcia zakupowe + widok zamówiono vs przyjęto (feature #1 bez zapotrzebowania, #29)."""
from sqlalchemy import select

from app.models import Company, Container, OrderItem

from .conftest import login


def _seed(db):
    company = db.scalars(select(Company)).first()
    container = Container(company_id=company.id, container_no="TEMU1234567",
                          order_numbers="4500000001")
    db.add(container)
    db.add(OrderItem(company_id=company.id, order_number="4500000001", position="10",
                     material="ABC1", description="Rurka", quantity="100", unit="PCS"))
    db.add(OrderItem(company_id=company.id, order_number="4500000001", position="20",
                     material="ABC2", description="Kolanko", quantity="50"))
    db.flush()
    return company, container


def test_order_lines_reflect_receipts(client, db_session):
    _, container = _seed(db_session)
    db_session.commit()
    hdr = login(client)
    cid = container.id

    lines = client.get(f"/api/containers/{cid}/order-lines", headers=hdr).json()
    assert len(lines) == 2 and all(x["status"] == "none" for x in lines)

    assert client.put(f"/api/containers/{cid}/receipts", headers=hdr,
                      json={"order_number": "4500000001", "position": "10",
                            "qty_received": "100"}).status_code == 200
    client.put(f"/api/containers/{cid}/receipts", headers=hdr,
               json={"order_number": "4500000001", "position": "20", "qty_received": "30"})

    lines = {x["position"]: x for x in
             client.get(f"/api/containers/{cid}/order-lines", headers=hdr).json()}
    assert lines["10"]["status"] == "ok" and lines["10"]["received_qty"] == "100"
    assert lines["20"]["status"] == "partial"


def test_receipt_upsert_no_duplicate_and_over(client, db_session):
    _, container = _seed(db_session)
    db_session.commit()
    hdr = login(client)
    cid = container.id
    for qty in ("100", "120"):   # ten sam (order,position) → nadpisanie, nie duplikat
        client.put(f"/api/containers/{cid}/receipts", headers=hdr,
                   json={"order_number": "4500000001", "position": "10", "qty_received": qty})
    recs = client.get(f"/api/containers/{cid}/receipts", headers=hdr).json()
    assert len(recs) == 1 and recs[0]["qty_received"] == "120"
    lines = {x["position"]: x for x in
             client.get(f"/api/containers/{cid}/order-lines", headers=hdr).json()}
    assert lines["10"]["status"] == "over"


def test_receipt_without_order_line_appended_as_over(client, db_session):
    _, container = _seed(db_session)
    db_session.commit()
    hdr = login(client)
    cid = container.id
    client.put(f"/api/containers/{cid}/receipts", headers=hdr,
               json={"order_number": "9999999999", "position": "10", "qty_received": "5",
                     "material": "ZZZ"})
    extra = [x for x in client.get(f"/api/containers/{cid}/order-lines", headers=hdr).json()
             if x["order_number"] == "9999999999"]
    assert len(extra) == 1 and extra[0]["status"] == "over"


def test_three_way_invoiced_column(client, db_session):
    from app.models import InvoiceBatch, InvoiceItem, InvoiceJob
    _, container = _seed(db_session)
    batch = InvoiceBatch(container_id=container.id)
    db_session.add(batch)
    db_session.flush()
    job = InvoiceJob(batch_id=batch.id, filename="f.pdf", stored_name="s.pdf")
    db_session.add(job)
    db_session.flush()
    # zafakturowano ABC1: 60 na zamówione 100 → status_invoice partial; ABC2 bez faktury
    db_session.add(InvoiceItem(job_id=job.id, line_no=1, master_ref="ABC1", qty="60"))
    db_session.commit()
    hdr = login(client)
    lines = {x["position"]: x for x in
             client.get(f"/api/containers/{container.id}/order-lines", headers=hdr).json()}
    assert lines["10"]["invoiced_qty"] == "60" and lines["10"]["status_invoice"] == "partial"
    assert lines["20"]["invoiced_qty"] == "" and lines["20"]["status_invoice"] == "none"


def test_delete_receipt(client, db_session):
    _, container = _seed(db_session)
    db_session.commit()
    hdr = login(client)
    cid = container.id
    rid = client.put(f"/api/containers/{cid}/receipts", headers=hdr,
                     json={"order_number": "4500000001", "position": "10",
                           "qty_received": "100"}).json()["id"]
    assert client.delete(f"/api/containers/{cid}/receipts/{rid}", headers=hdr).status_code == 204
    assert client.get(f"/api/containers/{cid}/receipts", headers=hdr).json() == []

"""Przyjęcia zakupowe (goods receipts) + widok „zamówiono vs przyjęto" per pozycja.

Cykl zamówienie→przyjęcie→faktura liczony pozycyjnie na OrderItem (SAP EKPO): klucz
(kontener, order_number, position). Zakres firmowy egzekwuje get_scoped (fundament D1).
Przyjmować może magazyn/zakupy/logistyka/admin; podgląd — każda rola w zasięgu spółki.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record, record_changes
from ..database import get_db
from ..deps import ContentsReaders as contents_readers
from ..deps import get_scoped
from ..models import (
    Container,
    GoodsReceiptLine,
    InvoiceBatch,
    InvoiceItem,
    InvoiceJob,
    OrderItem,
    Role,
    User,
)
from ..schemas import OrderLineOut, ReceiptLineIn, ReceiptLineOut
from ..security import require_roles
from ..models import quantity_value
from ..tabular import to_float
from .containers import container_order_numbers

router = APIRouter(prefix="/api/containers", tags=["zakupy"])

receiver = Depends(require_roles(Role.admin, Role.logistics, Role.purchasing, Role.warehouse))


def _status(ordered, received) -> str:
    o, r = to_float(ordered), to_float(received)
    if o is None:
        return "unknown"          # zamówiona ilość nie-liczbowa — nie da się porównać
    if r is None or r == 0:
        return "none"
    if abs(r - o) < 1e-9:
        return "ok"
    return "over" if r > o else "partial"


def _invoiced_by_ref(db: Session, container_id: int) -> dict[str, float]:
    """Suma zafakturowanych ilości per ref (master_ref pozycji faktur tego kontenera).
    Faktury kontenera: InvoiceBatch(container) → InvoiceJob → InvoiceItem."""
    rows = db.execute(
        select(InvoiceItem.master_ref, InvoiceItem.qty)
        .join(InvoiceJob, InvoiceItem.job_id == InvoiceJob.id)
        .join(InvoiceBatch, InvoiceJob.batch_id == InvoiceBatch.id)
        .where(InvoiceBatch.container_id == container_id)).all()
    agg: dict[str, float] = {}
    for ref, qty in rows:
        ref = (ref or "").strip()
        n = to_float(qty)
        if not ref or n is None:
            continue
        agg[ref] = agg.get(ref, 0.0) + n
    return agg


def _fmt(n: float | None) -> str:
    return "" if n is None else format(n, "g")


@router.get("/{cid}/order-lines", response_model=list[OrderLineOut])
def order_lines(cid: int, db: Session = Depends(get_db),
                user: User = contents_readers):   # jak /items: bez agencji celnej
    """3-way per pozycja: zamówiono (OrderItem) vs przyjęto (GoodsReceiptLine) vs
    zafakturowano (InvoiceItem po ref). Zafakturowano liczone per ref — gdy ten sam ref
    jest na kilku pozycjach, pokazujemy tę samą sumę przy każdej (świadome uproszczenie).
    Przyjęcia spoza zamówienia doklejone na końcu jako „over"."""
    container = get_scoped(db, Container, cid, user)
    numbers = container_order_numbers(container)
    items = db.scalars(select(OrderItem).where(
        OrderItem.company_id == container.company_id,
        OrderItem.order_number.in_(numbers))).all() if numbers else []
    receipts = {(r.order_number, r.position): r for r in db.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.container_id == container.id)).all()}
    invoiced = _invoiced_by_ref(db, container.id)
    out: list[OrderLineOut] = []
    seen = set()
    for it in items:
        seen.add((it.order_number, it.position))
        rec = receipts.get((it.order_number, it.position))
        recv = rec.qty_received if rec else ""
        inv = _fmt(invoiced.get((it.material or "").strip())) if it.material else ""
        # DB-008: porównanie na liczbach z typowanych kolumn (tekst tylko do wyświetlenia)
        ordered = quantity_value(it.quantity_num, it.quantity)
        received = quantity_value(rec.qty_received_num, rec.qty_received) if rec else None
        out.append(OrderLineOut(
            order_number=it.order_number, position=it.position, material=it.material,
            description=it.description, ordered_qty=it.quantity, received_qty=recv,
            invoiced_qty=inv, receipt_id=rec.id if rec else None,
            status=_status(ordered, received), status_invoice=_status(ordered, inv)))
    for (onum, pos), rec in receipts.items():
        if (onum, pos) in seen:
            continue
        inv = _fmt(invoiced.get((rec.material or "").strip())) if rec.material else ""
        out.append(OrderLineOut(
            order_number=onum, position=pos, material=rec.material, description="",
            ordered_qty="", received_qty=rec.qty_received, invoiced_qty=inv,
            receipt_id=rec.id, status="over", status_invoice="unknown"))
    return out


@router.get("/{cid}/receipts", response_model=list[ReceiptLineOut])
def list_receipts(cid: int, db: Session = Depends(get_db),
                  user: User = contents_readers):   # jak /items: numery PO bez agencji celnej
    container = get_scoped(db, Container, cid, user)
    return db.scalars(select(GoodsReceiptLine)
                      .where(GoodsReceiptLine.container_id == container.id)
                      .order_by(GoodsReceiptLine.order_number, GoodsReceiptLine.position)).all()


@router.put("/{cid}/receipts", response_model=ReceiptLineOut)
def upsert_receipt(cid: int, body: ReceiptLineIn,
                   db: Session = Depends(get_db), user: User = receiver):
    """Zapis przyjęcia dla pozycji (upsert po order_number+position w tym kontenerze)."""
    container = get_scoped(db, Container, cid, user)
    onum = body.order_number.strip()
    if not onum:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "order_number jest wymagany.")
    pos = body.position.strip()
    row = db.scalar(select(GoodsReceiptLine).where(
        GoodsReceiptLine.container_id == container.id,
        GoodsReceiptLine.order_number == onum, GoodsReceiptLine.position == pos))
    if row is None:
        row = GoodsReceiptLine(company_id=container.company_id, container_id=container.id,
                               order_number=onum, position=pos, created_by_id=user.id)
        db.add(row)
        db.flush()
        record(db, entity_type=GoodsReceiptLine.__tablename__, entity_id=row.id,
               field="created", old_value=None, new_value=f"{onum}/{pos}", user=user,
               note=f"kontener {container.container_no}")
    record_changes(db, row, {"material": body.material.strip(),
                             "qty_received": body.qty_received.strip(),
                             "received_at": body.received_at, "note": body.note or ""},
                   user, note=f"przyjęcie {onum}/{pos}")
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{cid}/receipts/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_receipt(cid: int, receipt_id: int,
                   db: Session = Depends(get_db), user: User = receiver):
    container = get_scoped(db, Container, cid, user)
    row = db.get(GoodsReceiptLine, receipt_id)
    if not row or row.container_id != container.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono przyjęcia.")
    record(db, entity_type=GoodsReceiptLine.__tablename__, entity_id=row.id, field="delete",
           old_value=f"{row.order_number}/{row.position}: {row.qty_received}", new_value=None,
           user=user, note=f"kontener {container.container_no}")
    db.delete(row)
    db.commit()

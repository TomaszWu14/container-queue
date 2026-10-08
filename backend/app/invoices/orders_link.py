"""Faktura → zamówienie SAP (EKKO) → dostawca. Faktury podają numer zamówienia w nagłówku
(FICTIVA: „Order no. : 4700600638”); zamówienie z EKKO niesie numer SAP dostawcy (LIFNR),
który łączymy z kartoteką po `Supplier.sap_code` (import LFA1)."""
import re

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from ..models import InvoiceJob, SapOrder, Supplier

# numery zamówień zakupu ACME: 45… (ZTD), 47… / 48… (import) — 10 cyfr, poza dłuższymi liczbami
_ORDER_NO = re.compile(r"(?<!\d)4[5-8]\d{8}(?!\d)")


def order_numbers(text: str) -> list[str]:
    return list(dict.fromkeys(_ORDER_NO.findall(text or "")))


def invoice_orders(db: Session, job: InvoiceJob, company_id: int | None) -> list[SapOrder]:
    """Zamówienia EKKO tej faktury: numer zamówienia z nagłówka („Order no.”) albo numer
    faktury zapisany w EKKO jako „Zamówienie dostawcy” (FICTIVA: 260101E0001 przy
    4700600638) — druga droga działa, gdy PDF nie podaje numeru zamówienia."""
    numbers = order_numbers(job.text_excerpt)
    invoice_no = (job.invoice_number or "").strip()
    conditions: list[ColumnElement[bool]] = [SapOrder.order_number.in_(numbers)] if numbers else []
    if len(invoice_no) >= 3:   # krótkie numery („1”, „A1”) trafiałyby w przypadkowe zamówienia
        conditions.append(SapOrder.supplier_order_no == invoice_no)
    if not conditions:
        return []
    query = select(SapOrder).where(or_(*conditions))
    if company_id is not None:
        query = query.where(SapOrder.company_id == company_id)
    return list(db.scalars(query))


def orders_to_link(db: Session, job: InvoiceJob, company_id: int | None) -> list[SapOrder]:
    """Zamówienia z faktury bez kontenera — podpowiedź „przypnij do kontenera paczki”.
    Nie przypinamy sami: zła faktura w złym kontenerze psułaby dane zamówień
    (spec 2026-10-01-bramka-dokument-dostawa)."""
    if not job.batch:
        return []
    return [o for o in invoice_orders(db, job, company_id) if o.container_id is None]


def supplier_check(db: Session, job: InvoiceJob, orders: list[SapOrder]) -> dict | None:
    """Dostawca z zamówienia (EKKO) ↔ dostawca faktury (paczka / kontener). None = brak danych."""
    codes = sorted({o.supplier_sap for o in orders if o.supplier_sap})
    if not codes:
        return None
    batch = job.batch
    supplier = (batch.supplier or batch.container.supplier) if batch else None
    names = {s.sap_code: s.name for s in db.scalars(select(Supplier).where(Supplier.sap_code.in_(codes)))}
    invoice_code = (supplier.sap_code or "") if supplier else ""
    return {"orders": [o.order_number for o in orders], "order_suppliers": [
                {"sap_code": c, "name": names.get(c, "")} for c in codes],
            "invoice_supplier": {"sap_code": invoice_code, "name": supplier.name if supplier else ""},
            # dostawca faktury bez kodu SAP = nie da się porównać (nie „niezgodny”)
            "ok": None if not invoice_code else invoice_code in codes}

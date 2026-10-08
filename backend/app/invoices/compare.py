"""Porównania dokument (OCR) ↔ system: packing lista vs pozycje zamówień (W5 #33)
i faktura vs zamówienie EKKO/pozycje (W5 #34).

Wyłącznie RAPORT — nic tu nie nadpisuje danych; decyzję podejmuje człowiek w UI.
Klucz dopasowania pozycji: znormalizowany numer materiału/REF (wielkość liter i
znaki niealfanumeryczne pominięte) — ta sama zgrubna reguła co przy szukaniu w master.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Container, InvoiceJob, OrderItem, PurchaseOrder
from ..order_numbers import container_order_numbers
from .numbers import normalize_number

# ile względnej różnicy ilości uznajemy za szum zaokrągleń dokumentu (nie rozjazd)
_QTY_EPS = Decimal("0.001")


def _key(ref: str) -> str:
    return "".join(ch for ch in (ref or "").upper() if ch.isalnum())


def _qty(raw) -> Decimal | None:
    return normalize_number(raw)


def compare_rows(doc_rows: list[dict], sys_rows: list[dict]) -> list[dict]:
    """Wiersze raportu rozjazdów. Wejście: [{'ref','qty'}] z dokumentu i z systemu
    (ilości jako tekst 1:1). Duplikaty REF sumujemy po każdej stronie."""
    def bucket(rows):
        acc: dict[str, dict] = {}
        for row in rows:
            key = _key(row.get("ref", ""))
            if not key:
                continue
            entry = acc.setdefault(key, {"ref": row.get("ref", ""), "qty": Decimal(0),
                                         "qty_known": True})
            qty = _qty(row.get("qty"))
            if qty is None:
                entry["qty_known"] = False
            else:
                entry["qty"] += qty
        return acc

    doc, sys = bucket(doc_rows), bucket(sys_rows)
    out = []
    for key in sorted(set(doc) | set(sys)):
        d, s = doc.get(key), sys.get(key)
        if d and not s:
            status = "missing_in_system"
        elif s and not d:
            status = "missing_in_document"
        elif not d["qty_known"] or not s["qty_known"]:
            status = "qty_unknown"
        elif abs(d["qty"] - s["qty"]) <= _QTY_EPS * max(d["qty"], s["qty"], Decimal(1)):
            status = "ok"
        else:
            status = "qty_diff"
        out.append({
            "ref": (d or s)["ref"],
            "doc_qty": str(d["qty"]) if d and d["qty_known"] else (None if not d else ""),
            "sys_qty": str(s["qty"]) if s and s["qty_known"] else (None if not s else ""),
            "status": status,
        })
    return out


def _order_items(db: Session, container: Container) -> list[OrderItem]:
    numbers = container_order_numbers(container)
    if not numbers:
        return []
    return db.scalars(select(OrderItem)
                      .where(OrderItem.company_id == container.company_id,
                             OrderItem.order_number.in_(numbers))).all()


def packing_list_report(db: Session, job: InvoiceJob, container: Container,
                        uploads) -> dict:
    """#33: pozycje packing listy (OCR) vs OrderItems kontenera. Sam raport."""
    from . import extractor
    doc = extractor.parse_pdf(str(uploads / job.stored_name))
    doc_rows = [{"ref": it.get("ref", ""), "qty": it.get("qty", "")} for it in doc.items]
    sys_items = _order_items(db, container)
    rows = compare_rows(doc_rows,
                        [{"ref": it.material, "qty": it.quantity} for it in sys_items])
    return {"job_id": job.id, "kind": "packing_list", "rows": rows,
            "doc_items": len(doc_rows), "sys_items": len(sys_items),
            "mismatches": sum(1 for r in rows if r["status"] not in ("ok", "qty_unknown"))}


def invoice_vs_order(db: Session, job: InvoiceJob, container: Container,
                     tolerance_pct: float) -> dict:
    """#34: kwoty i ilości faktury vs zamówienie (EKKO/PurchaseOrder + OrderItems).

    Suma kwot pozycji faktury vs suma `amount` zamówień zakupowych kontenera;
    rozjazd > tolerance_pct → exceeded. Ilości per REF vs pozycje zamówień."""
    active = [it for it in job.items if not it.skipped]
    inv_total = Decimal(0)
    total_known = bool(active)
    for it in active:
        amount = normalize_number(it.amount)
        if amount is None:
            total_known = False
        else:
            inv_total += amount
    numbers = container_order_numbers(container)
    pos = db.scalars(select(PurchaseOrder).where(
        (PurchaseOrder.container_id == container.id)
        | ((PurchaseOrder.company_id == container.company_id)
           & PurchaseOrder.order_no.in_(numbers or [""])))).all()
    po_total = sum((Decimal(str(p.amount)) for p in pos if p.amount is not None), Decimal(0))
    diff_pct = None
    if total_known and po_total:
        diff_pct = float(abs(inv_total - po_total) / po_total * 100)
    rows = compare_rows(
        [{"ref": it.master_ref or it.raw_ref, "qty": it.qty} for it in active],
        [{"ref": it.material, "qty": it.quantity} for it in _order_items(db, container)])
    exceeded = bool(diff_pct is not None and diff_pct > tolerance_pct) \
        or any(r["status"] == "qty_diff" for r in rows)
    return {"job_id": job.id, "kind": "invoice",
            "invoice_total": str(inv_total) if total_known else None,
            "po_total": str(po_total) if pos else None,
            "diff_pct": round(diff_pct, 2) if diff_pct is not None else None,
            "tolerance_pct": tolerance_pct, "exceeded": exceeded, "rows": rows,
            "mismatches": sum(1 for r in rows if r["status"] not in ("ok", "qty_unknown"))}

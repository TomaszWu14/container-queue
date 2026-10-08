"""Bramka zgodności dokumentu z dostawą (spec 2026-10-01-bramka-dokument-dostawa, PR 2a).

Dowodem jest treść dokumentu, nie nazwa pliku. Sygnały: numer kontenera, zamówienia SAP,
dostawca (LIFNR), materiały spoza kontenera — każdy ok / sprzeczny / nie da się sprawdzić
(None). Liczone przy odczycie, jak `checks.job_checks`: gdy spłyną dane SAP, wynik sam się
odświeża. Status: conflict (którykolwiek sprzeczny) → nie da się zatwierdzić ani wyeksportować;
uncertain (brak danych albo nadwyżka ilości) → zatwierdzenie wymaga powodu; ok."""
from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from ..models import Container, InvoiceBatch, InvoiceJob, OrderItem, SapOrder
from ..models.invoices import INVOICE_LIKE_KINDS
from ..order_numbers import container_order_numbers
from .checks import job_checks
from .orders_link import invoice_orders
from .suggestions import found_container_numbers

OK, UNCERTAIN, CONFLICT = "ok", "uncertain", "conflict"


def _signal(key: str, ok: bool | None, detail: str = "") -> dict:
    return {"key": key, "ok": ok, "detail": detail}


def _containers(db: Session, company_id: int | None, numbers=(), ids=()) -> list[Container]:
    query = select(Container).where(
        Container.container_no.in_(sorted(numbers)) if numbers else Container.id.in_(sorted(ids)))
    if company_id is not None:
        query = query.where(Container.company_id == company_id)
    return list(db.scalars(query))


def job_conformity(db: Session, job: InvoiceJob, company_id: int | None) -> dict:
    container = job.batch.container
    signals: list[dict] = []
    move_to: list[Container] = []
    also_in: list[Container] = []   # faktura na kilka kontenerów: pozostałe z jej treści (PR 3)

    found = set(found_container_numbers(job.text_excerpt))
    if job.container_no:
        found.add(job.container_no.upper())
    if not found:
        signals.append(_signal("container", None))
    elif container.container_no.upper() in found:
        signals.append(_signal("container", True, ", ".join(sorted(found))))
        if len(found) > 1:
            also_in = [c for c in _containers(db, company_id, numbers=found) if c.id != container.id]
    else:
        signals.append(_signal("container", False, ", ".join(sorted(found))))
        move_to += _containers(db, company_id, numbers=found)

    own = set(db.scalars(select(SapOrder.order_number).where(
        SapOrder.container_id == container.id))) | set(container_order_numbers(container))
    mentioned = invoice_orders(db, job, company_id)
    to_link = [o.order_number for o in mentioned if o.container_id is None]
    foreign = [o for o in mentioned if o.container_id not in (None, container.id)]
    numbers = ", ".join(o.order_number for o in mentioned)
    if not mentioned:
        signals.append(_signal("orders", None))
    elif any(o.order_number in own or o.container_id == container.id for o in mentioned):
        signals.append(_signal("orders", True, numbers))
    elif foreign and {o.container_id for o in foreign} <= {c.id for c in also_in}:
        # PO kontenerów wymienionych na tej samej fakturze — nie sprzeczność (decyzja 4)
        signals.append(_signal("orders", True, numbers))
    elif foreign:
        # reguła z compare: są numery PO, żaden nie jest tego kontenera → odrzuć
        signals.append(_signal("orders", False, numbers))
        move_to += _containers(db, company_id, ids={o.container_id for o in foreign})
    else:   # PO bez kontenera → podpowiedź „przypnij” (PR 1), nie sprzeczność
        signals.append(_signal("orders", None, numbers))

    overage = False
    if job.doc_kind in INVOICE_LIKE_KINDS:
        checks = job_checks(db, job, company_id)
        supplier = checks["supplier"]
        signals.append(_signal("supplier", None if supplier is None else supplier["ok"],
                               supplier["invoice_supplier"]["name"] if supplier else ""))
        # pozycje wobec sumy kontenerów z faktury (decyzja 4)
        shared = set(db.scalars(select(SapOrder.order_number).where(
            SapOrder.container_id.in_([c.id for c in also_in])))) if also_in else set()
        for other in also_in:
            shared |= set(container_order_numbers(other))
        signals.append(_materials(db, job, company_id, own | set(to_link) | shared))
        # nadwyżka ponad zamówienie = niepewna; mniej (dostawa częściowa) = OK
        overage = any(r["ci_order"] and not r["ci_order"]["ok"] and (r["ci_order"]["diff_pct"] or 0) > 0
                      for r in checks["refs"])

    oks = [s["ok"] for s in signals]
    status = CONFLICT if False in oks else UNCERTAIN if None in oks or overage else OK
    move = {c.id: c for c in move_to if c.id != container.id}
    return {"status": status, "signals": signals, "overage": overage, "to_link": to_link,
            "move_to": [{"id": c.id, "container_no": c.container_no} for c in move.values()],
            "also_in": [{"id": c.id, "container_no": c.container_no,
                         "has_copy": has_copy(db, job, c)} for c in also_in],
            "ack": (job.check_data or {}).get("conformity_ack")}


def has_copy(db: Session, job: InvoiceJob, target: Container) -> bool:
    """Ten sam dokument jest już w paczkach kontenera docelowego: numer faktury + typ, a bez
    numeru — te same strony tego samego oryginału (sha256, §4 pkt 18)."""
    same: list[ColumnElement[bool]]
    if (job.invoice_number or "").strip():
        same = [InvoiceJob.invoice_number == job.invoice_number, InvoiceJob.doc_kind == job.doc_kind]
    elif job.sha256:
        same = [InvoiceJob.sha256 == job.sha256, InvoiceJob.page_from == job.page_from,
                InvoiceJob.page_to == job.page_to]
    else:
        return False
    return db.scalar(select(InvoiceJob.id).join(InvoiceBatch).where(
        InvoiceBatch.container_id == target.id, InvoiceJob.id != job.id, *same).limit(1)) is not None


def _materials(db: Session, job: InvoiceJob, company_id: int | None, orders: set[str]) -> dict:
    """REF master pozycji faktury ↔ materiały zamówień kontenera. Pozycje bez dopasowania
    do master daty pomijamy (nie wiadomo, co to za materiał)."""
    refs = {i.master_ref.strip() for i in job.items if not i.skipped and i.master_ref}
    query = select(OrderItem.material).where(OrderItem.order_number.in_(sorted(orders)))
    if company_id is not None:
        query = query.where(OrderItem.company_id == company_id)
    known = {m.strip() for m in db.scalars(query) if m}
    if not refs or not known:
        return _signal("materials", None)
    outside = sorted(refs - known)
    return _signal("materials", not outside, ", ".join(outside))


_LABELS = {"container": "numer kontenera", "orders": "zamówienie SAP", "supplier": "dostawca",
           "materials": "materiał spoza kontenera"}


def conflict_message(result: dict) -> str:
    bad = [f"{_LABELS[s['key']]}: {s['detail']}" if s["detail"] else _LABELS[s["key"]]
           for s in result["signals"] if s["ok"] is False]
    where = ", ".join(c["container_no"] for c in result["move_to"])
    return ("Dokument nie pasuje do tego kontenera (" + "; ".join(bad) + ")"
            + (f" — pasuje do: {where}." if where else "."))


def confirm_gate(result: dict, reason: str | None) -> str:
    """Komunikat blokady zatwierdzenia albo "" (wolno). Niepewna wymaga powodu — raz
    podany zostaje w check_data aż do ponownej ekstrakcji."""
    if result["status"] == CONFLICT:
        return conflict_message(result)
    if result["status"] == UNCERTAIN and not result["ack"] and not (reason or "").strip():
        return ("Nie da się w pełni sprawdzić, czy dokument dotyczy tego kontenera — "
                "podaj powód zatwierdzenia.")
    return ""


def store_ack(job: InvoiceJob, reason: str, login: str, at: str) -> None:
    job.check_data = {**(job.check_data or {}),
                      "conformity_ack": {"reason": reason.strip()[:500], "by": login, "at": at}}

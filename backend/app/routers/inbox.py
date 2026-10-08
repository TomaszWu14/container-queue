"""#47 — inbox „Co dziś": jedno miejsce z zadaniami użytkownika przekrojowo przez moduły.
Łączy sygnały kontenerowe (silnik signals) z zadaniami decyzyjnymi cross-module
(faktury transportowe czekające na moją akceptację — #42). Liczone na żądanie, bez DB-state."""
from ..models import today_pl
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import Viewer as viewer
from ..deps import scope_company, scope_containers, scope_transport_orders
from ..models import (
    Container, FreightInvoice, Role, TransportOrder, TransportOrderStatus, User,
)
from ..notifications import demurrage_deadlines
from ..signals import compute_signals
from .containers import _LOAD
from .containers_common import mask_row
from .customer_orders import care_risk_map

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


_DONE = Container.FINISHED   # rozładowany — magazyn nie ma już zadania


def _task(kind: str, title: str, link: str, *, container: Container | None = None,
          due: str | None = None) -> dict:
    """Jednolita pozycja listy „Co dziś" (#26): co zrobić + gdzie kliknąć."""
    return {"kind": kind, "title": title, "link": link, "due": due,
            "container_id": container.id if container else None,
            "container_no": container.container_no if container else None}


def _warehouse_tasks(containers: list[Container], today) -> list[dict]:
    """Magazyn: rozładunki dziś/jutro + zaległe potwierdzenia rozładunku (awizacja minęła)."""
    tasks = []
    for c in sorted(containers, key=lambda c: c.notify_date or today):
        if c.status in _DONE or not c.notify_date:
            continue
        link = f"/kontenery/{c.id}"
        if c.notify_date < today:
            tasks.append(_task("unload_confirm", "Potwierdź rozładunek (awizacja minęła)", link,
                               container=c, due=c.notify_date.isoformat()))
        elif (c.notify_date - today).days <= 1:
            kind = "unload_today" if c.notify_date == today else "unload_tomorrow"
            tasks.append(_task(kind, "Rozładunek dziś" if kind == "unload_today" else "Rozładunek jutro",
                               link, container=c, due=c.notify_date.isoformat()))
    return tasks


@router.get("")
def inbox(db: Session = Depends(get_db), user: User = viewer,
          signals: bool = Query(default=True, description="false = pomiń sygnały (liczone też na Wieży)")) -> dict:
    today = today_pl()
    containers = db.scalars(scope_containers(
        select(Container).options(*_LOAD).where(
            Container.open_in_queue()), user)).all()
    tasks: list[dict] = []
    sig: list[dict] = []
    if user.role == Role.warehouse:
        # magazyn: bez sygnałów — niosą dane handlowe (dostawca), poza jego zakresem
        tasks += _warehouse_tasks(containers, today)
    elif signals:
        sig = [mask_row(s, user) for s in compute_signals(
            containers, demurrage_deadlines(db, containers), today,
            care=care_risk_map(db, containers, today, user))]
    if user.role == Role.forwarder and user.forwarder_id:
        orders = db.scalars(scope_transport_orders(select(TransportOrder).where(
            TransportOrder.status == TransportOrderStatus.WYSTAWIONE), user)
            .order_by(TransportOrder.pickup_date)).all()
        tasks += [_task("order_respond", "Zlecenie transportowe czeka na odpowiedź", "/spedycja",
                        container=o.container, due=o.pickup_date.isoformat() if o.pickup_date else None)
                  for o in orders]

    # zadania decyzyjne: faktury transportowe do zatwierdzenia (widzi je zatwierdzajacy = admin)
    approvals: list[dict] = []
    if user.role == Role.admin:
        fq = select(FreightInvoice).where(FreightInvoice.status == "DO_AKCEPTACJI")
        fq = scope_company(fq, FreightInvoice.company_id, user)
        approvals = [{
            "id": i.id, "bl_number": i.bl_number, "invoice_number": i.invoice_number,
            "amount": float(i.amount) if i.amount is not None else None, "currency": i.currency,
        } for i in db.scalars(fq.order_by(FreightInvoice.created_at.desc())).all()]

    tasks += [_task("freight_approval", f"Zaakceptuj fakturę transportową BL {a['bl_number'] or '—'}",
                    "/spedycja") for a in approvals]
    return {
        "tasks": tasks,
        "signals_count": len(sig),
        "signals_top": sig[:10],
        "freight_approvals": approvals,
        "freight_approvals_count": len(approvals),
    }

"""Wyliczenia konsolidacji kontenera z przypisanych zamowien (reguly potwierdzone
2026-09-22): fill_cbm = suma CBM niezablokowanych; CRD = max CRD niezablokowanych;
kontener zamkniety nie przyjmuje nowych zamowien."""
import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import CartStatus, ConsolidationStatus, Container, PurchaseOrder


def unblocked_cond():
    """Warunek \"zamowienie liczy sie do fill/CRD\" — wspolny dla wersji per kontener i batch."""
    return PurchaseOrder.cart_status != CartStatus.zablokowane.value


def _unblocked(container_id: int):
    return (PurchaseOrder.container_id == container_id, unblocked_cond())


def container_fill_cbm(db: Session, container_id: int) -> float:
    total = db.scalar(select(func.coalesce(func.sum(PurchaseOrder.cbm), 0))
                      .where(*_unblocked(container_id)))
    return float(total or 0)


def container_crd(db: Session, container_id: int) -> datetime.date | None:
    return db.scalar(select(func.max(PurchaseOrder.crd)).where(*_unblocked(container_id)))


def can_add_order(container: Container) -> bool:
    return container.consolidation_status != ConsolidationStatus.zamkniety.value


CRD_ESCALATION_DAYS = 10   # prog eskalacji (dni); konfigurowalny przez Admina w przyszlosci


def _consolidation_key(po) -> tuple:
    """Auto-reguła (#17): łączymy tylko zamowienia zgodne co do DOSTAWCY i TRASY (port
    zaladunku + rozladunku) — inaczej nie jada jednym kontenerem. Pola trasy sa
    opcjonalne (tekst na PurchaseOrder); puste → None, wiec grupuja sie spojnie
    (a testowe atrapy bez tych pol dzialaja jak dawne grupowanie mono-dostawca)."""
    return (po.supplier,
            (getattr(po, "port_of_departure", None) or None),
            (getattr(po, "port_of_discharge", None) or None))


def propose_consolidation(orders: list, capacity: float = 70.0) -> list[dict]:
    """Propozycje konsolidacji (tylko odczyt): grupuj po dostawcy I trasie (porty),
    w grupie sortuj malejaco po cbm i pakuj first-fit-decreasing do binow <= capacity.
    Najpelniejsze biny na gorze. Miks dostawcow/tras w jednym kontenerze poza zakresem."""
    groups: dict[tuple, list] = {}
    for po in orders:
        groups.setdefault(_consolidation_key(po), []).append(po)

    proposals = []
    for (supplier, pod, podis), group in groups.items():
        bins: list[dict] = []  # {"orders": [...], "total_cbm": float}
        for po in sorted(group, key=lambda p: float(p.cbm or 0), reverse=True):
            cbm = float(po.cbm or 0)
            target = next((b for b in bins if b["total_cbm"] + cbm <= capacity), None)
            if target is None:
                target = {"orders": [], "total_cbm": 0.0}
                bins.append(target)
            target["orders"].append(po.id)
            target["total_cbm"] += cbm
        route = " → ".join(x for x in (pod, podis) if x)
        for b in bins:
            proposals.append({
                "supplier": supplier, "orders": b["orders"], "total_cbm": b["total_cbm"],
                "port_of_departure": pod, "port_of_discharge": podis,
                "fill_pct": round(b["total_cbm"] / capacity * 100) if capacity else None,
                # czytelne uzasadnienie propozycji dla operatora (dostawca · trasa)
                "reason": supplier + (f" · {route}" if route else ""),
            })
    # najpelniejsze biny najpierw — najbardziej „gotowe" propozycje na gorze listy
    proposals.sort(key=lambda p: p["total_cbm"], reverse=True)
    return proposals


def crd_deviation_days(po) -> int | None:
    """Odchylenie aktualnego CRD od zakladanego (crd_target), w dniach. None gdy
    brak ktorejkolwiek daty. Dodatnie = poslizg (CRD pozniej niz zakladano)."""
    if po.crd is None or po.crd_target is None:
        return None
    return (po.crd - po.crd_target).days

"""Front-half (tylko odczyt): zamowienia przypisane do kontenera wraz z wyliczeniami
konsolidacji. Filtrowanie koszyka po cart_status zylo do istniejacego
GET /api/purchase-orders (parametr cart_status). Mutacje (dodaj/usun/zwolnij)
w kolejnym plastrze."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..audit import record_changes
from ..consolidation import (can_add_order, container_crd, container_fill_cbm,
                             crd_deviation_days, unblocked_cond, propose_consolidation, CRD_ESCALATION_DAYS)
from ..database import get_db
from ..deps import get_company_scoped, get_scoped, scope_company, scope_containers
from ..deps import Editors as _editors
from ..deps import PurchasingReaders as _releasers
from ..models import CartStatus, ConsolidationStatus, Container, PurchaseOrder, User
from ..notifications import notify, purchasing_users

router = APIRouter(prefix="/api", tags=["consolidation"])



def _scoped_po(db: Session, po_id: int, user: User) -> PurchaseOrder:
    return get_company_scoped(db, PurchaseOrder, po_id, user)


def _po_dict(po: PurchaseOrder) -> dict:
    return {"id": po.id, "order_no": po.order_no, "supplier": po.supplier,
            "cbm": float(po.cbm) if po.cbm is not None else None,
            "crd": po.crd, "crd_target": po.crd_target,
            "deviation_days": crd_deviation_days(po),
            "cart_status": po.cart_status, "container_id": po.container_id}


@router.get("/consolidation/proposals")
def consolidation_proposals(db: Session = Depends(get_db),
                            user: User = _releasers) -> list[dict]:
    """Tylko odczyt: propozycje pogrupowania koszyka (gotowe do konsolidacji zamowienia
    bez kontenera) w kontenery <= capacity, per dostawca. Zatwierdzenie idzie
    istniejacym PUT /containers/{cid}/orders/{poId}."""
    q = select(PurchaseOrder).where(
        PurchaseOrder.container_id.is_(None),
        PurchaseOrder.cart_status.in_([CartStatus.w_koszyku.value, CartStatus.zwolnione.value]))
    q = scope_company(q, PurchaseOrder.company_id, user)
    orders = db.scalars(q).all()
    by_id = {po.id: po for po in orders}
    proposals = propose_consolidation(orders)
    for p in proposals:
        p["order_names"] = [by_id[oid].order_no for oid in p["orders"]]
    return proposals


@router.get("/consolidation/containers")
def list_consolidation_containers(status: str = "otwarty",
                                  db: Session = Depends(get_db),
                                  user: User = _releasers) -> list[dict]:
    q = scope_containers(select(Container).where(Container.consolidation_status == status), user)
    containers = db.scalars(q.order_by(Container.container_no)).all()
    # jedno zgrupowane zapytanie zamiast 3 per kontener; fill/crd tylko z niezablokowanych
    # (ta sama reguła co container_fill_cbm/container_crd — unblocked_cond)
    ok = unblocked_cond()
    stats = {row[0]: row[1:] for row in db.execute(
        select(PurchaseOrder.container_id, func.count(PurchaseOrder.id),
               func.sum(case((ok, PurchaseOrder.cbm))),
               func.max(case((ok, PurchaseOrder.crd))))
        .where(PurchaseOrder.container_id.in_([c.id for c in containers]))
        .group_by(PurchaseOrder.container_id))} if containers else {}
    out = []
    for c in containers:
        n, fill, crd = stats.get(c.id, (0, None, None))
        out.append({"id": c.id, "container_no": c.container_no,
                    "consolidation_status": c.consolidation_status,
                    "capacity_cbm": float(c.capacity_cbm),
                    "fill_cbm": float(fill or 0), "crd": crd, "order_count": int(n or 0)})
    return out


@router.get("/containers/{container_id}/orders")
def container_orders(container_id: int, db: Session = Depends(get_db),
                     user: User = _releasers) -> dict:
    cont = get_scoped(db, Container, container_id, user)
    orders = db.scalars(select(PurchaseOrder)
                        .where(PurchaseOrder.container_id == container_id)
                        .order_by(PurchaseOrder.order_no)).all()
    return {"orders": [_po_dict(p) for p in orders],
            "fill_cbm": container_fill_cbm(db, container_id),
            "crd": container_crd(db, container_id),
            "capacity_cbm": float(cont.capacity_cbm),
            "consolidation_status": cont.consolidation_status}


@router.put("/containers/{cid}/orders/{po_id}")
def assign_order(cid: int, po_id: int, db: Session = Depends(get_db), user: User = _editors) -> dict:
    cont = get_scoped(db, Container, cid, user)
    po = _scoped_po(db, po_id, user)
    if not can_add_order(cont):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kontener zamknięty — nie można dodać zamówienia.")
    if po.company_id != cont.company_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Zamówienie i kontener należą do różnych spółek.")
    record_changes(db, po, {"container_id": cid, "cart_status": CartStatus.przypisane.value},
                   user, note="przypisano do kontenera")
    db.commit(); db.refresh(po)
    return _po_dict(po)


@router.delete("/containers/{cid}/orders/{po_id}")
def remove_order(cid: int, po_id: int, db: Session = Depends(get_db), user: User = _editors) -> dict:
    po = _scoped_po(db, po_id, user)
    if po.container_id != cid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zamówienia nie ma w tym kontenerze.")
    record_changes(db, po, {"container_id": None, "cart_status": CartStatus.w_koszyku.value},
                   user, note="odpięto z kontenera")
    db.commit(); db.refresh(po)
    return _po_dict(po)


@router.post("/purchase-orders/{po_id}/release")
def release_order(po_id: int, db: Session = Depends(get_db), user: User = _releasers) -> dict:
    po = _scoped_po(db, po_id, user)
    record_changes(db, po, {"cart_status": CartStatus.zwolnione.value}, user, note="zwolnienie do odbioru")
    db.commit(); db.refresh(po)
    return _po_dict(po)


@router.post("/purchase-orders/{po_id}/block")
def block_order(po_id: int, db: Session = Depends(get_db), user: User = _editors) -> dict:
    po = _scoped_po(db, po_id, user)
    record_changes(db, po, {"cart_status": CartStatus.zablokowane.value}, user, note="blokada zamówienia")
    db.commit(); db.refresh(po)
    return _po_dict(po)


@router.post("/purchase-orders/{po_id}/unblock")
def unblock_order(po_id: int, db: Session = Depends(get_db), user: User = _editors) -> dict:
    po = _scoped_po(db, po_id, user)
    record_changes(db, po, {"cart_status": CartStatus.w_koszyku.value}, user, note="odblokowano zamówienie")
    db.commit(); db.refresh(po)
    return _po_dict(po)


class CrdIn(BaseModel):
    crd: datetime.date | None = None
    crd_target: datetime.date | None = None


@router.patch("/purchase-orders/{po_id}/crd")
def update_crd(po_id: int, body: CrdIn, db: Session = Depends(get_db),
               user: User = _releasers) -> dict:
    po = _scoped_po(db, po_id, user)
    was_blocked = po.cart_status == CartStatus.zablokowane.value
    changes = {"crd": body.crd, "crd_target": body.crd_target}
    dev = crd_deviation_days(body)
    if dev is not None:
        if dev >= CRD_ESCALATION_DAYS:
            # blokada ma priorytet nad przypisaniem; container_id jest zachowany
            # (zamowienie wypada z konsolidacji, ale zostaje w kontenerze) — ZAL-2
            changes["cart_status"] = CartStatus.zablokowane.value
        elif po.cart_status == CartStatus.zablokowane.value:
            # nowy target sprowadzil odchylenie ponizej progu -> odblokuj,
            # przywracajac status sprzed blokady (przypisane vs w koszyku)
            changes["cart_status"] = (CartStatus.przypisane.value if po.container_id is not None
                                       else CartStatus.w_koszyku.value)
    record_changes(db, po, changes, user,
                   note=f"aktualizacja CRD (odchylenie {dev if dev is not None else '—'} dni)")
    newly_blocked = changes.get("cart_status") == CartStatus.zablokowane.value and not was_blocked
    if newly_blocked:
        notify(db, purchasing_users(db, po.company_id), kind="crd_escalation",
               title=f"Eskalacja CRD: zamówienie {po.order_no}",
               body=f"Odchylenie {dev} dni ≥ progu {CRD_ESCALATION_DAYS} — zamówienie zablokowane, wymaga decyzji Kupca.")
    db.commit(); db.refresh(po)
    return {"id": po.id, "crd": po.crd, "crd_target": po.crd_target,
            "deviation_days": dev, "cart_status": po.cart_status}


@router.post("/containers/{cid}/close-consolidation")
def close_consolidation(cid: int, db: Session = Depends(get_db), user: User = _editors) -> dict:
    cont = get_scoped(db, Container, cid, user)
    record_changes(db, cont, {"consolidation_status": ConsolidationStatus.zamkniety.value},
                   user, note="zamknięto konsolidację")
    db.commit()
    return {"id": cont.id, "consolidation_status": cont.consolidation_status}

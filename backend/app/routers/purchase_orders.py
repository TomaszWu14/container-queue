"""Zamówienia zakupowe (ETD) — lista dla kolejki jako wczesny etap przed kontenerem."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..deps import AdminOnly as admins
from ..deps import PurchasingReaders as po_readers
from ..deps import get_company_by_code, get_company_scoped, scope_company
from ..models import PurchaseOrder, User, pl_midnight_utc
from ..schemas import PurchaseOrderOut

router = APIRouter(prefix="/api/purchase-orders", tags=["purchase-orders"])


@router.get("", response_model=list[PurchaseOrderOut])
def list_purchase_orders(
    company_code: str | None = Query(default=None),
    unlinked: bool = Query(default=True),
    q: str | None = Query(default=None, max_length=160),
    created_from: datetime.date | None = Query(default=None),
    created_to: datetime.date | None = Query(default=None),
    cart_status: str | None = Query(default=None),
    # bez limitu przeglądarka master data ciągnęła cały import EKKO (tysiące wierszy);
    # domyślnie dużo (kolejka/koszyk liczą na pełną listę spółki), X-Total-Count = ile jest
    limit: int = Query(default=2000, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
    *,
    response: Response,
    db: Session = Depends(get_db),
    user: User = po_readers,
):
    """Zamówienia zakupowe. Domyślnie tylko NIEPOWIĄZANE z kontenerem
    (unlinked=true) — wczesny etap kolejki; powiązane reprezentuje ich kontener.
    Bez company_code (przeglądarka master data): zakres wg separacji spółek usera,
    z opcjonalną wyszukiwarką (numer/dostawca) i zakresem dat utworzenia.
    Sortowanie: ETD rosnąco (bez ETD na końcu), potem numer zamówienia."""
    query = select(PurchaseOrder)
    if company_code is not None:
        company = get_company_by_code(db, user, company_code)
        query = query.where(PurchaseOrder.company_id == company.id)
    else:
        query = scope_company(query, PurchaseOrder.company_id, user)
    if unlinked:
        query = query.where(PurchaseOrder.container_id.is_(None))
    if cart_status:
        query = query.where(PurchaseOrder.cart_status == cart_status)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(PurchaseOrder.order_no.ilike(pattern)
                            | PurchaseOrder.supplier.ilike(pattern))
    if created_from is not None:
        query = query.where(PurchaseOrder.created_at >= pl_midnight_utc(created_from))
    if created_to is not None:
        query = query.where(PurchaseOrder.created_at
                            < pl_midnight_utc(created_to + datetime.timedelta(days=1)))
    # ETD rosnąco, bez ETD na końcu, potem numer — w SQL, żeby limit/offset ciął po sortowaniu
    rows = db.scalars(query.order_by(PurchaseOrder.etd.is_(None), PurchaseOrder.etd,
                                     PurchaseOrder.order_no, PurchaseOrder.id)
                      .limit(limit).offset(offset)).all()
    total = offset + len(rows)
    if len(rows) == limit or offset:
        total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.delete("/{po_id}", status_code=204)
def delete_purchase_order(po_id: int, db: Session = Depends(get_db), user: User = admins):
    """Usunięcie zamówienia zakupowego (tylko admin, w granicach spółek usera).

    Zamówienie powiązane z kontenerem reprezentuje realny transport — 409 zamiast
    kaskady; najpierw trzeba odpiąć/skasować kontener."""
    po = get_company_scoped(db, PurchaseOrder, po_id, user)
    if po.container_id is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Nie można usunąć: zamówienie powiązane z kontenerem #{po.container_id}.")
    audit.record(db, entity_type="purchase_orders", entity_id=po.id, field="delete",
                 old_value=f"{po.order_no} ({po.supplier or 'bez dostawcy'})",
                 new_value=None, user=user, note="usunięto zamówienie zakupowe")
    db.delete(po)
    db.commit()

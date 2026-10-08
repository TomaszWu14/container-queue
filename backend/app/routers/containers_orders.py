"""Zamówienia (PO) i zakładanie zleceń — N rekordów kontenerów z jednego zlecenia."""
from ..models import today_pl
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..audit import record, record_created
from ..database import get_db
from ..deps import Editors as editors
from ..deps import PurchasingReaders as order_readers
from ..deps import (
    check_container_access,
    get_scoped,
    is_material_company,
    resolve_company_id,
    scope_company,
    supplier_clause_for_company,
)
from ..models import (
    Company,
    Container,
    ContainerStatus,
    ContainerType,
    Order,
    Port,
    Supplier,
    SupplierContact,
    TransportType,
    User,
)
from ..notifications import new_order_watchers, notify
from ..schemas import FoundOrderIn, OrderDetailOut, OrderIn, OrderOut, OrderProgress
from .containers_common import (
    _LOAD,
    _check_company_fks,
    _transport_prefix,
    reserve_transport_seqs,
    to_out,
)

# sub-router bez prefiksu — podpinany w routers/containers.py (prefiks /api, tag kolejka)
router = APIRouter()


# --- zamówienia (PO) ---

_DELIVERED = (ContainerStatus.DOSTARCZONY, ContainerStatus.ZREALIZOWANY)
# główny tryb zlecenia → główny transport kontenera (kontener dziedziczy go z zamówienia)
_MODE_TRANSPORT = {"SEA": TransportType.morski, "AIR": TransportType.lotniczy, "RAIL": TransportType.kolej}
_TRANSIT = (ContainerStatus.ZAPOWIEDZIANY, ContainerStatus.W_PRODUKCJI,
            ContainerStatus.TRANSPORT_WSTEPNY, ContainerStatus.W_TRANSPORCIE)

def compute_progress(containers: list[Container]) -> OrderProgress:
    """Podsumowanie postępu realizacji zamówienia na podstawie statusów kontenerów."""
    total = len(containers)
    delivered = sum(1 for c in containers if c.status in _DELIVERED)
    in_transit = sum(1 for c in containers if c.status in _TRANSIT)
    delayed = sum(1 for c in containers if c.is_delayed)
    at_port = total - delivered - in_transit
    if total == 0:
        derived = "PUSTE"
    elif delivered == total:
        derived = "ZAKONCZONE"
    elif delivered == 0 and at_port == 0:
        derived = "NOWE"
    else:
        derived = "W_TOKU"
    return OrderProgress(
        total=total, delivered=delivered, at_port_or_customs=at_port,
        in_transit=in_transit, delayed=delayed,
        percent=round(delivered * 100 / total) if total else 0,
        derived_status=derived)


def order_to_out(order: Order, user: User, detail: bool = False) -> OrderOut:
    schema = OrderDetailOut if detail else OrderOut
    out = schema.model_validate(order)
    # tylko kontenery w zakresie usera (logistyk z ograniczeniem magazynów: swoje) — liczba,
    # postęp i lista z tego samego zbioru, żeby nie zdradzać stanu niewidocznych dostaw
    visible = [c for c in order.containers if _may_see(user, c)]
    out.company_name = order.company.name if order.company else None
    out.supplier_name = order.supplier.name if order.supplier else None
    out.planned_container_count = order.container_count   # zaplanowane przy zakładaniu
    out.container_count = len(visible)                     # faktyczne rekordy w kolejce
    out.departure_port_name = order.departure_port.name if order.departure_port else None
    out.container_type_name = order.container_type.name if order.container_type else None
    out.supplier_contact_name = (order.supplier_contact.full_name
                                 if order.supplier_contact else None)
    out.created_by_login = order.created_by.login if order.created_by else None
    out.progress = compute_progress(visible)
    if detail:
        # maskowane wg roli
        out.containers = [to_out(c, user) for c in sorted(
            visible, key=lambda c: (c.notify_date or datetime.date.max, c.id))]
    return out


def _may_see(user: User, c: Container) -> bool:
    try:
        check_container_access(user, c)
    except HTTPException:
        return False
    return True


_ORDER_LOAD = (
    selectinload(Order.company), selectinload(Order.supplier),
    selectinload(Order.containers), selectinload(Order.departure_port),
    selectinload(Order.container_type), selectinload(Order.supplier_contact),
    selectinload(Order.created_by),
)

# widok szczegółowy: te same relacje co _ORDER_LOAD, ale kontenery z pełnym eager-loadem
_ORDER_DETAIL_LOAD = (
    selectinload(Order.company), selectinload(Order.supplier),
    selectinload(Order.departure_port), selectinload(Order.container_type),
    selectinload(Order.supplier_contact), selectinload(Order.created_by),
    selectinload(Order.containers).options(*_LOAD),
)


@router.get("/orders", response_model=list[OrderOut])
def list_orders(response: Response, db: Session = Depends(get_db), user: User = order_readers,
                q: str | None = None, limit: int = Query(default=500, ge=1, le=2000)):
    query = select(Order).options(*_ORDER_LOAD).order_by(Order.number.desc())
    query = scope_company(query, Order.company_id, user)
    if q:
        query = query.where(Order.number.ilike(f"%{q}%"))
    # bez limitu lista miała 4,3 MB (audyt PERF-003); resztę znajduje wyszukiwanie po numerze
    rows = db.scalars(query.limit(limit)).all()
    total = len(rows)
    if total == limit:
        total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    response.headers["X-Total-Count"] = str(total)
    return [order_to_out(order, user) for order in rows]


@router.get("/orders/{order_id}", response_model=OrderDetailOut)
def get_order(order_id: int, db: Session = Depends(get_db), user: User = order_readers):
    order = get_scoped(db, Order, order_id, user, options=_ORDER_DETAIL_LOAD)
    return order_to_out(order, user, detail=True)


@router.post("/orders", response_model=OrderOut, status_code=201)
def create_order(body: OrderIn, db: Session = Depends(get_db), user: User = editors):
    company_id = resolve_company_id(db, user, body.company_id)
    if db.scalar(select(Order).where(Order.company_id == company_id, Order.number == body.number)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Zamówienie o tym numerze już istnieje.")
    _check_company_fks(db, company_id, body.supplier_id, None, None)
    order = Order(number=body.number, company_id=company_id,
                  supplier_id=body.supplier_id, notes=body.notes)
    db.add(order)
    try:
        record_created(db, order, user, label=order.number)   # flush → wyścig złapany niżej
        db.commit()
    except IntegrityError:   # wyścig: równoległe utworzenie tego samego numeru
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Zamówienie o tym numerze już istnieje.") from None
    # pełny re-SELECT z relacjami poniżej odświeża rekord — osobny db.refresh() zbędny
    return order_to_out(db.scalar(select(Order).options(*_ORDER_LOAD)
                                  .where(Order.id == order.id)), user)


def _resolve_supplier(db: Session, company_id: int, supplier_id: int | None,
                      supplier_name: str | None) -> int | None:
    """Dostawca po id (musi być do użycia w spółce) albo po nazwie (get-or-create): spółka
    z materiałami Acme → kartoteka, spółka-klient → jej nadawca."""
    if supplier_id is not None:
        _check_company_fks(db, company_id, supplier_id, None, None)
        return supplier_id
    name = (supplier_name or "").strip()
    if not name:
        return None
    company = db.get(Company, company_id)
    supplier = db.scalar(select(Supplier).where(
        supplier_clause_for_company(company), Supplier.name == name)
        .order_by(Supplier.id).limit(1))
    if supplier is None:
        supplier = Supplier(name=name, client_company_id=(
            None if is_material_company(company) else company.id))
        db.add(supplier)
        db.flush()
    return supplier.id


@router.post("/zlecenia", response_model=OrderDetailOut, status_code=201)
def found_order(body: FoundOrderIn, db: Session = Depends(get_db), user: User = editors):
    """Zakłada zlecenie (Borealis/Cobalt): jedno zamówienie → N rekordów kontenerów w kolejce.

    Kontenery powstają bez numeru (dojdą później); dziedziczą dostawcę, port wypłynięcia,
    typ (rozmiar) kontenera i tryb transportu ze zlecenia. Zespół dostaje powiadomienie.
    """
    # spółka: z company_id, a gdy brak (np. admin, którego lista spółek jeszcze się nie
    # załadowała po stronie klienta) — z kodu zakładki, żeby nie trafić w spółkę domyślną
    requested_company_id = body.company_id
    if requested_company_id is None and body.company_code:
        company = db.scalar(select(Company).where(Company.code == body.company_code))
        if company:
            requested_company_id = company.id
    company_id = resolve_company_id(db, user, requested_company_id)

    supplier_id = _resolve_supplier(db, company_id, body.supplier_id, body.supplier_name)

    contact = db.get(SupplierContact, body.supplier_contact_id) if body.supplier_contact_id else None
    if body.supplier_contact_id and (not contact or contact.supplier_id != supplier_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Kontakt nie należy do wskazanego dostawcy.")
    ctype = db.get(ContainerType, body.container_type_id) if body.container_type_id else None
    if body.container_type_id and not ctype:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono typu kontenera.")
    if body.departure_port_id and not db.get(Port, body.departure_port_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono portu.")

    order = Order(
        number=body.number, company_id=company_id, supplier_id=supplier_id, notes=body.notes,
        supplier_contact_id=body.supplier_contact_id, departure_port_id=body.departure_port_id,
        container_type_id=body.container_type_id, main_mode=body.main_mode,
        sea_service=body.sea_service, container_count=body.container_count,
        goods_type=body.goods_type, is_adr=body.is_adr,
        goods_classification=body.goods_classification, goods_value=body.goods_value,
        goods_currency=body.goods_currency, goods_weight=body.goods_weight,
        readiness_date=body.readiness_date, created_by_id=user.id)
    db.add(order)
    try:
        db.flush()   # unikalność (company_id, number) — łapiemy też wyścig po sprawdzeniu wyżej
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Zamówienie o tym numerze już istnieje.") from None

    company = db.get(Company, company_id)
    size = ctype.name if ctype else ""
    transport_type = _MODE_TRANSPORT.get(getattr(body.main_mode, "value", None))
    year = (body.readiness_date or today_pl()).year
    # jeden blok numerów z licznika w bazie (DB-011) — nie max+1 w pętli ani w Pythonie
    prefix = _transport_prefix(company, year)
    first = reserve_transport_seqs(db, prefix, body.container_count)
    created = []
    for i in range(body.container_count):
        container = Container(
            container_no="", company_id=company_id, order_id=order.id,
            supplier_id=supplier_id, port_id=body.departure_port_id,
            container_size=size, transport_type=transport_type,
            transport_id=f"{prefix}{first + i:04d}",
            status=ContainerStatus.ZAPOWIEDZIANY)
        db.add(container)
        created.append(container)
    db.flush()   # jeden flush nadaje wszystkie PK
    for container in created:
        record(db, entity_type="containers", entity_id=container.id, field="status",
               old_value=None, new_value=container.status.value, user=user,
               note=f"zlecenie {order.number}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Konflikt numeracji transportu — spróbuj ponownie.") from None

    # powiadomienie o nowym zleceniu: team spółki zakładającej + team Acme (mail + dzwoneczek)
    notify(db, new_order_watchers(db, company_id), kind="order",
           title=f"Nowe zlecenie {order.number} ({company.name}) — {body.container_count} kont.",
           body=(f"Spółka: {company.name} · "
                 f"Dostawca: {order.supplier.name if order.supplier else '—'} · "
                 f"Zlecający: {user.full_name or user.login}"))
    db.commit()
    return order_to_out(db.scalar(select(Order).options(*_ORDER_DETAIL_LOAD)
                                  .where(Order.id == order.id)), user, detail=True)

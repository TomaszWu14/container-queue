"""Kolejka kontenerów: lista, karta kontenera, historia, eksport + spięcie sub-routerów.

Endpointy podzielone na moduły containers_* (zamówienia, zapis, planowanie, zawartość,
usuwanie, dziennik zmian, statystyki), wspólne helpery w containers_common. Tu zostaje
odczyt kontenera i jeden `router` pod /api, podpinany w main.py jak dotąd. Helpery są
re-eksportowane, więc dotychczasowe `from .containers import ...` działają bez zmian.
"""
from ..models import today_pl
import datetime
import logging

import httpx
from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..deps import Editors as editors
from ..deps import Viewer as viewer
from ..deps import ViewerOrSales as viewer_or_sales
from ..deps import apply_company_code_filter, get_scoped, own_company_id, scope_containers
from ..notification_alerts import demurrage_deadlines
from ..models import (
    AuditLog,
    Company,
    Container,
    ContainerStatus,
    CustomsStatus,
    DocumentStatus,
    Order,
    TransportJob,
    TransportJobContainer,
    TransportJobStatus,
    TransportType,
    User,
    Warehouse,
)
from ..audit import record_changes
from ..schemas import AuditOut, ContainerOut
from ..security import can_view_all
from . import (
    containers_bulk,
    containers_changes,
    containers_contents,
    containers_orders,
    containers_planning,
    containers_purge,
    containers_stats,
    containers_write,
)

# re-eksport helperów — importowane przez inne routery, invoices/compare, main.py i testy
from .containers_common import (  # noqa: F401
    _CUSTOMS_HIDDEN,
    _LOAD,
    _TRACKABLE_STATUSES,
    _WAREHOUSE_HIDDEN,
    _attach_status_ages,
    _check_company_fks,
    _enum_filter,
    _fk_filter,
    _max_transport_seq,
    _notify_new_delivery,
    _resolve_order,
    _transport_prefix,
    calendar_overrides_map,
    daily_limits_map,
    day_limit,
    fk_matches,
    get_container_checked,
    hidden_fields,
    next_transport_id,
    searchable,
    to_out,
    transport_job_conflicts,
)
from .containers_contents import (  # noqa: F401
    _PACKING_CACHE,
    _PACKING_TTL,
    _packing_result,
    container_order_numbers,
)
from .containers_orders import compute_progress, order_to_out  # noqa: F401
from .containers_purge import _purge_containers  # noqa: F401
from .customer_orders import customer_order_map

router = APIRouter(prefix="/api", tags=["kolejka"])
logger = logging.getLogger(__name__)

# Kolejność ma znaczenie: sub-routery podpinamy PRZED trasami tego pliku, bo stałe ścieżki
# GET (/containers/fill-summary, /containers/transport-conflicts, /containers/plan/pending)
# muszą wygrać z GET /containers/{container_id} zdefiniowanym niżej.
for _sub in (containers_bulk, containers_orders, containers_write, containers_planning,
             containers_contents,
             containers_purge, containers_changes, containers_stats):
    router.include_router(_sub.router)

# --- kontenery ---

@router.get("/containers", response_model=list[ContainerOut])
def list_containers(
    db: Session = Depends(get_db),
    user: User = viewer_or_sales,
    status_filter: str | None = Query(default=None, alias="status"),
    customs_status: str | None = None,
    document_status: str | None = None,
    supplier_id: str | None = None,
    forwarder_id: str | None = None,
    warehouse_id: str | None = None,
    warehouse_name: str | None = None,
    company_id: int | None = None,
    company_code: str | None = None,
    exclude_company_code: str | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    completed: bool | None = None,
    delayed: bool | None = None,
    transit: bool | None = None,
    q: str | None = None,
    # #5 — filtry per kolumna: tekst (ILIKE), enum (transport), zakres (ETA)
    vessel: str | None = None,
    transport: str | None = None,
    order_numbers: str | None = None,
    delivery_note: str | None = None,
    incoming_delivery_no: str | None = None,
    purchase_note: str | None = None,
    document_flow: str | None = None,
    sent_number: str | None = None,
    eta_from: datetime.date | None = None,
    eta_to: datetime.date | None = None,
    limit: int | None = Query(default=500, ge=1, le=2000),
    response: Response = None,
):
    # archiwum od najnowszych — przy limicie rosnąco pokazywało 500 NAJSTARSZYCH (audyt DATA-002)
    order = ((Container.notify_date.desc().nulls_last(), Container.id.desc()) if completed is True
             else (Container.notify_date.asc().nulls_last(), Container.id))
    query = select(Container).options(*_LOAD).order_by(*order)
    query = scope_containers(query, user)
    if company_id is not None:
        query = query.where(Container.company_id == company_id)
    query = apply_company_code_filter(query, db, Container.company_id,
                                      company_code, exclude_company_code)
    query = _enum_filter(query, Container.status, status_filter, ContainerStatus)
    query = _enum_filter(query, Container.document_status, document_status, DocumentStatus)
    # filtry i szukanie tylko po polach, które rola widzi (hidden_fields) — inaczej
    # magazyn/agencja potwierdzałyby istnienie PO/dostawcy samym wynikiem wyszukiwania
    hidden = hidden_fields(user)
    if "customs_status" not in hidden:   # spedytor nie widzi odprawy (2026-09-28)
        query = _enum_filter(query, Container.customs_status, customs_status, CustomsStatus)
    if "supplier_id" not in hidden:
        query = _fk_filter(query, Container.supplier_id, supplier_id)
    if "forwarder_id" not in hidden:
        query = _fk_filter(query, Container.forwarder_id, forwarder_id)
    query = _fk_filter(query, Container.warehouse_id, warehouse_id)
    if warehouse_name:
        # kolejka DLT = kontenery spółki (Acme) kierowane do magazynu o tej nazwie
        query = query.join(Warehouse, Container.warehouse_id == Warehouse.id).where(
            func.upper(Warehouse.name) == warehouse_name.upper())
    if date_from is not None:
        query = query.where(Container.notify_date >= date_from)
    if date_to is not None:
        query = query.where(Container.notify_date <= date_to)
    # #5 — filtry per kolumna
    for field, val in (("vessel", vessel), ("order_numbers", order_numbers),
                       ("delivery_note", delivery_note),
                       ("incoming_delivery_no", incoming_delivery_no),
                       ("purchase_note", purchase_note), ("document_flow", document_flow),
                       ("sent_number", sent_number)):
        if val and field not in hidden:
            query = query.where(getattr(Container, field).ilike(f"%{val}%"))
    query = _enum_filter(query, Container.transport_type, transport, TransportType)
    if eta_from is not None:
        query = query.where(Container.eta >= eta_from)
    if eta_to is not None:
        query = query.where(Container.eta <= eta_to)
    if completed is True:
        query = query.where(~Container.open_in_queue())   # archiwum
    elif completed is False:
        query = query.where(Container.open_in_queue())    # kolejka (DOSTARCZONY też)
    if transit is not None:
        query = query.where(Container.is_transit.is_(transit))
    if q:
        like = f"%{q}%"
        # każda gałąź OR ma indeks (GIN pg_trgm / FK) i zostaje na containers — PERF-007
        conds = searchable(user, {
            "container_no": Container.container_no.ilike(like),
            "notes": Container.notes.ilike(like), "vessel": Container.vessel.ilike(like),
            "transport_id": Container.transport_id.ilike(like),
            "order_numbers": Container.order_numbers.ilike(like),
            "order_number": fk_matches(db, Container.order_id,
                                       select(Order.id).where(Order.number.ilike(like)))})
        query = query.where(or_(*conds))
    if delayed is not None:
        clause = Container.delayed_clause(today_pl())
        query = query.where(clause if delayed else ~clause)
    rows = db.scalars(query.limit(limit)).all()
    if response is not None:
        # lista obcięta limitem → UI pokazuje „pokazano N z M” zamiast cicho gubić rekordy
        total = len(rows)
        if limit is not None and total == limit:
            sub = query.order_by(None).subquery()
            total = db.scalar(select(func.count(func.distinct(sub.c.id))))
        response.headers["X-Total-Count"] = str(total)
    care = customer_order_map(db, rows, user)
    deadlines = demurrage_deadlines(db, rows)
    items = [to_out(c, user) for c in rows]
    for it in items:
        it.customer_order = care.get(it.id)
        it.demurrage_deadline = deadlines.get(it.id)
    return _attach_status_ages(db, items)


_ACTIVE_JOB = (TransportJobStatus.SZKIC, TransportJobStatus.WYSLANE)


@router.get("/containers/to-forward", response_model=list[ContainerOut])
def containers_to_forward(db: Session = Depends(get_db), user: User = editors):
    """Kolejka „do zlecenia": aktywne kontenery bez aktywnego TransportJob, z flagą
    needs_forwarding albo bez przypisanego spedytora. Scoping per spółka."""
    # kontenery uwięzione w aktywnym zleceniu (SZKIC/WYSLANE) — wykluczamy
    busy = (select(TransportJobContainer.container_id)
            .join(TransportJob, TransportJob.id == TransportJobContainer.job_id)
            .where(TransportJob.status.in_(_ACTIVE_JOB)))
    query = (select(Container).options(*_LOAD)
             .where(Container.status.not_in(Container.FINISHED),
                    Container.id.not_in(busy),
                    or_(Container.needs_forwarding.is_(True),
                        Container.forwarder_id.is_(None)))
             .order_by(Container.notify_date.asc().nulls_last(), Container.id))
    query = scope_containers(query, user)
    return [to_out(c, user) for c in db.scalars(query).all()]


class NeedsForwardingIn(BaseModel):
    value: bool


@router.patch("/containers/{container_id}/needs-forwarding", response_model=ContainerOut)
def set_needs_forwarding(container_id: int, body: NeedsForwardingIn,
                         db: Session = Depends(get_db), user: User = editors):
    container = get_scoped(db, Container, container_id, user)
    record_changes(db, container, {"needs_forwarding": body.value}, user)
    db.commit()
    db.refresh(container)
    return to_out(container, user)



@router.get("/containers/counts")
def container_counts(db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Liczba aktywnych (niezrealizowanych) kontenerów per spółka — do kart zakładek.

    Zawsze zwraca wszystkie spółki (0 gdy brak), w zakresie widoczności użytkownika.
    Zadeklarowany PRZED /containers/{container_id}, by „counts" nie trafiło w {id}.
    """
    query = select(Container.company_id, func.count(Container.id))
    query = scope_containers(query, user)
    query = query.where(Container.open_in_queue())
    query = query.group_by(Container.company_id)
    by_id = {cid: count for cid, count in db.execute(query)}
    # nie ujawniamy pełnej listy kodów spółek rolom spoza centrali: view_all → wszystkie;
    # rola przypisana do spółki → tylko jej; rola bez spółki (spedytor) → spółki widocznych kontenerów
    company_q = select(Company)
    if not can_view_all(user):
        own = own_company_id(user)
        visible = [own] if own is not None else list(by_id)
        company_q = company_q.where(Company.id.in_(visible))
    companies = db.scalars(company_q).all()
    counts = {c.code: by_id.get(c.id, 0) for c in companies}
    # DLT to nie spółka, lecz magazyn (kontenery Acme kierowane do DLT)
    dlt_q = select(func.count(Container.id)).join(
        Warehouse, Container.warehouse_id == Warehouse.id)
    dlt_q = scope_containers(dlt_q, user)
    dlt_q = dlt_q.where(Container.open_in_queue(),
                        func.upper(Warehouse.name) == "DLT")
    counts["DLT"] = db.scalar(dlt_q) or 0
    return counts


@router.get("/containers/{container_id}", response_model=ContainerOut)
def get_container(container_id: int, db: Session = Depends(get_db), user: User = viewer_or_sales):
    container = get_container_checked(db, container_id, user)
    out = to_out(container, user)
    # #35: przeladunek? — rozne statki w eventach trackingu albo ostatni event
    # z innym statkiem niz pole kontenera (tylko tu, nie na liscie — N+1)
    from ..models import TrackingEvent
    from ..tracking.ais import normalize_name
    names = {normalize_name(v) for v in db.scalars(
        select(TrackingEvent.vessel).where(TrackingEvent.container_id == container.id,
                                           TrackingEvent.vessel != "")).all()}
    names.discard("")
    own = normalize_name(container.vessel or "")
    out.vessel_mismatch = len(names) > 1 or (bool(names) and bool(own) and own not in names)
    # brakujące typy dokumentów (wspólne źródło prawdy) — zasila wiedzę kontekstową na karcie
    from .customs import missing_document_types
    # spedytor: braki dokumentów odprawowych zdradzałyby obieg odprawy (_FORWARDER_HIDDEN)
    if "missing_documents" not in hidden_fields(user):
        out.missing_documents = missing_document_types(db, container)
    return out


@router.get("/containers/{container_id}/palletization")
def get_palletization(container_id: int, db: Session = Depends(get_db), user: User = viewer):
    """#46: sekcja paletyzacji na karcie rozładunku — proxy do serwisu paletyzacji (best-effort).
    Serwis paletyzacji NIE ma dziś endpointu z planem paletyzacji ani pola
    numeru kontenera na Shipment/HU. Puste pallet_api_url = wyłączone."""
    container = get_container_checked(db, container_id, user)
    if not settings.pallet_api_url:
        return {"configured": False}
    try:
        resp = httpx.get(
            f"{settings.pallet_api_url.rstrip('/')}/handling-units",
            params={"q": container.container_no},
            headers={"X-API-Key": settings.pallet_api_token},
            timeout=settings.pallet_api_timeout,
        )
        resp.raise_for_status()
        return {"configured": True, "data": resp.json()}
    except httpx.HTTPError as exc:
        logger.warning("Pallet service proxy failed for %s: %s", container.container_no, exc)
        return {"configured": True, "error": "Serwis paletyzacji niedostępny."}


@router.get("/containers/{container_id}/history", response_model=list[AuditOut])
def container_history(container_id: int, db: Session = Depends(get_db), user: User = viewer_or_sales):
    get_container_checked(db, container_id, user)
    entries = db.scalars(
        select(AuditLog).options(selectinload(AuditLog.user))
        .where(AuditLog.entity_type == "containers", AuditLog.entity_id == container_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())).all()
    # pola maskowane w to_out pomijamy — historia zmian ujawniłaby ich wartości
    hidden = hidden_fields(user)
    result = []
    for entry in entries:
        if entry.field in hidden:
            continue  # nie ujawniamy zmian pól zamaskowanych dla tej roli
        out = AuditOut.model_validate(entry)
        out.user_login = entry.user.login if entry.user else None
        result.append(out)
    return result


@router.get("/containers/export/xlsx")
def export_containers(
    db: Session = Depends(get_db),
    user: User = viewer,
    status_filter: str | None = Query(default=None, alias="status"),
    customs_status: str | None = None,
    supplier_id: str | None = None,
    forwarder_id: str | None = None,
    warehouse_id: str | None = None,
    warehouse_name: str | None = None,
    company_code: str | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    completed: bool | None = None,
    delayed: bool | None = None,
    q: str | None = None,
):
    """Eksport przefiltrowanej kolejki do pliku Excel (.xlsx)."""
    from io import BytesIO

    from fastapi.responses import StreamingResponse
    from openpyxl import Workbook

    from ..date_pl import date_pl
    from ..exports import XLSX_MIME, append_row

    rows = list_containers(
        db=db, user=user, status_filter=status_filter, customs_status=customs_status,
        supplier_id=supplier_id, forwarder_id=forwarder_id, warehouse_id=warehouse_id,
        warehouse_name=warehouse_name, company_code=company_code,
        date_from=date_from, date_to=date_to,
        completed=completed, delayed=delayed, q=q, limit=None)   # eksport = wszystkie pasujące

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "KOLEJKA"
    headers = ["DATA AWIZACJI", "NR KONTENERA", "SPÓŁKA", "DOSTAWCA", "NR ZAMÓWIENIA",
               "ETA", "ATD", "STATUS", "STATUS ODPRAWY", "STATUS DOKUMENTÓW",
               "SPEDYTOR", "MAGAZYN", "PORT",
               "STATEK", "TRANSPORT", "WIELKOŚĆ", "DOKUMENTY", "AGENCJA CELNA",
               "DNI WOLNE OD DEMURRAGE", "NR DOSTAWY", "NR RF", "OPÓŹNIONY", "UWAGI"]
    append_row(sheet, headers)
    for c in rows:
        append_row(sheet, [
            date_pl(c.notify_date), c.container_no, c.company_name, c.supplier_name,
            c.order_number, date_pl(c.eta), date_pl(c.atd),
            c.status.value, c.customs_status.value, c.document_status.value,
            c.forwarder_name, c.warehouse_name, c.port_name, c.vessel,
            c.transport_type.value if c.transport_type else "", c.container_size,
            "TAK" if c.documents_ok else "", c.customs_agency,
            c.demurrage_free_days, c.incoming_delivery_no, c.rf_number,
            "TAK" if c.is_delayed else "", c.notes,
        ])
    for column in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(30, max(10, width + 2))

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    filename = f"kolejka_{today_pl().isoformat()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

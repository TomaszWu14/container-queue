"""Zapis kontenera: utworzenie, import numerów PO, edycja, status, magazyn rozładunku."""

from ..models import today_pl
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import iso6346
from ..audit import record, record_changes
from ..database import get_db
from ..document_tiles import WARN_CUSTOMS, WARN_STATUS, missing_docs_warning
from ..deps import AdminOnly as admins
from ..deps import Editors as editors
from ..deps import WarehouseOrEditors as warehouse_or_editors
from ..deps import resolve_company_id, scope_containers
from ..models import (
    Company,
    Container,
    ContainerStatus,
    PlanningStatus,
    Role,
    User,
    Warehouse,
    utcnow,
)
from ..order_numbers import split_order_numbers
from ..planning import proposed_date, record_if_over_limit, reset_plan
from ..schemas import ContainerCreate, ContainerOut, ContainerUpdate, StatusChange, WarehouseNameIn
from ..tracking.service import reset_tracking
from .containers_common import (
    _TRACKABLE_STATUSES,
    _check_company_fks,
    _notify_new_delivery,
    _resolve_order,
    check_customs_status_change,
    check_not_modified,
    check_status_transition,
    sync_status_from_customs,
    get_container_checked,
    next_transport_id,
    to_out,
    transport_job_conflicts,
)

# sub-router bez prefiksu — podpinany w routers/containers.py (prefiks /api, tag kolejka)
router = APIRouter()


@router.post("/containers", response_model=ContainerOut, status_code=201)
def create_container(body: ContainerCreate, db: Session = Depends(get_db), user: User = editors):
    company_id = resolve_company_id(db, user, body.company_id)
    _check_company_fks(db, company_id, body.supplier_id, body.warehouse_id, body.order_id)
    data = body.model_dump(exclude={"company_id", "order_number"})
    data["order_id"] = _resolve_order(db, company_id, body.order_id,
                                      body.order_number, body.supplier_id)
    container = Container(company_id=company_id, **data)
    # utworzenie od razu jako ZREALIZOWANY — completed_at jak w apply_status (retencja RODO
    # liczy od completed_at; bez niego kontener nigdy nie byłby czyszczony)
    if container.status == ContainerStatus.ZREALIZOWANY:
        container.completed_at = utcnow()
    # brak jawnej daty rozładunku + znana ETA => wstępna propozycja (eta + 4 dni)
    if container.eta and not container.notify_date:
        container.notify_date = proposed_date(container.eta)
    year = (container.notify_date or today_pl()).year
    container.transport_id = next_transport_id(db, db.get(Company, company_id), year)
    db.add(container)
    db.flush()
    record(db, entity_type="containers", entity_id=container.id, field="status",
           old_value=None, new_value=container.status.value, user=user, note="utworzenie")
    try:
        db.commit()
    except IntegrityError:
        # równoległe utworzenie zajęło ten sam transport_id — czytelne 409 do ponowienia
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Konflikt numeracji transportu — spróbuj ponownie.") from None
    _notify_new_delivery(db, container, user)   # Q66: powiadom magazyn o nowej dostawie
    from .quotes import ensure_transit_quote
    ensure_transit_quote(db, container, user)   # tranzyt (numer 47…) => auto-SZKIC wyceny
    return to_out(get_container_checked(db, container.id, user), user)


@router.post("/containers/import-po")
def import_po(file: UploadFile, db: Session = Depends(get_db), user: User = admins):
    """#42: dopisuje numery zamówień (order_numbers) do ISTNIEJĄCYCH kontenerów po
    numerze kontenera. Nie tworzy nowych kontenerów — sam import PO nie ma dość
    danych (spółka, ETA...), żeby założyć rekord bezpiecznie."""
    from ..config import settings
    from ..tabular import load_workbook_or_422, normalize_header
    from .forwarding_files import read_upload_capped
    content = read_upload_capped(file, settings.max_upload_mb, "Plik PO")
    sheet = load_workbook_or_422(content).worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pusty plik.")
    header = [normalize_header(c) for c in rows[0]]
    if "container_no" not in header or "order_numbers" not in header:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Brak wymaganych kolumn: container_no, order_numbers.")
    no_idx, po_idx = header.index("container_no"), header.index("order_numbers")

    matched, skipped = 0, 0
    touched = []
    for row in rows[1:]:
        no_raw = str(row[no_idx] or "").strip() if row and no_idx < len(row) else ""
        po_raw = str(row[po_idx] or "").strip() if row and po_idx < len(row) else ""
        if not no_raw or not po_raw:
            skipped += 1
            continue
        number = iso6346.normalize(no_raw)
        container = db.scalar(scope_containers(
            select(Container).where(Container.container_no == number), user))
        if not container:
            skipped += 1
            continue
        existing = set(split_order_numbers(container.order_numbers))
        new = [n for n in split_order_numbers(po_raw) if n not in existing]
        if new:   # dopisz tylko brakujące numery — istniejący tekst zostaje nietknięty
            old = container.order_numbers
            container.order_numbers = ", ".join(filter(None, [(old or "").strip(), *new]))
            record(db, entity_type="containers", entity_id=container.id, field="order_numbers",
                   old_value=old or None, new_value=container.order_numbers, user=user,
                   note=f"import PO ({file.filename})")
            touched.append(container)
        matched += 1
    db.commit()
    from .quotes import ensure_transit_quote
    for container in touched:
        ensure_transit_quote(db, container, user)   # tranzyt (numer 47…) => auto-SZKIC wyceny
    return {"matched": matched, "skipped": skipped}


@router.patch("/containers/{container_id}", response_model=ContainerOut)
def update_container(container_id: int, body: ContainerUpdate,
                     db: Session = Depends(get_db), user: User = editors):
    container = get_container_checked(db, container_id, user)
    changes = body.model_dump(exclude_unset=True)
    note = changes.pop("change_note", "")
    check_not_modified(db, container, changes.pop("expected_updated_at", None))
    check_customs_status_change(container.customs_status, changes.get("customs_status"), user, note)
    # ręczne wpisanie daty zamraża ją przed automatem ETA (patrz app/planning.py)
    reset_needed = False
    if "notify_date" in changes and changes["notify_date"] != container.notify_date:
        changes["notify_date_manual"] = True
        # data uzgodniona ze spedycją zmieniona u nas => plan przestaje być uzgodniony
        # także WYSLANE: spedycja ma starą datę w mailu, więc uzgodnienia startują od nowa
        reset_needed = container.planning_status != PlanningStatus.PROPOZYCJA
    # doczepiane rekordy muszą należeć do spółki kontenera (izolacja danych)
    _check_company_fks(db, container.company_id,
                       changes.get("supplier_id"), changes.get("warehouse_id"),
                       changes.get("order_id"))
    prev_warehouse_id = container.warehouse_id
    prev_no = container.container_no
    prev_customs = container.customs_status
    record_changes(db, container, changes, user, note=note)
    if "customs_status" in changes:
        sync_status_from_customs(db, container, user)   # status kontenera z odprawy (2026-09-28)
    docs_warning = (missing_docs_warning(db, container, user, container.customs_status.value)
                    if container.customs_status != prev_customs
                    and container.customs_status in WARN_CUSTOMS else None)
    if container.container_no != prev_no:
        # tracking starego numeru to dane innego kontenera — oś/ETD/status od nowa
        reset_tracking(db, container, user)
    # zmiana numeru lub wyjście ze statusu śledzonego kasuje stary błąd trackingu —
    # inaczej user widzi „Błąd trackingu" na kontenerze, który dawno nie jest śledzony
    if "container_no" in changes or (
            "status" in changes and container.status not in _TRACKABLE_STATUSES):
        container.tracking_error = ""
    if reset_needed:
        reset_plan(db, container, user, note="zmiana daty po potwierdzeniu spedycji")
    if container.warehouse_id != prev_warehouse_id:
        record_if_over_limit(db, container, user)
    db.commit()
    if container.warehouse_id and container.warehouse_id != prev_warehouse_id:
        _notify_new_delivery(db, container, user)   # Q66: (prze)przypisano magazyn
    from .quotes import ensure_transit_quote
    ensure_transit_quote(db, container, user)   # tranzyt (numer 47…) => auto-SZKIC wyceny
    out = to_out(get_container_checked(db, container_id, user), user)
    out.docs_warning = docs_warning
    # #49: ostrzeżenie (nie blokada) — ten sam dostawca ma już ≥2 inne kontenery
    # z tą samą datą awizacji (i tym samym magazynem, gdy ustawiony)
    if "notify_date" in changes and container.notify_date and container.supplier_id:
        others_q = select(func.count(Container.id)).where(
            Container.supplier_id == container.supplier_id,
            Container.notify_date == container.notify_date,
            Container.id != container.id,
            Container.status.notin_(Container.FINISHED))
        if container.warehouse_id:
            others_q = others_q.where(Container.warehouse_id == container.warehouse_id)
        others = db.scalar(others_q) or 0
        if others >= 2:
            out.notify_conflict = others
    # ostrzeżenie (nie blokada): zapis daty/magazynu rozjechał paczkę transportową
    # na różne magazyny tego samego dnia
    if ("notify_date" in changes or "warehouse_id" in changes) and container.notify_date:
        hits = transport_job_conflicts(db, user, container.notify_date,
                                       container.notify_date, [container.id])
        mine = next((h for h in hits if h["container_id"] == container.id), None)
        if mine:
            out.transport_conflict = mine["warehouses"]
    return out


# statusy, z których magazyn potwierdza rozładunek bez tłumaczenia się
_UNLOAD_EXPECTED = (ContainerStatus.AWIZOWANY, ContainerStatus.W_DOSTAWIE, ContainerStatus.DOSTARCZONY)


def apply_status(db: Session, container: Container, body: StatusChange, user: User,
                 warnings: list[str] | None = None) -> bool:
    """Walidacja + audyt + zmiana statusu (bez commita) — wspólne dla pojedynczej i masowej.
    Zwraca True, gdy status faktycznie się zmienił; błąd = HTTPException przed mutacją.
    Braki dokumentów przy DOSTARCZONY: wpis w historii, tekst ostrzeżenia do `warnings`."""
    # decyzja 2026-09-28: ZREALIZOWANY ustawia logistyka po zamknięciu formalności (faktury,
    # dokumenty) — magazyn tylko potwierdza rozładunek
    if user.role == Role.warehouse and body.status != ContainerStatus.DOSTARCZONY:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Magazyn może tylko potwierdzić rozładunek. Zrealizowany ustawia logistyka.")
    if body.status == container.status:
        return False
    # decyzja 2026-09-28 (audyt BIZ-002): rozładunek kontenera, który nie jest awizowany / w dostawie,
    # jest dopuszczalny (przyjechał bez awizacji), ale magazyn musi napisać dlaczego
    if (user.role == Role.warehouse and container.status not in _UNLOAD_EXPECTED
            and not (body.note or "").strip()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Kontener nie jest awizowany — potwierdzenie rozładunku wymaga notatki.")
    check_status_transition(container.status, body.status, user, body.note)
    record(db, entity_type="containers", entity_id=container.id, field="status",
           old_value=container.status.value, new_value=body.status.value,
           user=user, note=body.note)
    container.status = body.status
    # dosłownie ZREALIZOWANY: completed_at = moment realizacji (nie rozładunku)
    container.completed_at = utcnow() if body.status == ContainerStatus.ZREALIZOWANY else None
    if body.status not in _TRACKABLE_STATUSES:
        container.tracking_error = ""  # wyszedł ze śledzenia — nie trzymaj starego błędu
    if body.status in WARN_STATUS:
        warning = missing_docs_warning(db, container, user, body.status.value)
        if warning and warnings is not None:
            warnings.append(warning)
    return True


@router.post("/containers/{container_id}/status", response_model=ContainerOut)
def change_status(container_id: int, body: StatusChange,
                  db: Session = Depends(get_db), user: User = warehouse_or_editors):
    container = get_container_checked(db, container_id, user)
    warnings: list[str] = []
    if not apply_status(db, container, body, user, warnings):
        return to_out(container, user)
    db.commit()
    out = to_out(get_container_checked(db, container_id, user), user)
    out.docs_warning = warnings[0] if warnings else None
    return out


def apply_warehouse(db: Session, container: Container, raw_name: str, user: User) -> bool:
    """Magazyn rozładunku po nazwie (brakujący tworzony w spółce kontenera) + audyt i kontrola
    limitu dnia, bez commita — wspólne dla pojedynczej i masowej zmiany. True = zmieniono."""
    name = raw_name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pusta nazwa magazynu.")
    warehouse = db.scalar(select(Warehouse).where(
        Warehouse.company_id == container.company_id,
        func.upper(Warehouse.name) == name.upper()))
    if warehouse is None:
        warehouse = Warehouse(company_id=container.company_id, name=name, country="PL")
        db.add(warehouse)
        db.flush()
    if container.warehouse_id == warehouse.id:
        return False
    old = container.warehouse.name if container.warehouse else None
    record(db, entity_type="containers", entity_id=container.id, field="warehouse",
           old_value=old, new_value=warehouse.name, user=user,
           note=f"zmiana magazynu rozładunku: {old or '—'} → {warehouse.name}")
    # przypisujemy relację (nie tylko FK), by odpowiedź odświeżyła nazwę magazynu
    container.warehouse = warehouse
    record_if_over_limit(db, container, user)
    return True


@router.post("/containers/{container_id}/warehouse", response_model=ContainerOut)
def change_warehouse(container_id: int, body: WarehouseNameIn,
                     db: Session = Depends(get_db), user: User = editors):
    """Szybka zmiana magazynu rozładunku (menu kontekstowe w kolejce).

    Magazyn to nazwa przypięta do spółki kontenera (DLT/ACME/BOREALIS/…); brakujący
    tworzony jest w locie — spójne z importem, który tworzy magazyny per spółka.
    """
    container = get_container_checked(db, container_id, user)
    if apply_warehouse(db, container, body.name, user):
        db.commit()
        _notify_new_delivery(db, container, user)   # Q66: (prze)przypisano magazyn
    out = to_out(get_container_checked(db, container_id, user), user)
    # ostrzeżenie (nie blokada): zmiana magazynu rozjechała paczkę transportową
    if container.notify_date:
        hits = transport_job_conflicts(db, user, container.notify_date,
                                       container.notify_date, [container.id])
        mine = next((h for h in hits if h["container_id"] == container.id), None)
        if mine:
            out.transport_conflict = mine["warehouses"]
    return out

"""Moduł agencji celnej (odprawa) — dwustronny obieg.

Flow procesowy (jasny i przejrzysty):
  1. Logistyka ZLECA odprawę wskazanej agencji celnej  → status ZLECONA, agencja powiadomiona.
  2. Agencja WYZNACZA / ZMIENIA agenta prowadzącego     → nasi pracownicy powiadomieni.
  3. Agencja aktualizuje STATUS odprawy (rewizja/odprawiony/dokumenty) → druga strona powiadomiona.
  4. Obie strony komunikują się przez wiadomości przy kontenerze (istniejący kanał).

Zakres widoczności agencji: wyłącznie kontenery, których odprawę jej zlecono
(egzekwowane przez scope_containers / check_container_access w deps).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record, record_changes, record_created
from ..database import get_db
from ..document_tiles import WARN_CUSTOMS, missing_docs_warning
from ..deps import AdminOnly as admin_only
from ..deps import Editors as logistics_or_admin
from ..deps import PurchasingReaders as docs_senders
from ..deps import Viewer as viewer
from ..deps import scope_containers
from ..models import (
    Attachment,
    Container,
    CustomsAgency,
    CustomsCaseStatus,
    CustomsStatus,
    DocumentStatus,
    DocumentType,
    Role,
    User,
    today_pl,
    utcnow,
)
from ..notifications import company_watchers, customs_agency_users, notify
from ..schemas import (
    ContainerOut,
    CustomsAgencyOut,
    CustomsAgentIn,
    CustomsAssignIn,
    CustomsCaseStatusIn,
    CustomsCaseStatusOut,
    CustomsCaseStatusSetIn,
    CustomsStatusIn,
    DocumentTypeIn,
    DocumentTypeOut,
    SendDocsIn,
)
from ..security import require_roles
from .containers import _LOAD, get_container_checked, to_out
from .containers_common import check_customs_status_change, sync_status_from_customs

router = APIRouter(prefix="/api/customs", tags=["agencja celna"])

customs_side = Depends(require_roles(Role.admin, Role.logistics, Role.customs))
# wysyłka dokumentów: także dział zakupów (komunikacja zakupy ↔ transport ↔ agencja)


def _status_label(customs_status: CustomsStatus) -> str:
    return {
        CustomsStatus.BRAK: "brak",
        CustomsStatus.DOKUMENTY_KOMPLETNE: "dokumenty kompletne",
        CustomsStatus.ZLECONA: "zlecona",
        CustomsStatus.DRAFT_WYSLANY: "draft zgłoszenia wysłany",
        CustomsStatus.DRAFT_POTWIERDZONY: "draft zgłoszenia potwierdzony",
        CustomsStatus.ODPRAWIONY: "odprawiony",
        CustomsStatus.ZWOLNIONY: "zwolniony (można wydać)",
        CustomsStatus.ROZLICZONY: "rozliczony",
        CustomsStatus.REWIZJA: "rewizja",
    }.get(customs_status, customs_status.value)


@router.get("/agencies", response_model=list[CustomsAgencyOut])
def list_agencies(db: Session = Depends(get_db), user: User = logistics_or_admin):
    """Aktywne agencje celne — do wyboru przy zlecaniu odprawy."""
    return db.scalars(select(CustomsAgency).where(CustomsAgency.is_active)
                      .order_by(CustomsAgency.name)).all()


@router.get("/board", response_model=list[ContainerOut])
def customs_board(response: Response, db: Session = Depends(get_db), user: User = customs_side,
                  archive: bool = False, limit: int = Query(default=500, ge=1, le=2000)):
    """Tablica odpraw.

    Agencja celna: kontenery jej zlecone (wszystkie statusy odprawy).
    Logistyka/admin: kontenery w zakresie, które są w obiegu celnym
    (przypisana agencja lub status odprawy inny niż BRAK).
    Domyślnie tylko niezrealizowane (audyt PERF-003: pełna historia to 12,7 MB);
    `archive=true` = zrealizowane, od najnowszych, z limitem i X-Total-Count."""
    query = select(Container).options(*_LOAD)
    query = scope_containers(query, user)
    if user.role != Role.customs:
        query = query.where(
            Container.customs_agency_id.is_not(None)
            | (Container.customs_status != CustomsStatus.BRAK))
    if archive:
        query = query.where(~Container.open_in_queue()).order_by(
            Container.customs_assigned_at.desc().nullslast(), Container.id.desc())
    else:
        query = query.where(Container.open_in_queue()).order_by(
            Container.customs_assigned_at.desc().nullslast(), Container.eta.asc().nullslast())
    rows = db.scalars(query.limit(limit)).all()
    total = len(rows)
    if total == limit:
        sub = query.order_by(None).subquery()
        total = db.scalar(select(func.count()).select_from(sub))
    response.headers["X-Total-Count"] = str(total)
    # braki checklisty dla całej tablicy w 2 zapytaniach (bez N+1)
    required = db.scalars(select(DocumentType)
                          .where(DocumentType.is_active, DocumentType.is_required)
                          .order_by(DocumentType.sort_order, DocumentType.name)).all()
    present: dict[int, set[int]] = {}
    if required and rows:
        pairs = db.execute(select(Attachment.container_id, Attachment.document_type_id)
                           .where(Attachment.container_id.in_([c.id for c in rows]),
                                  Attachment.document_type_id.is_not(None))).all()
        for cid, dtid in pairs:
            present.setdefault(cid, set()).add(dtid)
    out_rows = []
    for c in rows:
        out = to_out(c, user)
        if required and in_customs_flow(c):
            have = present.get(c.id, set())
            out.missing_documents = [dt.name for dt in required if dt.id not in have]
        else:
            out.missing_documents = []
        out_rows.append(out)
    return out_rows


@router.post("/containers/{container_id}/assign", response_model=ContainerOut)
def assign_agency(container_id: int, body: CustomsAssignIn,
                  db: Session = Depends(get_db), user: User = logistics_or_admin):
    """Logistyka zleca odprawę agencji celnej (lub zmienia agencję)."""
    container = get_container_checked(db, container_id, user)
    agency = db.get(CustomsAgency, body.customs_agency_id)
    if not agency or not agency.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono aktywnej agencji celnej.")
    previous_agency_id = container.customs_agency_id
    changes: dict = {
        "customs_agency_id": agency.id,
        "customs_agency": agency.name,
        "customs_assigned_at": utcnow(),
    }
    if body.customs_date is not None:
        changes["customs_date"] = body.customs_date
    if body.customs_note:
        changes["customs_note"] = body.customs_note
    # zmiana agencji = nowy agent musi być wyznaczony od nowa
    if previous_agency_id and previous_agency_id != agency.id:
        changes["customs_agent_name"] = ""
        changes["customs_agent_phone"] = ""
        changes["customs_agent_email"] = ""
    if container.customs_status in (CustomsStatus.BRAK, CustomsStatus.DOKUMENTY_KOMPLETNE):
        changes["customs_status"] = CustomsStatus.ZLECONA
    record_changes(db, container, changes, user, note="zlecenie odprawy agencji celnej")
    sync_status_from_customs(db, container, user)   # status kontenera z odprawy (2026-09-28)
    # powiadom nową agencję (a przy zmianie — także poprzednią, że odpięto)
    notify(db, customs_agency_users(db, agency.id), kind="customs",
           title=f"Zlecono odprawę: {container.container_no}",
           body=f"Agencja {agency.name} — prosimy o wyznaczenie agenta i prowadzenie odprawy."
                + (f" Uwagi: {body.customs_note}" if body.customs_note else ""),
           container_id=container.id, exclude_user_id=user.id)
    if previous_agency_id and previous_agency_id != agency.id:
        notify(db, customs_agency_users(db, previous_agency_id), kind="customs",
               title=f"Odprawa przekazana innej agencji: {container.container_no}",
               body="Kontener nie jest już przypisany do Waszej agencji.",
               container_id=container.id, exclude_user_id=user.id)
    db.commit()
    return to_out(get_container_checked(db, container_id, user), user)


@router.post("/containers/{container_id}/unassign", response_model=ContainerOut)
def unassign_agency(container_id: int, db: Session = Depends(get_db),
                    user: User = logistics_or_admin):
    """Logistyka wycofuje zlecenie odprawy (odpina agencję)."""
    container = get_container_checked(db, container_id, user)
    previous_agency_id = container.customs_agency_id
    if not previous_agency_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Kontener nie ma przypisanej agencji celnej.")
    changes = {
        "customs_agency_id": None,
        "customs_agent_name": "",
        "customs_agent_phone": "",
        "customs_agent_email": "",
    }
    if container.customs_status == CustomsStatus.ZLECONA:
        changes["customs_status"] = CustomsStatus.BRAK
    record_changes(db, container, changes, user, note="wycofanie zlecenia odprawy")
    notify(db, customs_agency_users(db, previous_agency_id), kind="customs",
           title=f"Wycofano zlecenie odprawy: {container.container_no}",
           body="Kontener został odpięty od Waszej agencji.",
           container_id=container.id, exclude_user_id=user.id)
    db.commit()
    return to_out(get_container_checked(db, container_id, user), user)


@router.post("/containers/{container_id}/agent", response_model=ContainerOut)
def set_agent(container_id: int, body: CustomsAgentIn,
              db: Session = Depends(get_db), user: User = customs_side):
    """Agencja celna wyznacza/zmienia agenta prowadzącego odprawę. Nasi pracownicy powiadomieni."""
    container = get_container_checked(db, container_id, user)
    if container.customs_agency_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Kontener nie ma przypisanej agencji celnej.")
    changes = {
        "customs_agent_name": body.customs_agent_name.strip(),
        "customs_agent_phone": body.customs_agent_phone.strip(),
        "customs_agent_email": body.customs_agent_email.strip(),
    }
    record_changes(db, container, changes, user, note="wyznaczenie agenta celnego")
    agent = body.customs_agent_name.strip() or "—"
    notify(db, company_watchers(db, container.company_id), kind="customs",
           title=f"Agent celny dla {container.container_no}: {agent}",
           body=f"Agencja {container.customs_agency}: agent {agent}"
                + (f", tel. {body.customs_agent_phone}" if body.customs_agent_phone else ""),
           container_id=container.id, exclude_user_id=user.id)
    db.commit()
    return to_out(get_container_checked(db, container_id, user), user)


# --- checklista kompletności dokumentów -------------------------------------

def in_customs_flow(container: Container) -> bool:
    """Kontener w obiegu celnym — tylko takich dotyczy checklista dokumentów."""
    return (container.customs_agency_id is not None
            or container.customs_status != CustomsStatus.BRAK)


def missing_document_types(db: Session, container: Container) -> list[str]:
    """Nazwy wymaganych typów dokumentów bez ani jednego załącznika (jedno źródło
    prawdy dla UI, wysyłki i alertów). Pusta lista = komplet lub poza obiegiem."""
    return missing_document_types_batch(db, [container])[container.id]


def missing_document_types_batch(db: Session, containers: list[Container]) -> dict[int, list[str]]:
    """Wsadowo {container.id: braki} — dwa zapytania zamiast 2×N (PERF-004)."""
    out: dict[int, list[str]] = {c.id: [] for c in containers}
    ids = [c.id for c in containers if in_customs_flow(c)]
    if not ids:
        return out
    required = db.scalars(select(DocumentType)
                          .where(DocumentType.is_active, DocumentType.is_required)
                          .order_by(DocumentType.sort_order, DocumentType.name)).all()
    if not required:
        return out
    present: set[tuple[int, int]] = set(db.execute(select(
        Attachment.container_id, Attachment.document_type_id).where(
        Attachment.container_id.in_(ids),
        Attachment.document_type_id.is_not(None))).tuples())
    for cid in ids:
        out[cid] = [dt.name for dt in required if (cid, dt.id) not in present]
    return out


def _check_tile_code(db: Session, code: str | None, own_id: int | None) -> None:
    """Jeden typ na kafelek (kafelki dokumentów dostawy) — czytelny 409 zamiast błędu bazy."""
    if code is None:
        return
    other = db.scalar(select(DocumentType).where(DocumentType.tile_code == code))
    if other is not None and other.id != own_id:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Kafelek {code} jest już przypisany do typu „{other.name}”.")


@router.get("/document-types", response_model=list[DocumentTypeOut])
def list_document_types(active_only: bool = False, db: Session = Depends(get_db),
                        user: User = viewer):
    query = select(DocumentType).order_by(DocumentType.sort_order, DocumentType.name)
    if active_only:
        query = query.where(DocumentType.is_active)
    return db.scalars(query).all()


@router.post("/document-types", response_model=DocumentTypeOut, status_code=201)
def create_document_type(body: DocumentTypeIn, db: Session = Depends(get_db),
                         user: User = admin_only):
    if db.scalar(select(DocumentType).where(DocumentType.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki typ dokumentu już istnieje.")
    _check_tile_code(db, body.tile_code, None)
    document_type = DocumentType(**body.model_dump())
    db.add(document_type)
    record_created(db, document_type, user)
    db.commit()
    return document_type


@router.patch("/document-types/{type_id}", response_model=DocumentTypeOut)
def update_document_type(type_id: int, body: DocumentTypeIn,
                         db: Session = Depends(get_db), user: User = admin_only):
    document_type = db.get(DocumentType, type_id)
    if not document_type:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono typu dokumentu.")
    _check_tile_code(db, body.tile_code, type_id)
    record_changes(db, document_type, body.model_dump(exclude_unset=True), user)
    db.commit()
    return document_type


@router.delete("/document-types/{type_id}", status_code=204)
def delete_document_type(type_id: int, db: Session = Depends(get_db), user: User = admin_only):
    from .dictionaries import guarded_delete
    guarded_delete(db, DocumentType, type_id, user, "typ dokumentu")


# --- słownik statusów sprawy celnej (definiowany w panelu admina) ---

@router.get("/case-statuses", response_model=list[CustomsCaseStatusOut])
def list_case_statuses(active_only: bool = False, db: Session = Depends(get_db),
                       user: User = viewer):
    query = select(CustomsCaseStatus).order_by(
        CustomsCaseStatus.sort_order, CustomsCaseStatus.name)
    if active_only:
        query = query.where(CustomsCaseStatus.is_active)
    return db.scalars(query).all()


@router.post("/case-statuses", response_model=CustomsCaseStatusOut, status_code=201)
def create_case_status(body: CustomsCaseStatusIn, db: Session = Depends(get_db),
                       user: User = admin_only):
    if db.scalar(select(CustomsCaseStatus).where(CustomsCaseStatus.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki status już istnieje.")
    case_status = CustomsCaseStatus(**body.model_dump())
    db.add(case_status)
    record_created(db, case_status, user)
    db.commit()
    return case_status


@router.patch("/case-statuses/{status_id}", response_model=CustomsCaseStatusOut)
def update_case_status_entry(status_id: int, body: CustomsCaseStatusIn,
                             db: Session = Depends(get_db), user: User = admin_only):
    case_status = db.get(CustomsCaseStatus, status_id)
    if not case_status:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono statusu.")
    record_changes(db, case_status, body.model_dump(exclude_unset=True), user)
    db.commit()
    return case_status


@router.delete("/case-statuses/{status_id}", status_code=204)
def delete_case_status(status_id: int, db: Session = Depends(get_db), user: User = admin_only):
    from .dictionaries import guarded_delete
    guarded_delete(db, CustomsCaseStatus, status_id, user, "status sprawy celnej")


@router.post("/containers/{container_id}/case-status", response_model=ContainerOut)
def set_case_status(container_id: int, body: CustomsCaseStatusSetIn,
                    db: Session = Depends(get_db), user: User = customs_side):
    """Ustawienie statusu sprawy ze słownika (obie strony). Druga strona powiadomiona."""
    container = get_container_checked(db, container_id, user)
    if container.customs_agency_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Kontener nie ma przypisanej agencji celnej.")
    label, case_status = "—", None
    if body.customs_case_status_id is not None:
        case_status = db.get(CustomsCaseStatus, body.customs_case_status_id)
        if not case_status or not case_status.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                "Nie znaleziono aktywnego statusu sprawy.")
        label = case_status.name
    record_changes(db, container,
                   {"customs_case_status_id": body.customs_case_status_id},
                   user, note="zmiana statusu sprawy celnej")
    # expire_on_commit=False: sesja trzyma zbuforowaną relację (None) mimo zmiany FK —
    # ustawiamy ją jawnie, żeby to_out zwrócił świeżą nazwę statusu
    container.customs_case_status_rel = case_status
    if user.role == Role.customs:
        recipients = company_watchers(db, container.company_id)
    else:
        recipients = customs_agency_users(db, container.customs_agency_id)
    notify(db, recipients, kind="customs",
           title=f"Sprawa celna {container.container_no}: {label}",
           body=body.customs_note, container_id=container.id, exclude_user_id=user.id)
    db.commit()
    return to_out(get_container_checked(db, container_id, user), user)


@router.post("/containers/{container_id}/send-docs", response_model=ContainerOut)
def send_docs_to_agency(container_id: int, body: SendDocsIn | None = None,
                        db: Session = Depends(get_db), user: User = docs_senders):
    """Wysyłka dokumentów do agencji: załączniki kontenera trafiają do wiadomości agencji.

    Wymaga przypisanej agencji i ≥1 załącznika. Braki w checkliście → 409 z listą
    (chyba że force=True — decyzja człowieka, odnotowana w audycie). Ustawia obieg
    dokumentów na WYSLANE i powiadamia użytkowników agencji listą plików."""
    container = get_container_checked(db, container_id, user)
    if container.customs_agency_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Kontener nie ma przypisanej agencji celnej.")
    attachments = db.scalars(select(Attachment)
                             .where(Attachment.container_id == container.id)
                             .order_by(Attachment.created_at)).all()
    if not attachments:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Brak załączników do wysłania — najpierw dodaj dokumenty.")
    recipients = customs_agency_users(db, container.customs_agency_id)
    if not recipients:
        # audyt 2026-10-06 #10: bez kont agencji powiadomienie nie dotrze do nikogo, a status
        # i komunikat mówiły „wysłano” — teraz odmowa ze wskazaniem drogi mailowej
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Agencja nie ma kont w aplikacji — powiadomienie do nikogo nie dotrze. "
                            "Wyślij maila: „Przygotuj maila do agencji” w sekcji faktur.")
    missing = missing_document_types(db, container)
    force = bool(body and body.force)
    if missing and not force:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Braki w checkliście dokumentów: {', '.join(missing)}.")
    note = "wysyłka dokumentów do agencji celnej"
    if missing:
        note += f" MIMO braków: {', '.join(missing)}"
    if container.document_status == DocumentStatus.WYSLANE:
        # ponowna wysyłka nie zmienia statusu — sam fakt (i ew. braki) do audytu
        record(db, entity_type="containers", entity_id=container.id,
               field="document_status", old_value=DocumentStatus.WYSLANE.value,
               new_value=DocumentStatus.WYSLANE.value, user=user, note=note)
    else:
        record_changes(db, container, {"document_status": DocumentStatus.WYSLANE},
                       user, note=note)
    # W5 #36: temat/treść z szablonu (per agencja albo domyślny); brak szablonu
    # w bazie = dotychczasowa treść
    from .documents import render_docs_message
    subject, message = render_docs_message(db, container, attachments)
    notify(db, recipients, kind="customs",
           title=subject, body=message,
           container_id=container.id, exclude_user_id=user.id)
    db.commit()
    return to_out(get_container_checked(db, container_id, user), user)


@router.post("/containers/{container_id}/status", response_model=ContainerOut)
def update_status(container_id: int, body: CustomsStatusIn,
                  db: Session = Depends(get_db), user: User = customs_side):
    """Zmiana statusu odprawy (obie strony). Powiadamiana jest druga strona."""
    container = get_container_checked(db, container_id, user)
    check_customs_status_change(container.customs_status, body.customs_status, user,
                                body.customs_note)
    prev_customs = container.customs_status
    changes: dict = {"customs_status": body.customs_status}
    if body.customs_note:
        changes["customs_note"] = body.customs_note
    if body.customs_date is not None:
        changes["customs_date"] = body.customs_date
    elif body.customs_status == CustomsStatus.REWIZJA:   # spec §2: rewizja z datą — domyślnie dziś
        changes["customs_date"] = today_pl()
    if body.customs_t1 is not None:
        changes["customs_t1"] = body.customs_t1
    record_changes(db, container, changes, user, note="zmiana statusu odprawy")
    sync_status_from_customs(db, container, user)   # status kontenera z odprawy (2026-09-28)
    warning = (missing_docs_warning(db, container, user, body.customs_status.value)
               if body.customs_status != prev_customs and body.customs_status in WARN_CUSTOMS else None)
    # druga strona: gdy zmienia agencja → informujemy naszych; gdy nasi → informujemy agencję
    if user.role == Role.customs:
        recipients = company_watchers(db, container.company_id)
    else:
        recipients = customs_agency_users(db, container.customs_agency_id)
    notify(db, recipients, kind="customs",
           title=f"Odprawa {container.container_no}: {_status_label(body.customs_status)}",
           body=body.customs_note, container_id=container.id, exclude_user_id=user.id)
    db.commit()
    out = to_out(get_container_checked(db, container_id, user), user)
    out.docs_warning = warning   # decyzja 9: ostrzeżenie, nie blokada
    return out

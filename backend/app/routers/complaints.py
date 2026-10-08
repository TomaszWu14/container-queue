"""Moduł reklamacyjny: zgłoszenia problemów na dostawie i formalne reklamacje.

- każda dostawa (kontener) może mieć zgłoszenia/reklamacje ze zdjęciami (aparat/plik),
- lista problemów definiowana w panelu admina (ProblemType),
- „zgłoś problem" powiadamia magazyniera (in-app + e-mail + Teams),
- reklamacja: unikalny numer, wysyłka do spedycji/ubezpieczyciela, licznik czasu
  z przypomnieniami (progi dni z ustawień),
- archiwum (zamknięte reklamacje).
"""
import datetime
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..audit import record, record_changes, record_created
from ..config import settings as app_config
from ..database import get_db
from ..deps import (
    AdminOnly as admin_only,
)
from ..deps import (
    Editors as editors,
)
from ..deps import (
    Viewer as viewer,
)
from ..deps import (
    WarehouseOrEditors as reporters,
)
from ..deps import (
    get_scoped,
    scope_containers,
)
from ..models import (
    Complaint,
    ComplaintKind,
    ComplaintPhoto,
    ComplaintProblem,
    ComplaintStatus,
    Container,
    ProblemType,
    Role,
    User,
    utcnow,
)
from ..notifications import (
    forwarder_users,
    notify,
    send_html_email,
    warehouse_users,
)
from ..schemas import (
    ComplaintCostRow,
    ComplaintCreate,
    ComplaintDetailOut,
    ComplaintOut,
    ComplaintPhotoOut,
    ComplaintSendIn,
    ComplaintStatsOut,
    ComplaintStatsRow,
    ComplaintStatusIn,
    ComplaintUpdate,
    ProblemTypeIn,
    ProblemTypeOut,
    SettingsIn,
    SettingsOut,
)
from .complaints_common import (  # noqa: F401 — re-eksport: publiczne ścieżki importu
    _LOAD,
    COST_ROLES,
    SETTINGS_DEFAULTS,
    _looks_like_image,
    _problem_lines,
    _timeline_lines,
    complaint_deadline,
    complaint_to_out,
    deadline_days_for,
    get_complaint_checked,
    get_setting,
    next_complaint_number,
    set_setting,
)
from .containers_common import hidden_fields
from .complaints_jobs import (  # noqa: F401 — re-eksport (app/jobs.py)
    check_complaint_auto_drafts,
    check_complaint_reminders,
)
from .complaints_letters import _LETTER_L10N, _RECIPIENT_LABELS, _complaint_email_html  # noqa: F401
from .complaints_letters import router as letters_router
from .forwarding import commit_with_file, read_upload_capped, safe_filename, uploads_dir

router = APIRouter(prefix="/api", tags=["reklamacje"])


# --- ustawienia (panel admina) ---

@router.get("/settings", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db), user: User = admin_only):
    return SettingsOut(**{k: get_setting(db, k) for k in SETTINGS_DEFAULTS})


@router.put("/settings", response_model=SettingsOut)
def write_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = admin_only):
    for key in SETTINGS_DEFAULTS:
        old, new = get_setting(db, key), str(getattr(body, key))
        if old != new:
            set_setting(db, key, new)
            record(db, entity_type="app_settings", entity_id=0, field=key, old_value=old,
                   new_value=new, user=user)
    db.commit()
    return SettingsOut(**{k: get_setting(db, k) for k in SETTINGS_DEFAULTS})


# --- słownik problemów ---

@router.get("/problem-types", response_model=list[ProblemTypeOut])
def list_problem_types(active_only: bool = False, db: Session = Depends(get_db),
                       user: User = viewer):
    query = select(ProblemType).order_by(ProblemType.sort_order, ProblemType.name)
    if active_only:
        query = query.where(ProblemType.is_active)
    return db.scalars(query).all()


@router.post("/problem-types", response_model=ProblemTypeOut, status_code=201)
def create_problem_type(body: ProblemTypeIn, db: Session = Depends(get_db), user: User = admin_only):
    if db.scalar(select(ProblemType).where(ProblemType.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki problem już istnieje.")
    problem = ProblemType(**body.model_dump())
    db.add(problem)
    record_created(db, problem, user)
    db.commit()
    return problem


@router.patch("/problem-types/{type_id}", response_model=ProblemTypeOut)
def update_problem_type(type_id: int, body: ProblemTypeIn,
                        db: Session = Depends(get_db), user: User = admin_only):
    problem = db.get(ProblemType, type_id)
    if not problem:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono problemu.")
    record_changes(db, problem, body.model_dump(exclude_unset=True), user)
    db.commit()
    return problem


# --- reklamacje ---

@router.get("/complaints", response_model=list[ComplaintOut])
def list_complaints(db: Session = Depends(get_db), user: User = viewer,
                    container_id: int | None = None,
                    status_filter: str | None = Query(default=None, alias="status"),
                    archived: bool | None = None):
    query = select(Complaint).options(*_LOAD).order_by(Complaint.created_at.desc())
    # zakres: tylko reklamacje kontenerów widocznych dla użytkownika — podzapytanie
    # (bez materializowania wszystkich kontenerów; poprawne też przy pustym zakresie)
    query = query.where(Complaint.container_id.in_(
        scope_containers(select(Container.id), user)))
    if container_id is not None:
        query = query.where(Complaint.container_id == container_id)
    if status_filter:
        try:
            query = query.where(Complaint.status == ComplaintStatus(status_filter))
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Nieprawidłowy status reklamacji.") from None
    if archived is True:
        query = query.where(Complaint.status == ComplaintStatus.ZAMKNIETA)
    elif archived is False:
        query = query.where(Complaint.status != ComplaintStatus.ZAMKNIETA)
    return [complaint_to_out(c, user) for c in db.scalars(query).all()]


@router.post("/complaints", response_model=ComplaintDetailOut, status_code=201)
def create_complaint(body: ComplaintCreate, db: Session = Depends(get_db), user: User = viewer):
    # Q67: reklamację może zgłosić każdy z dostępem do kontenera (dostęp egzekwuje
    # check_container_access poniżej — spedytor tylko własne, magazyn tylko swój magazyn)
    container = get_scoped(db, Container, body.container_id, user,
                           options=(selectinload(Container.warehouse),))
    try:
        kind = ComplaintKind(body.kind)
    except ValueError:
        kind = ComplaintKind.PROBLEM
    prefix = get_setting(db, "complaint_prefix") or "REK"
    complaint = Complaint(
        number=next_complaint_number(db, container, prefix), kind=kind,
        container_id=container.id, company_id=container.company_id,
        description=body.description, driver_note=body.driver_note,
        created_by_id=user.id)
    db.add(complaint)
    try:
        db.flush()   # unikalny number — równoległy create → 409, nie 500
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Konflikt numeracji reklamacji — spróbuj ponownie.") from None
    for pid in body.problem_type_ids:
        if db.get(ProblemType, pid):
            db.add(ComplaintProblem(complaint_id=complaint.id, problem_type_id=pid))
    record(db, entity_type="complaints", entity_id=complaint.id, field="status",
           old_value=None, new_value=complaint.status.value, user=user,
           note=f"utworzenie {complaint.number}")
    db.flush()
    if body.report_to_warehouse:
        _report_to_warehouse(db, complaint, container, user)
    # Q72: reklamacja dotycząca kontenera spedycji → powiadomienie do tej spedycji
    if container.forwarder_id and (not user.role == Role.forwarder
                                   or user.forwarder_id != container.forwarder_id):
        notify(db, forwarder_users(db, container.forwarder_id), kind="complaint",
               title=f"Reklamacja: {container.container_no}",
               body=f"Zgłoszono reklamację/problem ({complaint.number}) dotyczącą Twojej "
                    f"dostawy {container.container_no}.", container_id=container.id)
    db.commit()
    return complaint_to_out(get_complaint_checked(db, complaint.id, user), user, detail=True)


@router.get("/complaints/stats", response_model=ComplaintStatsOut)
def complaint_stats(months: int = Query(default=12, ge=1, le=60),
                    db: Session = Depends(get_db), user: User = viewer):
    """Rejestr szkód (W11 #68/#71): % kontenerów z reklamacją per dostawca i armator
    (ostatnie N mies. po dacie utworzenia kontenera) + suma kosztów reklamacji."""
    cutoff = utcnow() - datetime.timedelta(days=months * 30)
    containers = db.scalars(scope_containers(
        select(Container).options(selectinload(Container.supplier),
                                  selectinload(Container.carrier))
        .where(Container.created_at >= cutoff), user)).all()
    ids = [c.id for c in containers]
    complained = set(db.scalars(select(Complaint.container_id).where(
        Complaint.container_id.in_(ids)))) if ids else set()

    def rows(key) -> list[ComplaintStatsRow]:
        agg: dict[str, list[int]] = {}
        for c in containers:
            name = key(c)
            total, bad = agg.setdefault(name, [0, 0])
            agg[name][0] = total + 1
            agg[name][1] = bad + (1 if c.id in complained else 0)
        out = [ComplaintStatsRow(name=n, containers=t, with_complaint=b,
                                 pct=round(100 * b / t, 1) if t else 0.0)
               for n, (t, b) in agg.items()]
        out.sort(key=lambda r: (-r.with_complaint, -r.containers, r.name))
        return out

    # koszty: reklamacje kontenerów w zakresie użytkownika, utworzone w oknie
    complaints = db.scalars(select(Complaint).where(
        Complaint.container_id.in_(ids),
        Complaint.created_at >= cutoff)).all() if ids else []
    costs: dict[str, list[float]] = {}
    for cp in complaints:
        cur = (cp.claim_currency or "PLN").upper()
        claim, rec = costs.setdefault(cur, [0.0, 0.0])
        costs[cur][0] = claim + float(cp.claim_amount or 0)
        costs[cur][1] = rec + float(cp.recovered_amount or 0)
    cost_rows = [ComplaintCostRow(
        currency=cur, claim=round(claim, 2), recovered=round(rec, 2),
        recovery_pct=round(100 * rec / claim, 1) if claim else 0.0)
        for cur, (claim, rec) in sorted(costs.items()) if claim or rec]
    return ComplaintStatsOut(
        months=months,
        # dostawca ukryty dla roli (hidden_fields) — bez rozbicia per dostawca
        suppliers=[] if "supplier_name" in hidden_fields(user) else rows(
            lambda c: c.supplier.name if c.supplier else "—"),
        carriers=rows(lambda c: c.carrier.name if c.carrier
                      else (c.vessel or "—")),
        costs=cost_rows if user.role in COST_ROLES else [])


@router.get("/complaints/{complaint_id}", response_model=ComplaintDetailOut)
def get_complaint(complaint_id: int, db: Session = Depends(get_db), user: User = viewer):
    return complaint_to_out(get_complaint_checked(db, complaint_id, user), user, detail=True)


@router.patch("/complaints/{complaint_id}", response_model=ComplaintDetailOut)
def update_complaint(complaint_id: int, body: ComplaintUpdate,
                     db: Session = Depends(get_db), user: User = reporters):
    complaint = get_complaint_checked(db, complaint_id, user)
    # kwoty zmienia tylko admin/logistyka — magazyn ich nawet nie widzi (complaint_to_out)
    if (body.model_fields_set & {"claim_amount", "recovered_amount", "claim_currency"}
            and user.role not in (Role.admin, Role.logistics)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kwoty reklamacji zmienia logistyka.")
    if body.description is not None:
        complaint.description = body.description
    if body.driver_note is not None:
        complaint.driver_note = body.driver_note
    if body.problem_type_ids is not None:
        db.query(ComplaintProblem).filter(
            ComplaintProblem.complaint_id == complaint.id).delete()
        for pid in body.problem_type_ids:
            if db.get(ProblemType, pid):
                db.add(ComplaintProblem(complaint_id=complaint.id, problem_type_id=pid))
    if body.recipient_type is not None:
        old = complaint.recipient_type
        complaint.recipient_type = body.recipient_type
        if old != body.recipient_type:
            record(db, entity_type="complaints", entity_id=complaint.id,
                   field="recipient_type", old_value=old or None,
                   new_value=body.recipient_type or None, user=user)
    # jawny null czyści kwotę (formularz wysyła null dla pustego pola); pominięte = bez zmian
    if "claim_amount" in body.model_fields_set:
        complaint.claim_amount = body.claim_amount
    if "recovered_amount" in body.model_fields_set:
        complaint.recovered_amount = body.recovered_amount
    if body.claim_currency is not None:
        complaint.claim_currency = body.claim_currency.upper()
    db.commit()
    return complaint_to_out(get_complaint_checked(db, complaint_id, user), user, detail=True)


def _report_to_warehouse(db: Session, complaint: Complaint, container: Container,
                         user: User) -> None:
    """Zgłoszenie problemu do magazyniera: in-app + e-mail + Teams."""
    recipients = warehouse_users(db, container.company_id, container.warehouse_id)
    body = (f"Dostawa {container.container_no} ({complaint.number})\n"
            f"Problemy: {_problem_lines(complaint)}\n"
            f"Opis: {complaint.description or '—'}")
    notify(db, recipients, kind="complaint",
           title=f"Zgłoszenie problemu: {container.container_no}",
           body=body, container_id=container.id, exclude_user_id=user.id)
    if complaint.status == ComplaintStatus.NOWA:
        complaint.status = ComplaintStatus.ZGLOSZONA
        complaint.reported_at = utcnow()
        record(db, entity_type="complaints", entity_id=complaint.id, field="status",
               old_value=ComplaintStatus.NOWA.value, new_value=complaint.status.value,
               user=user, note="zgłoszono do magazynu")


@router.post("/complaints/{complaint_id}/report", response_model=ComplaintDetailOut)
def report_complaint(complaint_id: int, db: Session = Depends(get_db), user: User = reporters):
    complaint = get_complaint_checked(db, complaint_id, user)
    _report_to_warehouse(db, complaint, complaint.container, user)
    db.commit()
    return complaint_to_out(get_complaint_checked(db, complaint_id, user), user, detail=True)


# --- zdjęcia (aparat / plik) ---

@router.post("/complaints/{complaint_id}/photos", response_model=ComplaintPhotoOut,
             status_code=201)
def upload_photo(complaint_id: int, file: UploadFile, caption: str = "",
                       db: Session = Depends(get_db), user: User = reporters):
    complaint = get_complaint_checked(db, complaint_id, user)
    content = read_upload_capped(file, app_config.max_upload_mb, "Zdjęcie")
    # typ z rzeczywistej zawartości, nie z nagłówka klienta (który da się sfałszować)
    if not _looks_like_image(content[:16]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Dozwolone są tylko zdjęcia (JPG/PNG/WEBP/HEIC/GIF).")
    safe = safe_filename(file.filename, "foto")
    stored = f"rek{complaint.id}_{secrets.token_hex(8)}_{safe}"
    photo = ComplaintPhoto(
        complaint_id=complaint.id, filename=safe,
        stored_name=stored, content_type=file.content_type or "", size=len(content),
        caption=caption.strip()[:300], uploaded_by_id=user.id)
    db.add(photo)
    commit_with_file(db, uploads_dir() / stored, content)
    return ComplaintPhotoOut.model_validate(photo)


@router.get("/complaint-photos/{photo_id}/download")
def download_photo(photo_id: int, db: Session = Depends(get_db), user: User = viewer):
    photo = db.get(ComplaintPhoto, photo_id)
    if not photo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono zdjęcia.")
    get_complaint_checked(db, photo.complaint_id, user)
    path = uploads_dir() / photo.stored_name
    if not path.is_file():
        raise HTTPException(status.HTTP_410_GONE, "Plik usunięty z dysku.")
    # nie ufamy Content-Type z uploadu — wyświetlamy tylko bezpieczne typy obrazów
    safe = photo.content_type if photo.content_type in (
        "image/jpeg", "image/png", "image/webp", "image/gif") else "application/octet-stream"
    return FileResponse(path, filename=photo.filename, media_type=safe)


# --- wysyłka reklamacji do spedycji / ubezpieczyciela ---

@router.post("/complaints/{complaint_id}/send", response_model=ComplaintDetailOut)
def send_complaint(complaint_id: int, body: ComplaintSendIn,
                   db: Session = Depends(get_db), user: User = editors):
    if not app_config.smtp_host:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "SMTP nie jest skonfigurowany (SMTP_HOST).")
    complaint = get_complaint_checked(db, complaint_id, user)
    if complaint.status == ComplaintStatus.ZAMKNIETA:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Reklamacja jest zamknięta — otwórz ją, zanim wyślesz ponownie.")
    subject = f"Reklamacja {complaint.number} — {complaint.container.container_no if complaint.container else ''}"
    try:
        send_html_email([body.target_email], subject,
                        _complaint_email_html(complaint, body.message),
                        reply_to=user.email or app_config.smtp_from)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("Błąd wysyłki reklamacji: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Nie udało się wysłać wiadomości — sprawdź konfigurację SMTP.") from exc
    complaint.status = ComplaintStatus.WYSLANA
    complaint.sent_at = utcnow()
    complaint.sent_target = f"{body.target_label} <{body.target_email}>".strip()
    complaint.reminders_sent = ""  # licznik czasu startuje od wysyłki
    record(db, entity_type="complaints", entity_id=complaint.id, field="status",
           old_value=None, new_value=complaint.status.value, user=user,
           note=f"wysłano do {complaint.sent_target}")
    db.commit()
    return complaint_to_out(get_complaint_checked(db, complaint_id, user), user, detail=True)


@router.post("/complaints/{complaint_id}/status", response_model=ComplaintDetailOut)
def change_complaint_status(complaint_id: int, body: ComplaintStatusIn,
                            db: Session = Depends(get_db), user: User = editors):
    complaint = get_complaint_checked(db, complaint_id, user)
    try:
        new_status = ComplaintStatus(body.status)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nieprawidłowy status.") from None
    old = complaint.status.value
    complaint.status = new_status
    if new_status == ComplaintStatus.ODPOWIEDZ:
        complaint.response_at = utcnow()
    if new_status == ComplaintStatus.ZAMKNIETA:
        complaint.closed_at = utcnow()
    else:
        complaint.closed_at = None  # wyjście z archiwum czyści datę zamknięcia (spójny wiek)
    record(db, entity_type="complaints", entity_id=complaint.id, field="status",
           old_value=old, new_value=new_status.value, user=user, note=body.note)
    db.commit()
    return complaint_to_out(get_complaint_checked(db, complaint_id, user), user, detail=True)


# --- szablon pisma (W11 #70) — complaints_letters.py ---
router.include_router(letters_router)

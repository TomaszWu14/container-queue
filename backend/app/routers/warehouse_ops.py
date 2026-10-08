"""Operacje magazynowe: kolejka bramy (check-in ochrony), pomiar czasu rozładunku,
zdjęcia z rozładunku (+ reklamacja z prefillu) i predykcja obsady.

Izolacja per zasób przez deps (scope_containers / get_container_checked) —
zero własnych reguł w tym routerze.
"""
from ..models import pl_midnight_utc, today_pl
import datetime
import math
import pathlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record
from ..config import settings
from ..database import get_db
from ..deps import StaffReaders as staff
from ..deps import Viewer as viewer
from ..deps import WarehouseOrEditors as warehouse_or_editors
from ..deps import scope_company, scope_containers
from ..models import (
    AuditLog,
    Complaint,
    ComplaintPhoto,
    Container,
    PalletCallLine,
    PalletCallStatus,
    PalletCall,
    UnloadPhoto,
    User,
    utcnow,
)
from ..notifications import company_watchers, notify, warehouse_users
from ..app_settings import get_setting
from .complaints import _looks_like_image, next_complaint_number
from .containers import get_container_checked
from .forwarding import commit_with_file, read_upload_capped, safe_filename, uploads_dir

router = APIRouter(prefix="/api", tags=["magazyn"])


# --- #60 kolejka bramy ---

def _today_audit_map(db: Session, container_ids: list[int], field: str,
                     since: datetime.datetime) -> dict[int, str]:
    """{container_id: created_at ISO} ostatniego wpisu audytu danego pola od `since`."""
    if not container_ids:
        return {}
    rows = db.execute(
        select(AuditLog.entity_id, func.max(AuditLog.created_at))
        .where(AuditLog.entity_type == "containers",
               AuditLog.entity_id.in_(container_ids),
               AuditLog.field == field,
               AuditLog.created_at >= since)
        .group_by(AuditLog.entity_id)).all()
    return {cid: at.isoformat() for cid, at in rows}


@router.get("/gate")
def gate_queue(db: Session = Depends(get_db), user: User = warehouse_or_editors,
               warehouse_id: int | None = None):
    """Dzisiejsze spodziewane auta: kontener, nr rej., status przyjazdu/check-in."""
    today = today_pl()
    query = scope_containers(
        select(Container).where(Container.notify_date == today,
                                Container.status.not_in(Container.FINISHED))
        .order_by(Container.id), user)
    if warehouse_id is not None:
        query = query.where(Container.warehouse_id == warehouse_id)
    containers = db.scalars(query).all()
    ids = [c.id for c in containers]
    day_start = pl_midnight_utc(today)
    arrived = _today_audit_map(db, ids, "driver-arrived", day_start)
    checked_in = _today_audit_map(db, ids, "gate-checkin", day_start)
    return {
        "day": today.isoformat(),
        "items": [{
            "id": c.id,
            "container_no": c.container_no,
            "truck_no": c.truck_no,
            "trailer_no": c.trailer_no,
            "driver_name": c.driver_name,
            "warehouse_id": c.warehouse_id,
            "warehouse": c.warehouse.name if c.warehouse else "",
            "notify_date": c.notify_date.isoformat() if c.notify_date else None,
            "eta": c.eta.isoformat() if c.eta else None,
            "status": c.status.value,
            "driver_arrived_at": arrived.get(c.id),
            "checked_in_at": checked_in.get(c.id),
            "ramp_stage": c.ramp_stage,
        } for c in containers],
    }


class RampStageIn(BaseModel):
    stage: str | None = None


@router.post("/containers/{container_id}/ramp-stage")
def set_ramp_stage(container_id: int, body: RampStageIn, db: Session = Depends(get_db),
                   user: User = warehouse_or_editors):
    """D9: etap rampy ustawia magazyn (drugi wymiar — ContainerStatus bez zmian)."""
    if body.stage is not None and body.stage not in Container.RAMP_STAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nieznany etap rampy.")
    container = get_container_checked(db, container_id, user)
    if container.ramp_stage != body.stage:
        record(db, entity_type="containers", entity_id=container.id, field="ramp_stage",
               old_value=container.ramp_stage, new_value=body.stage, user=user)
        container.ramp_stage = body.stage
        db.commit()
    return {"ramp_stage": container.ramp_stage}


@router.post("/gate/{container_id}/checkin")
def gate_checkin(container_id: int, db: Session = Depends(get_db),
                 user: User = warehouse_or_editors):
    """Check-in ochrony „Przyjechał": audyt + dzwonek do magazynu. Idempotentny w dniu."""
    container = get_container_checked(db, container_id, user)
    day_start = pl_midnight_utc()
    already = db.scalar(select(AuditLog).where(
        AuditLog.entity_type == "containers",
        AuditLog.entity_id == container.id,
        AuditLog.field == "gate-checkin",
        AuditLog.created_at >= day_start))
    if already:
        return {"status": "ok", "already": True}
    record(db, entity_type="containers", entity_id=container.id, field="gate-checkin",
           old_value=None, new_value="przyjechał", user=user, note="kolejka bramy")
    if not container.ramp_stage:   # D9 jak „Przyjechałem” kierowcy: przyjazd = podstawiony
        record(db, entity_type="containers", entity_id=container.id, field="ramp_stage",
               old_value=None, new_value="PODSTAWIONY", user=user, note="przyjazd na bramie")
        container.ramp_stage = "PODSTAWIONY"
    # logistyka też wie o przyjeździe (dotąd tylko ze strony kierowcy — link znika, 2026-10-07)
    notify(db, company_watchers(db, container.company_id)
           + warehouse_users(db, container.company_id, container.warehouse_id),
           kind="gate", title=f"Brama: auto przyjechało — {container.container_no}",
           body=f"Nr rej.: {container.truck_no or '—'} / {container.trailer_no or '—'}",
           container_id=container.id, exclude_user_id=user.id)
    db.commit()
    return {"status": "ok", "already": False}


# --- #61 pomiar czasu rozładunku ---

@router.post("/containers/{container_id}/unload/start")
def unload_start(container_id: int, db: Session = Depends(get_db),
                 user: User = warehouse_or_editors):
    container = get_container_checked(db, container_id, user)
    if container.unload_started_at and not container.unload_finished_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Rozładunek już trwa.")
    container.unload_started_at = utcnow()
    container.unload_finished_at = None   # restart pomiaru = nowy pomiar
    record(db, entity_type="containers", entity_id=container.id, field="unload_started_at",
           old_value=None, new_value=container.unload_started_at.isoformat(),
           user=user, note="start rozładunku")
    db.commit()
    return {"unload_started_at": container.unload_started_at.isoformat()}


@router.post("/containers/{container_id}/unload/stop")
def unload_stop(container_id: int, db: Session = Depends(get_db),
                user: User = warehouse_or_editors):
    container = get_container_checked(db, container_id, user)
    if not container.unload_started_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Rozładunek nie został rozpoczęty.")
    if container.unload_finished_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Rozładunek już zakończony.")
    container.unload_finished_at = utcnow()
    minutes = round((container.unload_finished_at
                     - container.unload_started_at).total_seconds() / 60)
    record(db, entity_type="containers", entity_id=container.id, field="unload_finished_at",
           old_value=None, new_value=container.unload_finished_at.isoformat(),
           user=user, note=f"stop rozładunku ({minutes} min)")
    db.commit()
    return {"unload_finished_at": container.unload_finished_at.isoformat(),
            "duration_minutes": minutes}


# --- #64 zdjęcia z rozładunku ---

def _photo_out(p: UnloadPhoto) -> dict:
    return {"id": p.id, "container_id": p.container_id, "filename": p.filename,
            "caption": p.caption, "size": p.size,
            "created_at": p.created_at.isoformat()}


@router.get("/containers/{container_id}/unload-photos")
def list_unload_photos(container_id: int, db: Session = Depends(get_db),
                       user: User = viewer):
    get_container_checked(db, container_id, user)
    rows = db.scalars(select(UnloadPhoto)
                      .where(UnloadPhoto.container_id == container_id)
                      .order_by(UnloadPhoto.id)).all()
    return [_photo_out(p) for p in rows]


@router.post("/containers/{container_id}/unload-photos", status_code=201)
def upload_unload_photo(container_id: int, file: UploadFile, caption: str = "",
                              db: Session = Depends(get_db),
                              user: User = warehouse_or_editors):
    container = get_container_checked(db, container_id, user)
    content = read_upload_capped(file, settings.max_upload_mb, "Zdjęcie")
    if not _looks_like_image(content[:16]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Dozwolone są tylko zdjęcia (JPG/PNG/WEBP/HEIC/GIF).")
    safe = safe_filename(file.filename, "foto")
    stored = f"unl{container.id}_{secrets.token_hex(8)}_{safe}"
    photo = UnloadPhoto(
        container_id=container.id, filename=safe,
        stored_name=stored, content_type=file.content_type or "", size=len(content),
        caption=caption.strip()[:300], uploaded_by_id=user.id)
    db.add(photo)
    commit_with_file(db, uploads_dir() / stored, content)
    return _photo_out(photo)


@router.get("/unload-photos/{photo_id}/download")
def download_unload_photo(photo_id: int, db: Session = Depends(get_db),
                          user: User = viewer):
    photo = db.get(UnloadPhoto, photo_id)
    if not photo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono zdjęcia.")
    get_container_checked(db, photo.container_id, user)
    path = uploads_dir() / photo.stored_name
    if not path.is_file():
        raise HTTPException(status.HTTP_410_GONE, "Plik usunięty z dysku.")
    safe = photo.content_type if photo.content_type in (
        "image/jpeg", "image/png", "image/webp", "image/gif") else "application/octet-stream"
    return FileResponse(path, filename=photo.filename, media_type=safe)


class PhotoComplaintIn(BaseModel):
    description: str = Field(default="", max_length=2000)


@router.post("/unload-photos/{photo_id}/complaint", status_code=201)
def complaint_from_photo(photo_id: int, body: PhotoComplaintIn,
                         db: Session = Depends(get_db),
                         user: User = warehouse_or_editors):
    """Prefill draftu reklamacji z kontenerem i podpiętym zdjęciem z rozładunku."""
    photo = db.get(UnloadPhoto, photo_id)
    if not photo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono zdjęcia.")
    container = get_container_checked(db, photo.container_id, user)
    prefix = get_setting(db, "complaint_prefix") or "REK"
    complaint = Complaint(
        number=next_complaint_number(db, container, prefix),
        container_id=container.id, company_id=container.company_id,
        description=body.description
        or f"Zgłoszenie ze zdjęcia z rozładunku {container.container_no}.",
        created_by_id=user.id)
    db.add(complaint)
    db.flush()
    # kopia pliku pod nową nazwą (stored_name jest unikalny w obu tabelach)
    src = uploads_dir() / photo.stored_name
    stored = f"rek{complaint.id}_{secrets.token_hex(8)}_{pathlib.Path(photo.filename).name}"
    db.add(ComplaintPhoto(
        complaint_id=complaint.id, filename=photo.filename, stored_name=stored,
        content_type=photo.content_type, size=photo.size,
        caption=photo.caption, uploaded_by_id=user.id))
    record(db, entity_type="complaints", entity_id=complaint.id, field="status",
           old_value=None, new_value=complaint.status.value, user=user,
           note=f"utworzenie {complaint.number} ze zdjęcia rozładunku")
    db.commit()
    if src.is_file():
        (uploads_dir() / stored).write_bytes(src.read_bytes())
    return {"complaint_id": complaint.id, "number": complaint.number}


# --- #66 predykcja obsady ---

@router.get("/warehouse/staffing")
def staffing_forecast(db: Session = Depends(get_db), user: User = staff):
    """Palety do rozładunku jutro/pojutrze ÷ palety/os./zmianę → sugerowana obsada."""
    per_person = settings.staffing_pallets_per_person
    today = today_pl()
    days = [today + datetime.timedelta(days=1), today + datetime.timedelta(days=2)]
    out = []
    for day in days:
        rows = db.scalars(scope_containers(
            select(Container).where(Container.notify_date == day,
                                    Container.status.not_in(Container.FINISHED)),
            user)).all()
        container_pallets = sum(c.pallet_count or 0 for c in rows)
        # palety z wywołań DLT (linie z datą dostawy tego dnia, wywołania w drodze)
        call_q = (select(func.coalesce(func.sum(PalletCallLine.ilosc_pal), 0))
                  .join(PalletCall, PalletCall.id == PalletCallLine.pallet_call_id)
                  .where(PalletCallLine.data_dostawy == day,
                         PalletCall.status.in_((PalletCallStatus.sent,
                                                PalletCallStatus.confirmed))))
        call_q = scope_company(call_q, PalletCall.company_id, user)
        call_pallets = float(db.scalar(call_q) or 0)
        total = container_pallets + call_pallets
        out.append({
            "day": day.isoformat(),
            "containers": len(rows),
            "container_pallets": container_pallets,
            "call_pallets": round(call_pallets),
            "total_pallets": round(total),
            "suggested_people": math.ceil(total / per_person) if total else 0,
        })
    return {"pallets_per_person": per_person, "days": out}


class GateDelayIn(BaseModel):
    eta_time: str = Field(max_length=16)


@router.post("/gate/{container_id}/delay")
def gate_delay(container_id: int, body: GateDelayIn, db: Session = Depends(get_db),
               user: User = warehouse_or_editors):
    """Kierowca zadzwonił, że się spóźni — logistyka/magazyn wpisuje nową godzinę (zamiast
    strony kierowcy z linku; te same powiadomienia i okno 30 min)."""
    from .driver import report_delay
    report_delay(db, get_container_checked(db, container_id, user), body.eta_time, user,
                 "wpisane w aplikacji")
    return {"status": "ok"}

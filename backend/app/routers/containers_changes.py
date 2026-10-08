"""Dziennik zmian z audytu (digest, feed dnia) oraz obserwacja i flaga „specjalny"."""
import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..audit import record
from ..database import get_db
from ..deps import Editors as editors
from ..deps import ViewerOrSales as viewer_or_sales
from ..deps import scope_containers
from ..models import Container, Role, User, utcnow
from ..schemas import SpecialIn, WatchIn
from .containers_common import get_container_checked, hidden_fields

# sub-router bez prefiksu — podpinany w routers/containers.py (prefiks /api, tag kolejka)
router = APIRouter()


_FILE_FIELDS = frozenset({"attachment_upload", "attachment_delete", "attachment_replace"})


def _file_fields_hidden(user: User) -> frozenset[str]:
    """Wpisy o plikach niosą nazwy dokumentów (SAD, faktury) — spedytor i magazyn ich nie widzą."""
    return _FILE_FIELDS if user.role in (Role.forwarder, Role.warehouse) else frozenset()


# --- dziennik zmian „od wczoraj" (inspiracja Windward) ---

@router.get("/changes/digest")
def changes_digest(db: Session = Depends(get_db), user: User = viewer_or_sales,
                   hours: int = Query(default=24, le=168)):
    """Co się zmieniło w kontenerach w ostatnich N godzinach — z audytu.

    Kubełki: nowe kontenery (status z None), zmiany statusów, zmiany ETA,
    pozostałe pola. Tylko kontenery w zakresie usera."""
    from ..models import AuditLog
    since = utcnow() - datetime.timedelta(hours=hours)
    # scope PRZED capem (fix review): przy ruchliwym audycie wąski user dostawał
    # pusty digest, bo 1000 najnowszych wpisów należało do cudzych spółek
    scoped_ids = scope_containers(select(Container.id), user).scalar_subquery()
    logs = db.scalars(select(AuditLog)
                      .where(AuditLog.entity_type == "containers",
                             AuditLog.created_at >= since,
                             AuditLog.entity_id.in_(scoped_ids))
                      .order_by(AuditLog.created_at.desc())
                      .limit(1000)).all()
    ids = {log.entity_id for log in logs}
    if not ids:
        return {"since_hours": hours, "created": [], "status": [], "eta": [], "other": []}
    visible = {c.id: c.container_no for c in db.scalars(
        select(Container).where(Container.id.in_(ids))).all()}

    # pola maskowane dla roli pomijamy jak w historii kontenera (np. odprawa dla spedytora)
    hidden = hidden_fields(user) | _file_fields_hidden(user)
    created, status_ch, eta_ch, other = [], [], [], []
    for log in logs:
        no = visible.get(log.entity_id)
        if no is None or log.field in hidden:
            continue
        entry = {"container_id": log.entity_id, "container_no": no,
                 "field": log.field, "old": log.old_value, "new": log.new_value,
                 "at": log.created_at, "note": log.note}
        if log.field == "status" and log.old_value is None:
            created.append(entry)
        elif log.field == "status":
            status_ch.append(entry)
        elif log.field == "eta":
            eta_ch.append(entry)
        else:
            other.append(entry)
    cap = 30   # digest, nie pełny audyt — reszta w historii kontenera
    return {"since_hours": hours, "created": created[:cap], "status": status_ch[:cap],
            "eta": eta_ch[:cap], "other": other[:cap]}


# --- tablica zmian dnia (#30): feed z audytu z filtrami i paginacją ---

@router.get("/changes/feed")
def changes_feed(db: Session = Depends(get_db), user: User = editors,
                 company_id: int | None = None, warehouse_id: int | None = None,
                 entity_type: str = "", user_id: int | None = None,
                 page: int = Query(default=1, ge=1),
                 per_page: int = Query(default=50, ge=1, le=200)):
    """Dziennik zmian od początku dnia (czas PL) dla admin+logistyki.

    Filtr spółki/magazynu zawęża do encji kontenerowych (tylko one mają spółkę);
    logistyka bez view_all widzi wyłącznie kontenery swoich spółek."""
    from zoneinfo import ZoneInfo

    from ..models import AuditLog
    from ..security import can_view_all
    warsaw = ZoneInfo("Europe/Warsaw")
    local_now = utcnow().replace(tzinfo=datetime.UTC).astimezone(warsaw)
    since = (datetime.datetime.combine(local_now.date(), datetime.time.min, tzinfo=warsaw)
             .astimezone(datetime.UTC).replace(tzinfo=None))
    query = select(AuditLog).where(AuditLog.created_at >= since)
    if company_id or warehouse_id or not can_view_all(user):
        scoped = select(Container.id)
        if company_id:
            scoped = scoped.where(Container.company_id == company_id)
        if warehouse_id:
            scoped = scoped.where(Container.warehouse_id == warehouse_id)
        scoped = scope_containers(scoped, user).scalar_subquery()
        query = query.where(AuditLog.entity_type == "containers",
                            AuditLog.entity_id.in_(scoped))
    visible = query   # zakres użytkownika bez filtrów typu/autora — źródło słowników (ACL-002)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    logs = db.scalars(query.options(selectinload(AuditLog.user))
                      .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                      .offset((page - 1) * per_page).limit(per_page)).all()
    container_ids = {log.entity_id for log in logs if log.entity_type == "containers"}
    numbers = {c.id: c.container_no for c in db.scalars(
        select(Container).where(Container.id.in_(container_ids)))} if container_ids else {}
    entries = [{
        "id": log.id, "at": log.created_at, "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "container_no": numbers.get(log.entity_id) if log.entity_type == "containers" else None,
        "field": log.field, "old": log.old_value, "new": log.new_value,
        "note": log.note,
        "user_login": log.user.login if log.user else None,
        "user_name": (log.user.full_name or log.user.login) if log.user else "system",
    } for log in logs]
    # słowniki do filtrów: typy encji i userzy aktywni dzisiaj — tylko z WIDOCZNYCH wpisów;
    # z całego audytu logistyk spółki A dostawał loginy i nazwiska kont innych spółek (ACL-002)
    entity_types = list(db.scalars(visible.with_only_columns(AuditLog.entity_type).distinct()))
    actor_ids = set(db.scalars(visible.with_only_columns(AuditLog.user_id)
                               .where(AuditLog.user_id.is_not(None)).distinct()))
    actors = [{"id": u.id, "login": u.login, "full_name": u.full_name}
              for u in db.scalars(select(User).where(User.id.in_(actor_ids)))] \
        if actor_ids else []
    return {"total": total, "page": page, "per_page": per_page,
            "entries": entries, "entity_types": sorted(entity_types),
            "actors": sorted(actors, key=lambda a: a["login"])}
# --- „moje kontenery": gwiazdka per user ---

@router.get("/watch", response_model=list[int])
def watched_ids(db: Session = Depends(get_db), user: User = viewer_or_sales):
    from ..models import WatchedContainer
    return list(db.scalars(select(WatchedContainer.container_id)
                           .where(WatchedContainer.user_id == user.id)).all())


@router.get("/watch/reasons")
def watched_reasons(db: Session = Depends(get_db), user: User = viewer_or_sales) -> list[dict]:
    """Powody własnych obserwacji (tylko niepuste) — kolejka pokazuje je przy gwiazdce."""
    from ..models import WatchedContainer
    rows = db.execute(select(WatchedContainer.container_id, WatchedContainer.reason)
                      .where(WatchedContainer.user_id == user.id,
                             WatchedContainer.reason != "")).all()
    return [{"container_id": cid, "reason": reason} for cid, reason in rows]


@router.post("/containers/{container_id}/watch")
def toggle_watch(container_id: int, body: WatchIn | None = None,
                 db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Toggle gwiazdki — idempotentny (drugi POST zdejmuje obserwację).
    Body opcjonalne: przy dodaniu zapisuje powód; przy zdjęciu ignorowane."""
    from ..models import WatchedContainer
    get_container_checked(db, container_id, user)
    existing = db.scalar(select(WatchedContainer).where(
        WatchedContainer.user_id == user.id,
        WatchedContainer.container_id == container_id))
    if existing:
        db.delete(existing)
        watching = False
    else:
        db.add(WatchedContainer(user_id=user.id, container_id=container_id,
                                reason=(body.reason.strip() if body else ""),
                                created_at=utcnow()))
        watching = True
    db.commit()
    return {"watching": watching}


@router.post("/containers/{container_id}/special")
def toggle_special(container_id: int, body: SpecialIn | None = None,
                   db: Session = Depends(get_db), user: User = editors):
    """Flaga „specjalny" (wyróżnienie do śledzenia) — globalna, nie per-user jak gwiazdka;
    widoczna w kolejce, na mapie i w karcie statku. Body opcjonalne: gdy podane, ustawia
    stan + powód (dropdown) + komentarz; brak body = toggle (wstecznie kompatybilne)."""
    container = get_container_checked(db, container_id, user)
    old = container.is_special
    container.is_special = body.is_special if body else not old
    if container.is_special:
        if body:
            container.special_reason = body.reason
            container.special_note = body.note
    else:                                   # wyłączenie czyści powód i notatkę
        container.special_reason = None
        container.special_note = ""
    record(db, entity_type="containers", entity_id=container.id, field="is_special",
           old_value=old, new_value=container.is_special, user=user)
    db.commit()
    return {"is_special": container.is_special,
            "special_reason": container.special_reason,
            "special_note": container.special_note}

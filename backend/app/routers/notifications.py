"""Powiadomienia in-app: lista, licznik nieprzeczytanych, oznaczanie jako przeczytane;
feed Aktualności na Pulpicie (kategorie, ważność, wątki — spec 2026-10-01)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from ..audit import record
from ..database import get_db
from ..deps import AdminOnly as admin_only
from ..deps import ViewerOrSales as viewer_or_sales
from ..deps import scope_containers
from ..models import Container, Notification, NotificationRule, Role, User
from .. import notification_feed as feed
from ..notifications import NOTIFY_CHANNELS, NOTIFY_KINDS
from ..schemas import NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["powiadomienia"])


class RuleIn(BaseModel):
    kind: str
    role: str      # wartość Role albo '*' (Teams)
    channel: str   # bell / email / teams
    enabled: bool


@router.get("/rules")
def list_rules(db: Session = Depends(get_db), user: User = admin_only):
    """Matryca reguł: znane kindy/role/kanały + nadpisania (brak wpisu = włączone)."""
    rules = db.scalars(select(NotificationRule)).all()
    return {"kinds": NOTIFY_KINDS, "channels": list(NOTIFY_CHANNELS),
            "roles": [r.value for r in Role],
            "rules": [{"kind": r.kind, "role": r.role, "channel": r.channel,
                       "enabled": r.enabled} for r in rules]}


@router.put("/rules")
def save_rules(body: list[RuleIn], db: Session = Depends(get_db),
               user: User = admin_only):
    """Zapis matrycy: pełna wymiana nadpisań. Wpisy enabled=True (=domyślne)
    nie są przechowywane — tabela trzyma tylko wyjątki."""
    from fastapi import HTTPException
    valid_roles = {r.value for r in Role} | {"*"}
    for rule in body:
        if (rule.kind not in NOTIFY_KINDS or rule.channel not in NOTIFY_CHANNELS
                or rule.role not in valid_roles):
            raise HTTPException(422, f"Nieznana reguła: {rule.kind}/{rule.role}/{rule.channel}")
    old = sorted(f"{r.kind}/{r.role}/{r.channel}"
                 for r in db.scalars(select(NotificationRule)) if not r.enabled)
    db.query(NotificationRule).delete()
    for rule in body:
        if not rule.enabled:
            db.add(NotificationRule(kind=rule.kind, role=rule.role,
                                    channel=rule.channel, enabled=False))
    new = sorted({f"{r.kind}/{r.role}/{r.channel}" for r in body if not r.enabled})
    if old != new:  # matryca globalna — entity_id=0; wartości = wyłączone kind/rola/kanał
        record(db, entity_type=NotificationRule.__tablename__, entity_id=0, field="disabled",
               old_value=", ".join(old), new_value=", ".join(new), user=user,
               note="zmiana matrycy reguł powiadomień")
    db.commit()
    return {"ok": True}


@router.get("", response_model=list[NotificationOut])
def list_notifications(db: Session = Depends(get_db), user: User = viewer_or_sales,
                       unread_only: bool = False,
                       limit: int = Query(default=50, ge=1, le=1000)):
    query = (select(Notification).where(Notification.user_id == user.id)
             .order_by(Notification.created_at.desc(), Notification.id.desc())
             .limit(min(limit, 200)))
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    return db.scalars(query).all()


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = viewer_or_sales):
    count = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.is_read.is_(False)))
    return {"count": count or 0}


@router.post("/read")
def mark_read(db: Session = Depends(get_db), user: User = viewer_or_sales,
              notification_id: int | None = None):
    query = update(Notification).where(Notification.user_id == user.id)
    if notification_id is not None:
        query = query.where(Notification.id == notification_id)
    db.execute(query.values(is_read=True))
    db.commit()
    return {"ok": True}


@router.post("/unread")
def mark_unread(notification_id: int, db: Session = Depends(get_db), user: User = viewer_or_sales):
    """„Oznacz jako nieprzeczytaną” w panelu czytania Aktualności."""
    db.execute(update(Notification).where(Notification.user_id == user.id,
                                          Notification.id == notification_id).values(is_read=False))
    db.commit()
    return {"ok": True}


def _feed_items(db: Session, user: User, rows: list[Notification]) -> list[dict]:
    """Wiersze + kategoria, ważność, wątek i kontenery z treści (tylko w zakresie użytkownika —
    numer obcego kontenera zostaje zwykłym tekstem)."""
    numbers = {n.id: feed.container_numbers(n) for n in rows}
    wanted_no = {no for nos in numbers.values() for no in nos}
    wanted_id = {n.container_id for n in rows if n.container_id}
    found: list[Container] = []
    if wanted_no or wanted_id:
        try:
            found = list(db.scalars(scope_containers(select(Container).where(or_(
                Container.container_no.in_(sorted(wanted_no)), Container.id.in_(sorted(wanted_id)))), user)))
        except HTTPException:   # konto bez zakresu kontenerów (np. spedytor bez firmy)
            found = []
    by_no = {c.container_no: c for c in found if c.container_no}
    by_id = {c.id: c for c in found}
    out = []
    for n in rows:
        refs = [by_id[n.container_id]] if n.container_id in by_id else []
        refs += [by_no[no] for no in numbers[n.id] if no in by_no and by_no[no] not in refs]
        out.append({**NotificationOut.model_validate(n).model_dump(),
                    "category": feed.category(n.kind), "priority": feed.priority(n.kind),
                    "thread_key": feed.thread_key(n),
                    "containers": [{"id": c.id, "container_no": c.container_no} for c in refs]})
    return out


@router.get("/feed")
def notification_feed(db: Session = Depends(get_db), user: User = viewer_or_sales,
                      category: str | None = None, unread_only: bool = False,
                      status: Literal["all", "unread", "read"] = "all",
                      priority: Literal["urgent", "normal", "info"] | None = None,
                      q: str | None = Query(default=None, max_length=100),
                      before_id: int | None = None, limit: int = Query(default=50, ge=1, le=100)):
    """Aktualności: najnowsze pierwsze, po `limit` z „załaduj starsze” (before_id);
    `pinned` = pilne nieprzeczytane (tylko na pierwszej stronie)."""
    query = select(Notification).where(Notification.user_id == user.id)
    if category == "system":
        query = query.where(Notification.kind.not_in(feed.KNOWN_NON_SYSTEM))
    elif category in feed.CATEGORIES:
        query = query.where(Notification.kind.in_(feed.CATEGORIES[category]))
    if unread_only or status == "unread":
        query = query.where(Notification.is_read.is_(False))
    elif status == "read":
        query = query.where(Notification.is_read.is_(True))
    if priority == "urgent":
        query = query.where(Notification.kind.in_(feed.URGENT))
    elif priority == "info":
        query = query.where(Notification.kind.in_(feed.INFO))
    elif priority == "normal":
        query = query.where(Notification.kind.not_in(feed.URGENT | feed.INFO))
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.where(or_(Notification.title.ilike(like), Notification.body.ilike(like)))
    if before_id is not None:
        query = query.where(Notification.id < before_id)
    rows = list(db.scalars(query.order_by(Notification.id.desc()).limit(limit + 1)))
    pinned: list[Notification] = []
    if before_id is None:
        pinned = list(db.scalars(select(Notification).where(
            Notification.user_id == user.id, Notification.is_read.is_(False),
            Notification.kind.in_(feed.URGENT)).order_by(Notification.id.desc()).limit(20)))
    return {"items": _feed_items(db, user, rows[:limit]), "pinned": _feed_items(db, user, pinned),
            "has_more": len(rows) > limit}


@router.get("/{notification_id}/thread")
def notification_thread(notification_id: int, db: Session = Depends(get_db),
                        user: User = viewer_or_sales):
    """Oś zdarzeń wątku (ten sam kontener albo statek) — panel czytania."""
    n = db.scalar(select(Notification).where(Notification.id == notification_id,
                                             Notification.user_id == user.id))
    if n is None:
        raise HTTPException(404, "Nie znaleziono powiadomienia.")
    key = feed.thread_key(n)
    query = select(Notification).where(Notification.user_id == user.id)
    if key.startswith("c:"):
        query = query.where(Notification.container_id == n.container_id)
    elif key.startswith("v:"):
        query = query.where(Notification.title.like(f"Statek {feed.vessel_name(n.title)} %"))
    else:
        query = query.where(Notification.id == n.id)
    rows = list(db.scalars(query.order_by(Notification.id.desc()).limit(50)))
    return {"thread_key": key, "items": _feed_items(db, user, rows)}

"""Moduł spedytora: zlecenia transportowe (pełny obieg), wiadomości, pliki, agent celny.

Tu: zlecenia transportowe, odprawa, kierowca, e-mail z kolejką dnia, wiadomości.
Załączniki/OCR i helpery uploadu — forwarding_files.py; faktury transportowe BL —
forwarding_freight.py (oba dołączone do tego routera).
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..audit import record, record_changes
from ..config import settings
from ..database import get_db
from ..date_pl import date_pl
from ..deps import (
    Editors as editors,
)
from ..deps import (
    Viewer as viewer,
)
from ..deps import (
    get_company_by_code,
    get_scoped,
    scope_transport_orders,
)
from ..models import (
    Container,
    Forwarder,
    Message,
    Role,
    TransportOrder,
    TransportOrderStatus,
    User,
    Warehouse,
)
from ..notifications import (
    company_watchers,
    container_watchers,
    forwarder_users,
    notify,
    send_html_email,
    warehouse_users,
)
from ..schemas import (
    ContainerOut,
    CustomsUpdateIn,
    DriverIn,
    MessageIn,
    MessageOut,
    QueueEmailIn,
    TransportOrderIn,
    TransportOrderOut,
    TransportOrderStatusIn,
)
from ..security import require_roles
from . import forwarding_files, forwarding_freight
from .containers import get_container_checked, to_out
from .containers_common import check_customs_status_change, check_not_modified, sync_status_from_customs
from .forwarding_files import (  # noqa: F401 — re-eksport: publiczne importy z .forwarding
    allowed_extensions,
    commit_with_file,
    read_upload_capped,
    safe_filename,
    uploads_dir,
)
from .forwarding_freight import (  # noqa: F401
    FreightDecisionIn,
    FreightInvoiceContainerOut,
    FreightInvoiceOut,
)

router = APIRouter(prefix="/api", tags=["spedycja"])
logger = logging.getLogger(__name__)

# dozwolone przejścia obiegu zlecenia: kto może wykonać dany krok
ORDER_FLOW: dict[TransportOrderStatus, tuple[set[TransportOrderStatus], set[Role]]] = {
    # logistyka/admin mogą zaakceptować w imieniu spedytora (np. potwierdził telefonicznie) —
    # zawsze z notatką (decyzja 2026-09-28)
    TransportOrderStatus.ZAAKCEPTOWANE: ({TransportOrderStatus.WYSTAWIONE},
                                         {Role.forwarder, Role.logistics, Role.admin}),
    TransportOrderStatus.ODRZUCONE: ({TransportOrderStatus.WYSTAWIONE},
                                     {Role.forwarder}),
    TransportOrderStatus.W_REALIZACJI: ({TransportOrderStatus.ZAAKCEPTOWANE},
                                        {Role.forwarder}),
    TransportOrderStatus.WYKONANE: ({TransportOrderStatus.ZAAKCEPTOWANE,
                                     TransportOrderStatus.W_REALIZACJI},
                                    {Role.forwarder}),
    TransportOrderStatus.POTWIERDZONE: ({TransportOrderStatus.WYKONANE},
                                        {Role.admin, Role.logistics}),
}
# BIZ-008: korekty obiegu przez logistykę/admina — zawsze z powodem (w audycie i powiadomieniu
# spedytora): ponowne wystawienie po odrzuceniu (np. nowy termin) i cofnięcie „wykonane”
# klikniętego przez spedytora pomyłkowo. Spedytor tych kroków nie wykona.
ORDER_CORRECTIONS: dict[tuple[TransportOrderStatus, TransportOrderStatus], set[Role]] = {
    (TransportOrderStatus.ODRZUCONE, TransportOrderStatus.WYSTAWIONE): {Role.logistics, Role.admin},
    (TransportOrderStatus.WYKONANE, TransportOrderStatus.W_REALIZACJI): {Role.logistics, Role.admin},
}


def order_to_out(order: TransportOrder) -> TransportOrderOut:
    out = TransportOrderOut.model_validate(order)
    out.container_no = order.container.container_no if order.container else None
    out.forwarder_name = order.forwarder.name if order.forwarder else None
    out.created_by_login = order.created_by.login if order.created_by else None
    return out


def get_order_checked(db: Session, order_id: int, user: User) -> TransportOrder:
    return get_scoped(db, TransportOrder, order_id, user, options=(
        selectinload(TransportOrder.container),
        selectinload(TransportOrder.forwarder),
        selectinload(TransportOrder.created_by)))


# --- zlecenia transportowe ---

@router.get("/transport-orders", response_model=list[TransportOrderOut])
def list_transport_orders(db: Session = Depends(get_db), user: User = viewer,
                          status_filter: TransportOrderStatus | None = None,
                          container_id: int | None = None):
    query = scope_transport_orders(
        select(TransportOrder)
        .options(selectinload(TransportOrder.container),
                 selectinload(TransportOrder.forwarder),
                 selectinload(TransportOrder.created_by))
        .order_by(TransportOrder.created_at.desc()), user)
    if status_filter:
        query = query.where(TransportOrder.status == status_filter)
    if container_id:
        query = query.where(TransportOrder.container_id == container_id)
    return [order_to_out(o) for o in db.scalars(query).all()]


@router.get("/transport-orders/kpi")
def transport_orders_kpi(db: Session = Depends(get_db), user: User = viewer):
    """KPI spedycji (W9): zlecenia per spedytor, rozkład statusów, średni czas
    realizacji (pickup→delivery), % odrzuceń. Zakres wg roli (scope_transport_orders)."""
    stmt = scope_transport_orders(select(
        TransportOrder.status, TransportOrder.forwarder_id,
        TransportOrder.pickup_date, TransportOrder.delivery_date), user)
    rows = db.execute(stmt).all()

    by_status: dict[str, int] = {}
    by_forwarder: dict[int, int] = {}
    realization_days: list[int] = []
    for r in rows:
        by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
        by_forwarder[r.forwarder_id] = by_forwarder.get(r.forwarder_id, 0) + 1
        if r.pickup_date and r.delivery_date:
            realization_days.append((r.delivery_date - r.pickup_date).days)

    top = sorted(by_forwarder.items(), key=lambda kv: kv[1], reverse=True)[:5]
    names = {f.id: f.name for f in db.scalars(
        select(Forwarder).where(Forwarder.id.in_([i for i, _ in top])))} if top else {}
    rejected = by_status.get(TransportOrderStatus.ODRZUCONE.value, 0)
    return {
        "total": len(rows),
        "by_status": by_status,
        "avg_realization_days": (round(sum(realization_days) / len(realization_days), 1)
                                 if realization_days else None),
        "rejection_rate": round(rejected / len(rows) * 100, 1) if rows else 0.0,
        "top_forwarders": [{"name": names.get(i, f"#{i}"), "count": c} for i, c in top],
    }


@router.post("/transport-orders", response_model=TransportOrderOut, status_code=201)
def create_transport_order(body: TransportOrderIn, db: Session = Depends(get_db),
                           user: User = editors):
    container = get_container_checked(db, body.container_id, user)
    forwarder_id = body.forwarder_id or container.forwarder_id
    if not forwarder_id or not db.get(Forwarder, forwarder_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Wskaż spedytora (kontener nie ma przypisanego).")
    order = TransportOrder(
        container_id=container.id, company_id=container.company_id,
        forwarder_id=forwarder_id, pickup_location=body.pickup_location,
        delivery_location=body.delivery_location, pickup_date=body.pickup_date,
        delivery_date=body.delivery_date, instructions=body.instructions,
        created_by_id=user.id)
    db.add(order)
    db.flush()
    record(db, entity_type="transport_orders", entity_id=order.id, field="status",
           old_value=None, new_value=order.status.value, user=user, note="utworzenie")
    notify(db, forwarder_users(db, forwarder_id), kind="order",
           title=f"Nowe zlecenie transportowe: {container.container_no}",
           body=body.instructions, container_id=container.id, exclude_user_id=user.id)
    db.commit()
    return order_to_out(get_order_checked(db, order.id, user))


def _check_order_flow(order: TransportOrder, target: TransportOrderStatus, user: User) -> None:
    flow = ORDER_FLOW.get(target)
    if not flow:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nieprawidłowy status docelowy.")
    allowed_from, allowed_roles = flow
    if user.role not in allowed_roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Brak uprawnień do tego kroku obiegu.")
    if order.status not in allowed_from:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Przejście {order.status.value} → {target.value} niedozwolone.")


@router.post("/transport-orders/{order_id}/status", response_model=TransportOrderOut)
def change_order_status(order_id: int, body: TransportOrderStatusIn,
                        db: Session = Depends(get_db), user: User = viewer):
    order = get_order_checked(db, order_id, user)
    if user.role in ORDER_CORRECTIONS.get((order.status, body.status), set()):
        if not body.reason.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Korekta obiegu zlecenia wymaga podania powodu.")
    else:
        _check_order_flow(order, body.status, user)
    if (body.status == TransportOrderStatus.ZAAKCEPTOWANE and user.role != Role.forwarder
            and not body.reason.strip()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Akceptacja w imieniu spedytora wymaga notatki (np. „potwierdził telefonicznie”).")
    if body.status == TransportOrderStatus.ODRZUCONE and not body.reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Odrzucenie zlecenia wymaga podania powodu.")
    record(db, entity_type="transport_orders", entity_id=order.id, field="status",
           old_value=order.status.value, new_value=body.status.value,
           user=user, note=body.reason)
    order.status = body.status
    if body.status == TransportOrderStatus.ODRZUCONE:
        order.rejection_reason = body.reason
    elif body.status == TransportOrderStatus.WYSTAWIONE:
        order.rejection_reason = ""   # ponownie wystawione — stary powód zostaje w audycie
    container_no = order.container.container_no if order.container else ""
    if user.role == Role.forwarder:
        recipients = company_watchers(db, order.company_id)
    else:
        recipients = forwarder_users(db, order.forwarder_id)
    notify(db, recipients, kind="order",
           title=f"Zlecenie {container_no}: {body.status.value}",
           body=body.reason, container_id=order.container_id, exclude_user_id=user.id)
    db.commit()
    return order_to_out(get_order_checked(db, order_id, user))


# --- agent celny / odprawa (spedytor) ---

@router.patch("/containers/{container_id}/customs", response_model=ContainerOut)
def update_customs(container_id: int, body: CustomsUpdateIn,
                   db: Session = Depends(get_db),
                   # bez spedytora: odprawa to wyłącznie agencja celna (decyzja 2026-09-28)
                   user: User = editors):
    container = get_container_checked(db, container_id, user)
    changes = body.model_dump(exclude_unset=True)
    check_customs_status_change(container.customs_status, changes.get("customs_status"), user,
                                changes.get("customs_note"))
    record_changes(db, container, changes, user, note="aktualizacja odprawy")
    sync_status_from_customs(db, container, user)   # status kontenera z odprawy (2026-09-28)
    db.commit()
    return to_out(get_container_checked(db, container_id, user), user)


# --- dane kierowcy (uzupełnia spedycja) ---

@router.patch("/containers/{container_id}/driver", response_model=ContainerOut)
def update_driver(container_id: int, body: DriverIn,
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.admin, Role.logistics,
                                                     Role.forwarder))):
    container = get_container_checked(db, container_id, user)
    check_not_modified(db, container, body.expected_updated_at)
    record_changes(db, container, body.model_dump(exclude_unset=True, exclude={"expected_updated_at"}),
                   user, note="dane kierowcy")
    # magazyn przyjmujący (np. DLT) też musi znać nr auta/kierowcy przed przyjazdem
    recipients = container_watchers(db, container) \
        + warehouse_users(db, container.company_id, container.warehouse_id)
    notify(db, recipients, kind="driver",
           title=f"Dane kierowcy dla {container.container_no}",
           # bez danych osobowych — treść idzie też e-mailem/Teams/n8n (RODO, GDPR-001)
           body="Uzupełniono dane kierowcy — szczegóły na karcie kontenera.",
           container_id=container.id, exclude_user_id=user.id)
    db.commit()
    return to_out(get_container_checked(db, container_id, user), user)


# --- e-mail z kolejką dnia do spedycji (prośba o dane kierowców) ---

def _queue_email_html(day, warehouse_label: str, containers: list[Container]) -> str:
    """Tabela kolejki dnia w stylu firmowego maila (zielone wiersze, czerwone numery)."""
    from ..html_templates import render
    from ..mail_html import RED, table_context
    ordered = sorted(containers, key=lambda x: (x.warehouse.name if x.warehouse else "", x.id))
    table = table_context(ordered, [("supplier", RED), "vessel", "eta", "transport", "container",
                                    "orders", "warehouse", "delivery", "rf"])
    return render("mail/queue_day.html", day=day, warehouse_label=warehouse_label,
                  containers=containers, **table)


@router.post("/forwarding/queue-email")
def send_queue_email(body: QueueEmailIn, db: Session = Depends(get_db),
                     user: User = editors):
    if not settings.smtp_host:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "SMTP nie jest skonfigurowany — uzupełnij SMTP_HOST "
                            "(np. smtp.office365.com) w konfiguracji.")
    company = get_company_by_code(db, user, body.company_code)

    query = (select(Container)
             .options(selectinload(Container.supplier), selectinload(Container.order),
                      selectinload(Container.warehouse), selectinload(Container.forwarder))
             .where(Container.company_id == company.id,
                    Container.notify_date == body.day))
    if body.warehouse_id:
        query = query.where(Container.warehouse_id == body.warehouse_id)
    containers = db.scalars(query.order_by(Container.id)).all()
    if not containers:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Brak kontenerów na wskazany dzień.")

    warehouse_label = "wszystkie magazyny"
    if body.warehouse_id:
        warehouse = db.get(Warehouse, body.warehouse_id)
        warehouse_label = warehouse.name if warehouse else warehouse_label

    by_forwarder: dict[int | None, list[Container]] = {}
    for c in containers:
        by_forwarder.setdefault(c.forwarder_id, []).append(c)

    sent, missing_email, no_forwarder, failed = [], [], 0, []
    for forwarder_id, items in by_forwarder.items():
        forwarder = db.get(Forwarder, forwarder_id) if forwarder_id else None
        if not forwarder:
            no_forwarder += len(items)
            continue
        if not forwarder.email:
            missing_email.append(forwarder.name)
            continue
        subject = f"Kolejka {date_pl(body.day)} {warehouse_label} — dane kierowców"
        html = _queue_email_html(body.day, warehouse_label, items)
        try:
            send_html_email([forwarder.email], subject, html,
                            reply_to=user.email or settings.smtp_from)
        except Exception as exc:  # noqa: BLE001 — nie przerywamy pozostałych wysyłek
            logger.warning("kolejka dnia: mail do spedytora %s nie wyszedł", forwarder.name,
                           exc_info=True)
            failed.append({"forwarder": forwarder.name, "error": str(exc)})
            continue
        record(db, entity_type="queue_email", entity_id=company.id, field="sent",
               old_value=None, new_value=f"{forwarder.name} <{forwarder.email}>",
               user=user, note=f"kolejka {body.day.isoformat()} ({warehouse_label}), "
                               f"{len(items)} kont.")
        sent.append({"forwarder": forwarder.name, "email": forwarder.email,
                     "containers": len(items)})
    db.commit()
    return {"sent": sent, "missing_email": missing_email, "no_forwarder": no_forwarder,
            "failed": failed}


# --- wiadomości ---

def _mentioned_users(db: Session, body: str, container) -> list["User"]:
    """Aktywni userzy @wspomniani w treści, z realnym dostępem do tego kontenera
    (izolacja spółek — obcy login po prostu nie dostaje powiadomienia)."""
    from ..deps import check_container_access
    logins = set(re.findall(r"@([\w.\-]+)", body))
    if not logins:
        return []
    users = db.scalars(select(User).where(
        User.is_active, User.login.in_(logins))).all()
    allowed = []
    for u in users:
        try:
            check_container_access(u, container)
            allowed.append(u)
        except HTTPException:
            continue
    return allowed


# wspólny wątek, ale agencja celna i spedytor nie widzą swoich wiadomości nawzajem (spedytor:
# zero danych odprawy; agencja: nie jej sprawa) — personel wewnętrzny widzi wszystko (REGULY-PROCESU)
_WALLED = {Role.customs: Role.forwarder, Role.forwarder: Role.customs}


def message_visible(author_role: Role | None, reader_role: Role) -> bool:
    return author_role is None or _WALLED.get(author_role) != reader_role


@router.get("/containers/{container_id}/messages", response_model=list[MessageOut])
def list_messages(container_id: int, db: Session = Depends(get_db), user: User = viewer):
    get_container_checked(db, container_id, user)
    messages = db.scalars(select(Message).options(selectinload(Message.user))
                          .where(Message.container_id == container_id)
                          .order_by(Message.created_at, Message.id)).all()
    result = []
    for message in messages:
        if not message_visible(message.user.role if message.user else None, user.role):
            continue
        out = MessageOut.model_validate(message)
        if message.user:
            out.user_login = message.user.login
            out.user_full_name = message.user.full_name
            out.user_role = message.user.role
        result.append(out)
    return result


@router.post("/containers/{container_id}/messages", response_model=MessageOut,
             status_code=201)
def create_message(container_id: int, body: MessageIn,
                   db: Session = Depends(get_db), user: User = viewer):
    container = get_container_checked(db, container_id, user)
    message = Message(container_id=container_id, user_id=user.id, body=body.body)
    db.add(message)
    mentioned = [u for u in _mentioned_users(db, body.body, container)
                 if message_visible(user.role, u.role)]
    watchers = [u for u in container_watchers(db, container) if message_visible(user.role, u.role)]
    notify(db, watchers, kind="message",
           title=f"Nowa wiadomość przy {container.container_no} ({user.full_name or user.login})",
           body=body.body[:500], container_id=container_id,
           exclude_user_id=user.id)
    if mentioned:
        # wzmianka jest jawna — pomija filtr „tylko obserwowane"
        notify(db, mentioned, kind="mention",
               title=f"Wspomniano Cię przy kontenerze {container.container_no} "
                     f"({user.full_name or user.login})",
               body=body.body[:500], container_id=container_id,
               exclude_user_id=user.id, ignore_watch_only=True)
    db.commit()
    out = MessageOut.model_validate(message)
    out.user_login = user.login
    out.user_full_name = user.full_name
    out.user_role = user.role
    return out


# załączniki/OCR i faktury BL — osobne moduły; dołączone na końcu, więc kolejność tras
# (i prefiks /api, tag „spedycja”) jest taka jak przed podziałem
router.include_router(forwarding_files.router)
router.include_router(forwarding_freight.router)

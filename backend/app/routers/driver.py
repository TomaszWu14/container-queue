"""SMS do kierowcy i zgłoszenia kierowcy wpisywane w aplikacji.

Decyzja 2026-10-07: nic bez logowania — kierowca dostaje SMS z datą, adresem i telefonem
magazynu (bez linku). Przyjazd odnotowuje brama (check-in), spóźnienie po telefonie kierowcy
wpisuje logistyka / magazyn (POST /api/gate/{id}/delay → report_delay).
"""
import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record
from ..config import settings
from ..database import get_db
from ..date_pl import date_pl
from ..deps import ForwarderOrEditors as forwarder_or_editors
from ..models import (PL_TZ, AuditLog, Container, Role, SmsMessage, User, pl_midnight_utc,
                      utcnow)
from ..notifications import company_watchers, notify, warehouse_users
from ..sms import SmsError, send_sms, sms_configured
from ..sms_budget import SmsBudgetExceeded, check_budget

router = APIRouter(prefix="/api", tags=["kierowca"])
logger = logging.getLogger(__name__)


def _delivery_date(container: Container) -> datetime.date | None:
    """Data planowanej dostawy dla kierowcy: awizacja (notify_date), fallback ETA."""
    return container.notify_date or container.eta


# --- wysyłka SMS (panel kierowcy) ---

def send_driver_sms(db: Session, container: Container,
                    user: User | None = None) -> SmsMessage:
    """Wysyła SMS z danymi dostawy (bez linku). Rekord SmsMessage zawsze
    zapisany (status sent/error) — panel pokazuje pełną historię. Commit u wołającego.
    Wyczerpany dzienny limit (COST-003) → SmsBudgetExceeded, zanim cokolwiek się zmieni."""
    check_budget(db)
    delivery = _delivery_date(container)
    warehouse = container.warehouse
    body = (f"TIMPORYE: dostawa {container.container_no}"
            + (f" {date_pl(delivery)}" if delivery else "")
            + (f". Magazyn: {warehouse.name}, {warehouse.address}" if warehouse else "")
            + (f". Tel. magazynu: {warehouse.contact_phone}" if warehouse and warehouse.contact_phone else "")
            + ". Spoznienie? Zadzwon do magazynu.")
    message = SmsMessage(container_id=container.id, phone=container.driver_phone,
                         body=body, delivery_date=delivery)
    try:
        send_sms(container.driver_phone, body)
        message.status = "sent"
    except SmsError as exc:
        message.status = "error"
        message.error = str(exc)[:300]
    db.add(message)
    record(db, entity_type="containers", entity_id=container.id, field="driver_sms",
           old_value=None, new_value=message.status, user=user,
           note="SMS do kierowcy")
    return message


# spedytor: max N wysłanych SMS na kontener w dobie kalendarzowej (czas polski; liczone z audytu,
# wszystkie konta spedytorów); logistyka/admin bez limitu (audyt UI S10, 2026-09-27)
FORWARDER_SMS_LIMIT = 3   # domyślna wartość; aktualna z panelu admina (sms_settings)


def _forwarder_limit(db: Session) -> int:
    from ..sms_settings import load
    return load(db).forwarder_daily_limit


def _forwarder_sms_today(db: Session, container_id: int) -> int:
    return db.scalar(select(func.count(AuditLog.id)).join(User, AuditLog.user_id == User.id).where(
        AuditLog.entity_type == "containers", AuditLog.entity_id == container_id,
        AuditLog.field == "driver_sms", AuditLog.new_value == "sent",
        User.role == Role.forwarder,
        AuditLog.created_at >= pl_midnight_utc())) or 0


@router.post("/containers/{container_id}/driver-sms")
def send_sms_now(container_id: int, db: Session = Depends(get_db),
                 user: User = forwarder_or_editors):
    from .containers import get_container_checked
    container = get_container_checked(db, container_id, user)
    if not (container.driver_phone or "").strip():
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Kontener nie ma numeru telefonu kierowcy.")
    if user.role == Role.forwarder \
            and _forwarder_sms_today(db, container.id) >= _forwarder_limit(db):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Wysłano już {_forwarder_limit(db)} SMS do kierowcy tego kontenera "
                            "dzisiaj. Jutro możesz wysłać ponownie, a dziś kolejny wyśle logistyka.")
    if not sms_configured():
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "SMS nie jest skonfigurowany (SMS_PROVIDER / SMSAPI_TOKEN). "
                            "Skontaktuj się z administratorem.")
    try:
        message = send_driver_sms(db, container, user)
    except SmsBudgetExceeded as exc:
        db.commit()   # alert adminów zostaje mimo odmowy
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    db.commit()
    return {"status": message.status, "error": message.error}


@router.get("/containers/{container_id}/driver-sms")
def sms_history(container_id: int, db: Session = Depends(get_db),
                user: User = forwarder_or_editors):
    from .containers import get_container_checked
    get_container_checked(db, container_id, user)
    rows = db.scalars(select(SmsMessage).where(SmsMessage.container_id == container_id)
                      .order_by(SmsMessage.created_at.desc())).all()
    return {"configured": sms_configured(),
            "messages": [{"id": m.id, "phone": m.phone, "status": m.status,
                          "error": m.error, "created_at": m.created_at.isoformat()}
                         for m in rows]}


# okno dla zgłoszeń spóźnienia — każde to mail/Teams/n8n do logistyki
_DELAY_DEDUP = datetime.timedelta(minutes=30)


def report_delay(db: Session, container: Container, eta_time: str, user: User | None,
                 note: str) -> None:
    """Spóźnienie kierowcy (HH:MM) — ze strony kierowcy albo wpisane w aplikacji przez logistykę /
    magazyn po telefonie (decyzja 2026-10-07: nic bez logowania). Najwyżej jedno zgłoszenie na
    kontener w oknie — każde to mail/Teams/n8n; ta sama godzina = retry (OK), inna = odmowa."""
    eta_time = eta_time.strip()[:5]
    try:
        datetime.time.fromisoformat(eta_time)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Podaj godzinę w formacie HH:MM.") from None
    previous = db.scalar(select(AuditLog).where(
        AuditLog.entity_type == "containers",
        AuditLog.entity_id == container.id,
        AuditLog.field == "driver-delayed",
        AuditLog.created_at >= utcnow() - _DELAY_DEDUP)
        .order_by(AuditLog.created_at.desc()).limit(1))
    if previous:
        if previous.new_value == eta_time:
            return
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Spóźnienie (~{previous.new_value}) zostało już przekazane do "
                            "magazynu. Kolejną zmianę można zgłosić za pół godziny.")
    record(db, entity_type="containers", entity_id=container.id, field="driver-delayed",
           old_value=None, new_value=eta_time, user=user, note=note)
    recipients = (company_watchers(db, container.company_id)
                  + warehouse_users(db, container.company_id, container.warehouse_id))
    notify(db, recipients, kind="driver",
           title=f"Kierowca spóźni się: {container.container_no}, nowa godzina ~{eta_time}",
           container_id=container.id, exclude_user_id=user.id if user else None)
    db.commit()


# --- auto-wysyłka dzień przed dostawą ---

def send_tomorrow_sms(db: Session, now: datetime.datetime | None = None) -> int:
    """Auto-SMS przypominające kierowcom o dostawie — godzina (czas PL) i dni przed dostawą
    z panelu admina (sms_settings). Dedup: najwyżej jedno przypomnienie per kontener+data
    dostawy na dobę PL (kilka dni przed = kilka przypomnień, każdego dnia jedno); nieudane
    ponawiane najwyżej SMS_AUTO_MAX_ATTEMPTS razy na dobę, całość w dziennym limicie SMS."""
    from ..sms_settings import load
    cfg = load(db)
    if not sms_configured() or not cfg.reminder_enabled:
        return 0
    now_utc = now or utcnow()
    now_pl = now_utc.replace(tzinfo=datetime.UTC).astimezone(PL_TZ)
    if now_pl.hour < cfg.reminder_hour:
        return 0
    day_start = pl_midnight_utc(now_pl.date())
    sent = 0
    for days in cfg.reminder_days_before:
        target = now_pl.date() + datetime.timedelta(days=days)
        candidates = db.scalars(select(Container).where(
            Container.status.not_in(Container.FINISHED),
            Container.driver_phone != "",
            (Container.notify_date == target)
            | (Container.notify_date.is_(None) & (Container.eta == target)))).all()
        for container in candidates:
            statuses = db.scalars(select(SmsMessage.status).where(
                SmsMessage.container_id == container.id,
                SmsMessage.delivery_date == target,
                SmsMessage.created_at >= day_start)).all()
            # COST-003: pętla chodzi co 15 min — bez limitu zły numer albo awaria bramki
            # dawały kilkadziesiąt płatnych prób na kontener dziennie
            if "sent" in statuses or len(statuses) >= settings.sms_auto_max_attempts:
                continue
            try:
                message = send_driver_sms(db, container)
                # commit po KAŻDEJ wysyłce: wyjątek/redeploy w połowie pętli nie może cofnąć
                # SmsMessage już wysłanych SMS (limit dzienny by ich nie liczył → kolejny
                # płatny SMS za 15 min)
                db.commit()
            except SmsBudgetExceeded:
                logger.warning("auto-SMS: dzienny limit SMS wyczerpany — przerwano, wysłano %d",
                               sent)
                db.commit()
                return sent
            except Exception:
                # jeden zepsuty kontener nie zatrzymuje przypomnień dla pozostałych
                logger.exception("auto-SMS: błąd wysyłki dla kontenera %s", container.id)
                db.rollback()
                continue
            if message.status == "sent":
                sent += 1
    return sent

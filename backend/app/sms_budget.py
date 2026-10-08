"""COST-003: globalny dzienny limit SMS (koszt bramki) i alert adminów przy 80% i 100%.

Limit liczy PRÓBY wysyłki od polskiej północy — także nieudane (bramka mogła naliczyć SMS
mimo błędu). `SMS_DAILY_CAP=0` = bez limitu. Alert raz na dobę na próg, do aktywnych adminów
(dzwonek/e-mail wg matrycy powiadomień). Limit prób auto-przypomnienia: routers/driver.py.
"""
import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Notification, Role, SmsMessage, User, pl_midnight_utc
from .sms import SmsError

WARN_RATIO = 0.8


class SmsBudgetExceeded(SmsError):
    """Dzienny limit SMS wyczerpany — nic nie idzie do bramki."""


def attempts_today(db: Session) -> int:
    db.flush()   # próby z tej samej transakcji (pętla auto-SMS) też się liczą
    return db.scalar(select(func.count(SmsMessage.id)).where(
        SmsMessage.created_at >= pl_midnight_utc())) or 0


def _alert_admins_once(db: Session, kind: str, title: str, body: str) -> None:
    if db.scalar(select(Notification.id).where(
            Notification.kind == kind, Notification.created_at >= pl_midnight_utc()).limit(1)):
        return
    from .notifications import notify
    admins = db.scalars(select(User).where(User.role == Role.admin,
                                           User.is_active.is_(True))).all()
    notify(db, list(admins), kind=kind, title=title, body=body)


def check_budget(db: Session) -> None:
    """Przed każdą próbą wysyłki. Wyczerpany limit → alert + SmsBudgetExceeded (wołający
    commituje alert); próba dobijająca do 80% → ostrzeżenie. Commit u wołającego."""
    cap = settings.sms_daily_cap
    if cap <= 0:
        return
    used = attempts_today(db)
    if used >= cap:
        _alert_admins_once(
            db, "sms_budget_exceeded", f"SMS: wyczerpany dzienny limit ({cap})",
            "Wysyłka SMS do kierowców wstrzymana do północy. Sprawdź historię SMS "
            "(pętla, zły numer, awaria bramki) albo podnieś SMS_DAILY_CAP.")
        raise SmsBudgetExceeded(f"Wyczerpany dzienny limit SMS ({cap}). Wysyłka wróci po "
                                "północy — skontaktuj się z administratorem.")
    if used + 1 >= math.ceil(cap * WARN_RATIO):
        _alert_admins_once(
            db, "sms_budget_warning", f"SMS: {used + 1} z {cap} dziennego limitu",
            f"Wykorzystano {round(100 * WARN_RATIO)}% dziennego limitu SMS (SMS_DAILY_CAP). "
            "Po jego wyczerpaniu wysyłka wstrzyma się do północy.")

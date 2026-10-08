"""Retencja danych bez własnego cyklu życia (OBS-011 / GDPR-007) — wpięte w zadanie
`applog_retention` (raz na dobę). Każda funkcja osobno: błąd jednej nie ucisza reszty."""
import datetime

from sqlalchemy import delete

from .config import settings
from .models import (
    ClientError,
    LoginFailure,
    PasswordResetToken,
    RefreshToken,
    SmsMessage,
    utcnow,
)


def _ago(days: int) -> datetime.datetime:
    return utcnow() - datetime.timedelta(days=days)


def purge_expired_tokens(db) -> int:
    """Refresh i reset tokeny wygasłe dawniej niż TOKEN_RETENTION_DAYS. Liczy się tylko
    `expires_at`: ważny token (sesja, także odwołany — wykrywa ponowne użycie) zostaje."""
    cutoff = _ago(settings.token_retention_days)
    n = sum(db.execute(delete(m).where(m.expires_at < cutoff)).rowcount or 0
            for m in (RefreshToken, PasswordResetToken))
    db.commit()
    return n


def purge_sms_messages(db) -> int:
    """Historia SMS (telefon kierowcy, treść z linkiem) starsza niż SMS_RETENTION_DAYS."""
    cutoff = _ago(settings.sms_retention_days)
    n = db.execute(delete(SmsMessage).where(SmsMessage.created_at < cutoff)).rowcount or 0
    db.commit()
    return n


def purge_client_errors(db) -> int:
    """Błędy JS z beaconu (URL, User-Agent) starsze niż CLIENT_ERROR_RETENTION_DAYS."""
    cutoff = _ago(settings.client_error_retention_days)
    n = db.execute(delete(ClientError).where(ClientError.created_at < cutoff)).rowcount or 0
    db.commit()
    return n


def purge_login_failures(db) -> int:
    """Stan limitera logowań (ARCH-003) starszy niż okno — limiter sprząta sam co N porażek,
    ale przy ciszy (brak porażek) wiersze z IP-skrótami zostawałyby bez końca."""
    cutoff = utcnow() - datetime.timedelta(minutes=settings.login_window_minutes)
    n = db.execute(delete(LoginFailure).where(LoginFailure.created_at <= cutoff)).rowcount or 0
    db.commit()
    return n

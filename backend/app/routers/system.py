"""W14: panel System (zdrowie), beacon błędów JS, log logowań, BlockedIP,
podgląd „jako rola" i sesje użytkowników (admin)."""
import datetime
import logging
import pathlib
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..audit import record
from ..config import settings
from ..database import get_db
from ..deps import AdminOnly as admin_only
from ..models import (
    AuditLog,
    BlockedIP,
    ClientError,
    Container,
    PurchaseOrder,
    RefreshToken,
    Role,
    TrackedVessel,
    User,
    utcnow,
)
from ..schemas import (
    BlockedIPIn,
    BlockedIPOut,
    ClientErrorIn,
    ImpersonateIn,
    SessionOut,
)
from ..security import (
    ACCESS_COOKIE,
    api_limiter,
    client_ip,
    create_impersonation_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["system"])

_START_TIME = time.monotonic()


# --- W14 #50: beacon błędów JS z panelu (bez auth, ostry rate-limit, twarde limity) ---

@router.post("/client-error", status_code=202)
def client_error(body: ClientErrorIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if api_limiter.hit(f"cerr:{ip}", settings.client_error_rate_per_minute) is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Za dużo zgłoszeń.")
    ua = (request.headers.get("user-agent") or "")[:300]
    from ..main import redact_tokens  # ponytail: import w funkcji (main importuje routery)
    # OBS-011: tokeny linków publicznych (/dostawa/<token> itd.) nie trafiają do bazy
    db.add(ClientError(name=body.name, message=redact_tokens(body.message),
                       stack=redact_tokens(body.stack), url=redact_tokens(body.url),
                       user_agent=ua))
    db.commit()
    # OBS-010: do Sentry jako osobne zdarzenie frontu (grupowane po błędzie); log tylko jako
    # warning — ERROR poszedłby drugi raz przez integrację logging jako jedno zbiorcze „issue”
    from ..redaction import capture_client_error
    capture_client_error(body.name, body.message, body.stack, body.url, ua)
    logger.warning("Client error: %s: %s (url=%s)", body.name, body.message[:300],
                   redact_tokens(body.url))
    return {"detail": "ok"}


# --- monitor wydajności i pojemności serwera (admin-only, 2026-09-24) ---

@router.get("/admin/monitor")
def server_monitor(db: Session = Depends(get_db), user: User = admin_only):
    from .. import monitoring
    return monitoring.snapshot(db, _START_TIME)


# --- W14 #48: panel zdrowia (admin-only) ---

def _safe_scalar(db, stmt):
    try:
        return db.scalar(stmt)
    except Exception:  # noqa: BLE001 — metryka pomocnicza nie wywala panelu
        logger.warning("panel systemu: metryka niedostępna", exc_info=True)
        return None


def _dir_size_mb(path: str) -> float | None:
    try:
        root = pathlib.Path(path)
        if not root.is_dir():
            return 0.0
        return round(sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
                     / 1_048_576, 1)
    except Exception:  # noqa: BLE001
        logger.warning("panel systemu: rozmiar katalogu %s niedostępny", path, exc_info=True)
        return None


@router.get("/admin/system")
def system_status(db: Session = Depends(get_db), user: User = admin_only):
    from ..backup_verify import last_result
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        logger.warning("panel systemu: baza nie odpowiada na SELECT 1", exc_info=True)
        db_ok = False
    day_ago = utcnow() - datetime.timedelta(hours=24)
    iso = lambda v: v.isoformat() if v else None  # noqa: E731
    return {
        "version": settings.app_version if settings.app_version != "dev"
        else (settings.sentry_release or "dev"),
        "built_at": settings.build_time,
        "uptime_s": round(time.monotonic() - _START_TIME),
        "database": "ok" if db_ok else "error",
        "run_background_jobs": settings.run_background_jobs,
        "last_tracking_sync": iso(_safe_scalar(db, select(func.max(Container.tracked_at)))),
        "last_ais_seen": iso(_safe_scalar(db, select(func.max(TrackedVessel.last_seen)))),
        "last_po_import": iso(_safe_scalar(db, select(func.max(PurchaseOrder.created_at)))),
        "last_container_created": iso(_safe_scalar(db, select(func.max(Container.created_at)))),
        "client_errors_24h": _safe_scalar(db, select(func.count()).select_from(ClientError)
                                          .where(ClientError.created_at >= day_ago)) or 0,
        "uploads_size_mb": _dir_size_mb(settings.uploads_dir),
        "backup_verify": last_result,
    }


@router.get("/admin/integrations")
def integrations_status(db: Session = Depends(get_db), user: User = admin_only):
    """Stan integracji zewnętrznych (W12): skonfigurowana/wyłączona + ostatni sygnał.

    Zbiera istniejące sygnały konfiguracji (is_configured/flagi env) w jedno miejsce —
    diagnostyka bez zaglądania do Coolify."""
    from .. import mailer, powerbi, sharepoint, teams
    from ..sms import sms_configured
    iso = lambda v: v.isoformat() if v else None  # noqa: E731

    def item(key, label, configured, detail="", last=None):
        return {"key": key, "label": label,
                "status": "on" if configured else "off",
                "detail": detail, "last_signal": iso(last)}

    sp_detail, sp_last = sharepoint.status_detail(db)
    mail_ready, mail_detail, mail_last = mailer.status_detail(db)
    teams_url = settings.teams_webhook_url.strip()
    teams_detail, teams_last = teams.status_detail(teams_url) if teams_url else ("—", None)
    return {"integrations": [
        item("sharepoint", "SharePoint (sync kolejki)", sharepoint.is_configured(),
             sp_detail, sp_last),
        item("powerbi", "Power BI", powerbi.is_configured(),
             f"provider={settings.powerbi_provider}"),
        item("ais", "AIS (pozycje statków)", bool(settings.aisstream_api_key.strip()),
             "aisstream.io",
             _safe_scalar(db, select(func.max(TrackedVessel.last_seen)))),
        item("sms", "SMS (kierowcy)", sms_configured(),
             f"provider={settings.sms_provider}"),
        item("smtp", "E-mail (SMTP)", bool(settings.smtp_host.strip()),
             settings.smtp_host or "—"),
        item("mail_avizo", "Poczta awizacji (spedycja)", mail_ready, mail_detail, mail_last),
        item("teams", "MS Teams", bool(teams_url), teams_detail, teams_last),
    ]}


@router.post("/admin/system/verify-backup")
def run_verify_backup(user: User = admin_only):
    """W14 #47: ręczne uruchomienie weryfikacji backupu (przycisk w panelu System)."""
    from ..backup_verify import verify_backup
    return verify_backup()


# --- W14 #90: log logowań + BlockedIP ---

AUTH_FIELDS = ("login", "login_failed", "logout", "password_reset",
               "password_reset_requested", "password_changed", "2fa_enabled",
               "session_revoked", "sessions_revoked_others")


@router.get("/admin/auth-log")
def auth_log(q: str = "", ip: str = "", date_from: datetime.date | None = None,
             date_to: datetime.date | None = None,
             limit: int = Query(default=200, ge=1, le=1000),
             db: Session = Depends(get_db), user: User = admin_only):
    stmt = select(AuditLog).where(AuditLog.entity_type == "auth",
                                  AuditLog.field.in_(AUTH_FIELDS))
    if q:
        stmt = stmt.where(AuditLog.new_value.ilike(f"%{q}%"))
    if ip:
        stmt = stmt.where(AuditLog.note.ilike(f"%{ip}%"))
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at
                          < date_to + datetime.timedelta(days=1))
    rows = db.scalars(stmt.order_by(AuditLog.created_at.desc())
                      .limit(min(max(limit, 1), 1000))).all()
    return [{"id": r.id, "field": r.field, "login": r.new_value, "note": r.note,
             "created_at": r.created_at.isoformat()} for r in rows]


@router.get("/admin/blocked-ips", response_model=list[BlockedIPOut])
def list_blocked_ips(db: Session = Depends(get_db), user: User = admin_only):
    return db.scalars(select(BlockedIP).order_by(BlockedIP.created_at.desc())).all()


@router.post("/admin/blocked-ips", response_model=BlockedIPOut, status_code=201)
def block_ip(body: BlockedIPIn, db: Session = Depends(get_db), user: User = admin_only):
    ip = body.ip.strip()
    if db.scalar(select(BlockedIP).where(BlockedIP.ip == ip)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ten adres jest już zablokowany.")
    row = BlockedIP(ip=ip, note=body.note, created_by_id=user.id)
    db.add(row)
    db.flush()
    record(db, entity_type="blocked_ip", entity_id=row.id, field="blocked",
           old_value=None, new_value=ip, user=user, note=body.note)
    db.commit()
    return row


@router.delete("/admin/blocked-ips/{blocked_id}", status_code=204)
def unblock_ip(blocked_id: int, db: Session = Depends(get_db), user: User = admin_only):
    row = db.get(BlockedIP, blocked_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
    record(db, entity_type="blocked_ip", entity_id=row.id, field="unblocked",
           old_value=row.ip, new_value=None, user=user)
    db.delete(row)
    db.commit()


# --- W14 #87: podgląd „jako rola" (read-only) ---

@router.post("/admin/impersonate")
def impersonate(body: ImpersonateIn, response: Response,
                db: Session = Depends(get_db), user: User = admin_only):
    ctx = {"role": body.role.value, "company_id": body.company_id,
           "forwarder_id": body.forwarder_id, "customs_agency_id": body.customs_agency_id,
           "warehouse_id": body.warehouse_id, "view_all": body.role == Role.admin}
    token = create_impersonation_token(user, ctx)
    record(db, entity_type="impersonation", entity_id=user.id, field="start",
           old_value=None, new_value=body.role.value, user=user,
           note=f"podgląd jako {body.role.value} (spółka {body.company_id})")
    db.commit()
    # tylko cookie access (60 min) — refresh cookie zostaje, „wyjdź" = /api/auth/refresh
    response.set_cookie(ACCESS_COOKIE, token, max_age=3600, httponly=True,
                        samesite="lax", secure=settings.secure_cookies)
    return {"access_token": token, "detail": "Podgląd aktywny (tylko odczyt, 60 min)."}


# --- W14 #49/#88: 2FA disable + sesje dowolnego użytkownika (admin) ---

@router.post("/users/{user_id}/2fa/disable", status_code=200)
def disable_2fa(user_id: int, db: Session = Depends(get_db), user: User = admin_only):
    """Wyłączenie 2FA tylko przez INNEGO admina (zgubiony telefon), z audytem."""
    if user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Własne 2FA może wyłączyć tylko inny administrator.")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono użytkownika.")
    if not target.totp_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA nie jest włączone.")
    target.totp_secret = None
    target.totp_backup_codes = ""
    record(db, entity_type="auth", entity_id=target.id, field="2fa_disabled",
           old_value=target.login, new_value=None, user=user,
           note=f"wyłączenie 2FA przez {user.login}")
    db.commit()
    return {"detail": "2FA wyłączone."}


@router.get("/users/{user_id}/sessions", response_model=list[SessionOut])
def user_sessions(user_id: int, db: Session = Depends(get_db), user: User = admin_only):
    from .auth import list_user_sessions
    if not db.get(User, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono użytkownika.")
    return list_user_sessions(db, user_id, None)


@router.delete("/users/{user_id}/sessions/{session_id}", status_code=204)
def revoke_user_session(user_id: int, session_id: int,
                        db: Session = Depends(get_db), user: User = admin_only):
    row = db.get(RefreshToken, session_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono sesji.")
    row.revoked = True
    record(db, entity_type="auth", entity_id=user_id, field="session_revoked",
           old_value=None, new_value=str(session_id), user=user,
           note=f"wylogowanie sesji przez admina {user.login}")
    db.commit()

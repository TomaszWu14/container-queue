"""Dziennik serwera: bufor w pamięci → baza co 30 s (applog_loop), alerty dla adminów.

Middleware i job_loop tylko dopisują do bufora (bez SQL na ścieżce żądania). Każdy
proces ma własny bufor i własną pętlę zrzutu (także instancja bez pętli tła)."""
import asyncio
import datetime
import logging
import threading
import time

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .database import SessionLocal
from .models import AuditLog, JobRun, Notification, RequestCounter, RequestLog, Role, User, utcnow

logger = logging.getLogger(__name__)

SLOW_MS = 1000
RETENTION_DAYS = 30
ALERT_EVERY_S = 3600
FLUSH_EVERY_S = 30
MAX_BUFFER = 10_000  # ponytail: twardy limit na proces; przy stałym zalewaniu strata > alarm

_lock = threading.Lock()
_requests: list[dict] = []
_jobs: list[dict] = []
_counters: dict[datetime.datetime, list[int]] = {}   # minuta → [total, 4xx, 5xx, dur_sum]
_last_alert: dict[str, float] = {}
_requests_full_warned = False
_jobs_full_warned = False


def reset_for_tests() -> None:
    global _requests_full_warned, _jobs_full_warned
    with _lock:
        for store in (_requests, _jobs, _counters, _last_alert):
            store.clear()
        _requests_full_warned = False
        _jobs_full_warned = False


def _skip(method: str, path: str, status: int) -> bool:
    # health i jego głęboki wariant (OBS-009): 503 z monitora co minutę to nie błąd serwera
    return (not path.startswith("/api/") or path in ("/api/health", "/api/health/deep")
            or (status == 401 and method == "GET" and path == "/api/auth/me")
            or (status == 401 and method == "POST" and path == "/api/auth/refresh"))


def record_request(*, method: str, path: str, status: int, duration_ms: int,
                   user_id: int | None, ip: str, request_id: str, error: str = "") -> None:
    from .main import redact_tokens  # ponytail: import w funkcji (main importuje applog)
    method = method[:8]  # kolumna String(8) — Postgres odrzuca cały flush przy przepełnieniu
    if _skip(method, path, status):
        return
    global _requests_full_warned
    minute = utcnow().replace(second=0, microsecond=0)
    with _lock:
        c = _counters.setdefault(minute, [0, 0, 0, 0])
        c[0] += 1
        c[1] += 400 <= status < 500
        c[2] += status >= 500
        c[3] += duration_ms
        if status >= 400 or duration_ms > SLOW_MS:
            if len(_requests) >= MAX_BUFFER:
                if not _requests_full_warned:
                    logger.warning("Bufor żądań dziennika pełny (%d) — nowe wpisy pomijane", MAX_BUFFER)
                    _requests_full_warned = True
                return
            # traceback: ogon (nie głowa) — linia z typem/treścią wyjątku jest na końcu,
            # a stos przez BaseHTTPMiddleware/Starlette potrafi przekroczyć 4000 znaków
            _requests.append(dict(at=utcnow(), method=method, path=redact_tokens(path)[:500],
                                  status=status, duration_ms=duration_ms, user_id=user_id,
                                  ip=ip[:64], request_id=request_id[:16],
                                  error=redact_tokens(error)[-4000:]))


def record_job(*, job: str, fn: str, started_at: datetime.datetime, duration_ms: int,
               ok: bool, detail: str) -> None:
    from .main import redact_tokens
    if job == "monitor_sample" and ok:
        return  # próbkowanie co 60s zalałoby historię zadań — liczą się tylko awarie
    global _jobs_full_warned
    with _lock:
        if len(_jobs) >= MAX_BUFFER:
            if not _jobs_full_warned:
                logger.warning("Bufor zadań dziennika pełny (%d) — nowe wpisy pomijane", MAX_BUFFER)
                _jobs_full_warned = True
            return
        _jobs.append(dict(job=job[:60], fn=fn[:120], started_at=started_at,
                          duration_ms=duration_ms, ok=ok, detail=redact_tokens(detail)[:2000]))


def _alert(db, kind: str, title: str, body: str) -> None:
    """Tylko dzwonek (bell) — e-mail/Teams/n8n poza zakresem dla dziennika serwera.
    Treść nigdy nie zawiera tracebacku (wywołujący przekazuje już oczyszczoną)."""
    now = time.monotonic()
    if now - _last_alert.get(kind, -ALERT_EVERY_S) < ALERT_EVERY_S:
        return
    _last_alert[kind] = now
    from .notifications import kind_rules
    if not kind_rules(db, "system-error").get((Role.admin.value, "bell"), True):
        return                      # wyłączone w matrycy reguł (Administracja)
    admins = list(db.scalars(select(User).where(User.is_active, User.role == Role.admin)))
    db.add_all(Notification(user_id=admin.id, kind="system-error", title=title, body=body)
              for admin in admins)


def _upsert_counters(db, counters: dict) -> None:
    if not counters:
        return
    insert_ = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    for minute, (total, c4, c5, dur) in counters.items():
        stmt = insert_(RequestCounter).values(
            minute=minute, total=total, c4xx=c4, c5xx=c5, dur_ms_sum=dur)
        stmt = stmt.on_conflict_do_update(
            index_elements=["minute"],
            set_={"total": RequestCounter.total + stmt.excluded.total,
                  "c4xx": RequestCounter.c4xx + stmt.excluded.c4xx,
                  "c5xx": RequestCounter.c5xx + stmt.excluded.c5xx,
                  "dur_ms_sum": RequestCounter.dur_ms_sum + stmt.excluded.dur_ms_sum})
        db.execute(stmt)


def flush(db) -> int:
    global _requests_full_warned, _jobs_full_warned
    with _lock:
        reqs, jobs, counters = list(_requests), list(_jobs), dict(_counters)
        for store in (_requests, _jobs, _counters):
            store.clear()
        _requests_full_warned = False
        _jobs_full_warned = False
    _upsert_counters(db, counters)
    db.add_all(RequestLog(**r) for r in reqs)
    db.add_all(JobRun(**j) for j in jobs)
    errors = [r for r in reqs if r["status"] >= 500]
    if errors:
        _alert(db, "request", f"Błąd serwera ({len(errors)}×)",
               f"{errors[0]['method']} {errors[0]['path']} → {errors[0]['status']}")
    failed = [j for j in jobs if not j["ok"]]
    if failed:
        _alert(db, "job", f"Zadanie tła nie powiodło się: {failed[0]['job']}/{failed[0]['fn']}",
               f"{failed[0]['job']}/{failed[0]['fn']}")
    db.commit()
    return len(reqs) + len(jobs)


def purge(db, days: int = RETENTION_DAYS) -> int:
    cutoff = utcnow() - datetime.timedelta(days=days)
    n = 0
    for model, col in ((RequestLog, RequestLog.at), (JobRun, JobRun.started_at),
                       (RequestCounter, RequestCounter.minute)):
        n += db.execute(delete(model).where(col < cutoff)).rowcount or 0
    db.commit()
    return n


def purge_auth_audit(db) -> int:
    """RODO (GDPR-004): kasuje wpisy audit_log z entity_type='auth' (logowania, nieudane próby —
    IP i wpisane loginy) starsze niż AUDIT_AUTH_RETENTION_DAYS. Historia biznesowa zostaje."""
    cutoff = utcnow() - datetime.timedelta(days=settings.audit_auth_retention_days)
    n = db.execute(delete(AuditLog).where(AuditLog.entity_type == "auth",
                                          AuditLog.created_at < cutoff)).rowcount or 0
    db.commit()
    return n


async def applog_loop() -> None:
    def _once():
        with SessionLocal() as db:
            flush(db)
    while True:
        await asyncio.sleep(FLUSH_EVERY_S)
        try:
            await asyncio.to_thread(_once)
        except Exception:  # noqa: BLE001 — pętla nie umiera
            logger.exception("Zrzut dziennika serwera nie powiódł się")


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Mierzy czas i status każdego żądania; wyjątek = 500 z tracebackiem w dzienniku.

    Zapisuje tylko gdy naprawdę mamy wynik: odpowiedź albo złapany Exception. Na
    BaseException spoza Exception (np. CancelledError przy rozłączeniu klienta) nic
    się nie zapisuje — inaczej dziennik fałszywie pokazywałby 500."""

    async def dispatch(self, request, call_next):
        import traceback
        start = time.perf_counter()
        error, status = "", None
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception:
            error = traceback.format_exc()
            status = 500
            raise
        finally:
            if status is not None:
                try:
                    from .security import client_ip
                    record_request(method=request.method, path=request.url.path, status=status,
                                   duration_ms=int((time.perf_counter() - start) * 1000),
                                   user_id=getattr(request.state, "user_id", None),
                                   ip=client_ip(request) or "",
                                   request_id=getattr(request.state, "request_id", ""),
                                   error=error)
                except Exception:
                    logger.exception("Zapis dziennika żądania nie powiódł się")

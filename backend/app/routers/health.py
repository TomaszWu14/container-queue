"""OBS-009: głęboki health check — pętle tła, wiek kopii zapasowej, zajętość dysku.

`/api/health` (main.py) zostaje lekki: Docker HEALTHCHECK i proxy restartują kontener po
jego porażce, a restart nie naprawi starej kopii ani pełnego dysku. `/api/health/deep` jest
dla zewnętrznego monitora (np. Uptime Kuma): 200 = w normie, 503 = coś
wymaga uwagi. Publicznie zwraca TYLKO status; powód (wiek kopii, zajętość dysku, nazwy
zadań) widzi admin pod `/api/admin/health/deep`."""
import logging
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from .. import backup_verify, jobs, monitoring
from ..config import settings
from ..database import SessionLocal
from ..deps import AdminOnly as admin_only
from ..models import JobRun, User, utcnow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["system"])

DISK_MAX_PERCENT = 90.0
# zapas ponad interwał zadania: 6 h → alarm po 7 h (demurrage/customs_delay, plan OBS-009)
JOB_GRACE_S = 3600
# sukcesy tych zadań nie trafiają do job_runs (applog.record_job) — nie da się ich ocenić
UNTRACKED_JOBS = {"monitor_sample"}


def _check_jobs(db) -> dict:
    """Każda funkcja każdej pętli tego procesu musi mieć udany przebieg w oknie
    interwał + JOB_GRACE_S. Liczymy od późniejszego z: ostatni sukces, start pętli —
    tuż po restarcie pierwszy przebieg jeszcze trwa albo czeka na zrzut dziennika (30 s)."""
    started = {name: v for name, v in jobs.STARTED.items() if name not in UNTRACKED_JOBS}
    if not started:   # RUN_BACKGROUND_JOBS=false (instancja wtórna) — pętle chodzą gdzie indziej
        return {"ok": True, "items": [], "detail": "pętle tła nie działają w tym procesie"}
    rows = db.execute(select(JobRun.job, JobRun.fn, func.max(JobRun.started_at))
                      .where(JobRun.ok.is_(True), JobRun.job.in_(started))
                      .group_by(JobRun.job, JobRun.fn)).all()
    last_ok = {(job, fn): at for job, fn, at in rows}
    now = utcnow()
    items = []
    for name, (interval_s, fns, loop_started) in sorted(started.items()):
        max_age_s = interval_s + JOB_GRACE_S
        stale = [fn for fn in fns
                 if (now - max(last_ok.get((name, fn)) or loop_started, loop_started))
                 .total_seconds() > max_age_s]
        oks = [last_ok.get((name, fn)) for fn in fns]
        oldest_ok = None if None in oks else min(oks)
        items.append({"job": name, "ok": not stale, "stale": stale,
                      "max_age_h": round(max_age_s / 3600, 2),
                      "last_ok_at": oldest_ok.isoformat() if oldest_ok else None})
    return {"ok": all(i["ok"] for i in items), "items": items}


def _check_backup() -> dict:
    """Najnowszy dump z backup.sh młodszy niż BACKUP_MAX_AGE_HOURS (ten sam próg co
    cotygodniowa weryfikacja kopii). Poza Postgresem backup.sh nic nie zrzuca — pomijamy."""
    if not make_url(settings.database_url).drivername.startswith("postgresql"):
        return {"ok": True, "detail": "baza nie jest Postgresem — kopie nie są robione"}
    max_age_h = settings.backup_max_age_hours
    try:
        dump = backup_verify._newest_dump()
        age_h = (time.time() - dump.stat().st_mtime) / 3600 if dump else None
    except OSError:   # katalog niedostępny / plik zniknął w trakcie retencji
        dump, age_h = None, None
    if dump is None or age_h is None:
        return {"ok": False, "max_age_h": max_age_h, "detail": "brak plików kopii"}
    return {"ok": age_h <= max_age_h, "newest": dump.name, "age_h": round(age_h, 1),
            "max_age_h": max_age_h}


def _check_disk() -> dict:
    """System plików aplikacji, załączników i kopii (monitoring.disks — bez duplikatów)."""
    items = [{"label": d["label"], "percent": d["percent"], "free_gb": d["free_gb"]}
             for d in monitoring.disks()]
    ok = all(d["percent"] is None or d["percent"] <= DISK_MAX_PERCENT for d in items)
    return {"ok": ok, "max_percent": DISK_MAX_PERCENT, "items": items}


def _check_invoice_queue(db) -> dict:
    """Zaległość kolejki faktur w tle: najstarszy niepocięty zestaw (`uploaded`) dłużej niż
    STALE_MINUTES = pętla tła nie działa albo utknęła (zgłoszenie „WGRANE · 0 pozycji”)."""
    from ..invoices.ingest import STALE_MINUTES
    from ..models import InvoiceJob, InvoiceJobStatus
    oldest = db.scalar(select(func.min(InvoiceJob.created_at))
                       .where(InvoiceJob.status == InvoiceJobStatus.uploaded))
    age = int((utcnow() - oldest).total_seconds() // 60) if oldest else 0
    return {"ok": age <= STALE_MINUTES, "oldest_minutes": age, "max_minutes": STALE_MINUTES}


def run_checks() -> tuple[bool, dict]:
    checks: dict[str, dict] = {}
    with SessionLocal() as db:
        try:
            db.execute(text("SELECT 1"))
            checks["database"] = {"ok": True}
        except Exception:  # noqa: BLE001 — wynik kontroli, nie wyjątek endpointu
            logger.exception("Głęboki health check: baza niedostępna")
            checks["database"] = {"ok": False}
        try:
            checks["jobs"] = _check_jobs(db) if checks["database"]["ok"] \
                else {"ok": False, "detail": "baza niedostępna"}
        except Exception:  # noqa: BLE001
            logger.exception("Głęboki health check: odczyt job_runs nie powiódł się")
            checks["jobs"] = {"ok": False, "detail": "błąd odczytu job_runs"}
        try:
            checks["invoice_queue"] = _check_invoice_queue(db) if checks["database"]["ok"]                 else {"ok": False, "detail": "baza niedostępna"}
        except Exception:  # noqa: BLE001
            logger.exception("Głęboki health check: odczyt kolejki faktur nie powiódł się")
            checks["invoice_queue"] = {"ok": False, "detail": "błąd odczytu kolejki faktur"}
    checks["backup"] = _check_backup()
    checks["disk"] = _check_disk()
    return all(c["ok"] for c in checks.values()), checks


@router.get("/health/deep")
def health_deep():
    """Dla monitora z zewnątrz: kod 200/503 i sam status — bez szczegółów dla anonimów."""
    ok, _ = run_checks()
    return JSONResponse({"status": "ok" if ok else "fail"}, status_code=200 if ok else 503,
                        headers={"Cache-Control": "no-store"})


@router.get("/admin/health/deep")
def health_deep_details(user: User = admin_only):
    """Te same kontrole ze szczegółami — admin sprawdza, dlaczego monitor świeci na czerwono."""
    ok, checks = run_checks()
    return {"status": "ok" if ok else "fail", "checks": checks}

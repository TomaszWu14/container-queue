"""Pętle tła: tabela zadań + jeden runner.

Każde zadanie = (nazwa, interwał w s, [funkcje(db)]). Każda funkcja biegnie we własnym
try i z własną sesją DB w wątku — wyjątek jednej nie ucisza kolejnych (wcześniej np.
customs/docs/forecast/tracking/SMS/stale-import siedziały w jednym try)."""
import asyncio
import datetime
import logging
import time
import traceback
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import NamedTuple

from sqlalchemy import text

from . import applog, monitoring, retention
from .config import settings
from .database import SessionLocal, engine
from .models import today_pl, utcnow
from .notifications import (
    check_customs_alerts,
    check_daily_digest_alerts,
    check_demurrage_alerts,
    check_docs_alerts,
    check_forecast_alerts,
    check_pallet_urgent_alerts,
    check_stale_import_alerts,
    check_tracking_alerts,
    check_weekly_digest_alerts,
    purge_read_notifications,
)

logger = logging.getLogger(__name__)

HOUR = 3600


class Job(NamedTuple):
    name: str
    interval_s: float
    fns: tuple[Callable, ...]


# zadania z pamięcią procesu — każdy worker musi je robić sam (bez blokady w bazie)
PER_PROCESS_JOBS = {"monitor_sample"}
SKIPPED = object()   # _run: zadanie trwa w innym procesie/instancji — ten przebieg pominięty
# OBS-009: pętle uruchomione w TYM procesie: nazwa → (interwał s, nazwy funkcji, start pętli).
# Głęboki health check (routers/health.py) porównuje je z ostatnim udanym job_runs.
STARTED: dict[str, tuple[float, tuple[str, ...], datetime.datetime]] = {}


def split_jobs(all_jobs: list["Job"]) -> tuple[list["Job"], list["Job"]]:
    """(zadania każdego procesu, zadania tylko lidera) — BUILD-003, leader.py."""
    per_process = [j for j in all_jobs if j.name in PER_PROCESS_JOBS]
    return per_process, [j for j in all_jobs if j.name not in PER_PROCESS_JOBS]


def lock_key(name: str) -> int:
    """Stałe id advisory locka per zadanie (crc32 — identyczne w każdym procesie)."""
    return zlib.crc32(f"timporye.job:{name}".encode())


@contextmanager
def job_lock(name: str) -> Iterator[bool]:
    """ARCH-003: pg_try_advisory_lock na czas przebiegu → True = wolno biec.

    Lock sesyjny żyje na połączeniu, więc trzymamy WŁASNE połączenie przez cały
    przebieg i na nim zwalniamy (także przy wyjątku). Zerwane połączenie = koniec
    sesji PG = lock zwolniony przez serwer. SQLite (dev/testy): no-op, zawsze wolno.
    Chroni przed RÓWNOCZESNYM przebiegiem; dedup kolejnych przebiegów robią same
    funkcje (rekordy w bazie) — patrz docs/JEDNA-INSTANCJA.md."""
    if engine.dialect.name != "postgresql":
        yield True
        return
    key = lock_key(name)
    with engine.connect() as conn:
        got = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar())
        conn.commit()   # lock sesyjny przeżywa commit; bez tego „idle in transaction”
        try:
            yield got
        finally:
            if got:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                conn.commit()


def _run(fn: Callable, job_name: str = ""):
    if job_name and job_name not in PER_PROCESS_JOBS:
        with job_lock(job_name) as got:
            return _run_fn(fn) if got else SKIPPED
    return _run_fn(fn)


def _run_fn(fn: Callable):
    # commit po udanym przebiegu: zamknięcie sesji = rollback, więc zadanie, które
    # zapomni o commicie (np. pallet_urgent), gubiło powiadomienia in-app, a kanały
    # zewnętrzne leciały co cykl (dedup po nieistniejących rekordach niemożliwy)
    with SessionLocal() as db:
        result = fn(db)
        db.commit()
        return result


async def job_loop(job: Job) -> None:
    """Pierwszy przebieg zaraz po starcie, potem co interval_s; pętla nie umiera."""
    STARTED[job.name] = (job.interval_s, tuple(fn.__name__ for fn in job.fns), utcnow())
    while True:
        for fn in job.fns:
            started_at = utcnow()
            start = time.perf_counter()
            try:
                result = await asyncio.to_thread(_run, fn, job.name)
                if result is SKIPPED:
                    logger.info("Zadanie %s/%s pominięte — trwa w innym procesie",
                                job.name, fn.__name__)
                    continue
                if result:
                    logger.info("Zadanie %s/%s: %s", job.name, fn.__name__, result)
                applog.record_job(job=job.name, fn=fn.__name__, started_at=started_at,
                                  duration_ms=int((time.perf_counter() - start) * 1000),
                                  ok=True, detail=repr(result)[:2000] if result else "")
            except Exception:  # noqa: BLE001 — jedna funkcja nie ucisza reszty
                logger.exception("Zadanie %s/%s nie powiodło się", job.name, fn.__name__)
                applog.record_job(job=job.name, fn=fn.__name__, started_at=started_at,
                                  duration_ms=int((time.perf_counter() - start) * 1000),
                                  ok=False, detail=traceback.format_exc())
        await asyncio.sleep(job.interval_s)


def _congestion_job() -> Job:
    """Kongestia portów: near_port zasila kolektor AIS, więc job chodzi przy włączonym AIS."""
    from .tracking.congestion import check_congestion_alerts, record_port_congestion
    interval = max(0.5, settings.tracking_interval_hours) * HOUR
    return Job("congestion", interval, (record_port_congestion, check_congestion_alerts))


def _verify_backup_fn() -> Callable:
    """W14 #47: raz na dobę w dniu VERIFY_BACKUP_WEEKDAY (0=pon … 6=niedziela)."""
    from .backup_verify import verify_backup
    last_run_day: list[datetime.date | None] = [None]

    def verify_backup_weekly(_db):
        today = today_pl()
        if today.weekday() != settings.verify_backup_weekday or last_run_day[0] == today:
            return None
        last_run_day[0] = today
        return verify_backup().get("status")

    return verify_backup_weekly


def build_jobs(with_ais: bool = False) -> list[Job]:
    from .avizo_workflow import purge_driver_id_no, run_maintenance
    from .invoices.ingest import process_pending as process_pending_invoices
    from .orphan_files import quarantine_orphans
    from .routers.complaints import check_complaint_auto_drafts, check_complaint_reminders
    from .routers.driver import send_tomorrow_sms
    jobs = [
        Job("demurrage", 6 * HOUR, (check_demurrage_alerts,)),
        # odprawy + braki dokumentów + prognoza + milestone'y trackingu + auto-SMS
        # kierowców (gate ≥13:00 UTC w środku) + stęchłe importy (dedup w środku)
        Job("customs_delay", 6 * HOUR, (check_customs_alerts, check_docs_alerts,
                                        check_forecast_alerts, check_tracking_alerts,
                                        check_stale_import_alerts)),
        # przypomnienia SMS: godzina z panelu admina — sprawdzane co 15 min, żeby trzymać godzinę
        Job("sms_reminders", 15 * 60, (send_tomorrow_sms,)),
        # ARCH-004: wgrane faktury → cięcie, OCR, ekstrakcja poza wątkiem żądania HTTP
        Job("invoice_ingest", 30, (process_pending_invoices,)),
        # przypomnienia reklamacji + przedawnienia + auto-szkice z opóźnienia (W11 #67/#69)
        Job("complaints", 6 * HOUR, (check_complaint_reminders, check_complaint_auto_drafts)),
        Job("pallet_urgent", settings.pallet_alert_interval_hours * HOUR,
            (check_pallet_urgent_alerts,)),
        # okno poniedziałek 6-7 UTC i dedup per user/dzień siedzą w funkcji — poll co 20 min
        # (przy 24 h okno 1 h było trafiane tylko przypadkiem = digest praktycznie nie szedł)
        Job("weekly_digest", 20 * 60, (check_weekly_digest_alerts,)),
        Job("verify_backup", 6 * HOUR, (_verify_backup_fn(),)),
        # okno DIGEST_HOUR (czas PL) + dedup per user/dzień w funkcji
        Job("daily_digest", 20 * 60, (check_daily_digest_alerts,)),
        # wygasłe linki → EXPIRED, dostarczone → CLOSED, anonimizacja danych kierowców;
        # nr dokumentu kierowcy czyszczony 30 dni po ZREALIZOWANY (D8)
        Job("avizo_maintenance", 24 * HOUR, (run_maintenance, purge_driver_id_no)),
        # pliki dokumentów bez wiersza w bazie → uploads/_osierocone (spec dokumenty-dostaw §4 pkt 37)
        Job("orphan_files", 24 * HOUR, (quarantine_orphans,)),
        # monitor serwera: próbka CPU/RAM do historii panelu admina (pamięć procesu, 24 h)
        Job("monitor_sample", 60, (monitoring.sample,)),
        # dziennik serwera: retencja 30 dni dla request_logs/job_runs/request_counters;
        # log logowań (audit_log auth) po AUDIT_AUTH_RETENTION_DAYS (GDPR-004); wygasłe tokeny,
        # historia SMS, błędy JS (OBS-011/GDPR-007), stan limitera logowań (ARCH-003),
        # przeczytane powiadomienia (OBS-011)
        Job("applog_retention", 24 * HOUR, (applog.purge, applog.purge_auth_audit,
                                            retention.purge_expired_tokens,
                                            retention.purge_sms_messages,
                                            retention.purge_client_errors,
                                            retention.purge_login_failures,
                                            purge_read_notifications)),
    ]
    from . import sharepoint
    # bez kompletu SHAREPOINT_* albo bez SHAREPOINT_AUTO_SYNC job nie powstaje (domyślnie ręcznie)
    if sharepoint.is_configured() and settings.sharepoint_auto_sync:
        jobs.append(Job("sharepoint_queue", settings.sharepoint_queue_interval_minutes * 60,
                        (sharepoint.sharepoint_queue_sync,)))
    if with_ais:
        jobs.append(_congestion_job())
    return jobs

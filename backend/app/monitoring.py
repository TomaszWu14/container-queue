"""Monitor wydajności i pojemności serwera (panel admina, 2026-09-24).

Bez nowych zależności: Linux wystawia wszystko w /proc i /sys/fs/cgroup (stdlib wystarcza).
Aplikacja chodzi w kontenerze Dockera: /proc/stat, /proc/meminfo i loadavg pokazują CAŁY
host, a cgroup — limit i zużycie samego kontenera. Poza Linuksem (dev na Windows) pola = None.

Historia: pierścień próbek w pamięci procesu (1/min, 24 h) — jeden proces uvicorn, więc
wystarcza; po restarcie historia startuje od zera.
ponytail: pamięć procesu; tabela w DB, gdy potrzebna historia dłuższa niż doba/po restarcie.
"""
import collections
import logging
import os
import pathlib
import shutil
import threading
import time

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import monitoring_mem
from .config import settings
from .models import utcnow

logger = logging.getLogger(__name__)
_cpu_prev: tuple[int, int] | None = None     # (busy, total) z poprzedniego odczytu /proc/stat
_cpu_lock = threading.Lock()
HISTORY: collections.deque = collections.deque(maxlen=24 * 60)


def _read(path: str) -> str | None:
    try:
        return pathlib.Path(path).read_text()
    except OSError:
        return None


def cpu_percent() -> float | None:
    """Zajętość CPU hosta od poprzedniego odczytu (pierwszy odczyt = od startu systemu)."""
    global _cpu_prev
    raw = _read("/proc/stat")
    if not raw:
        return None
    vals = [int(v) for v in raw.splitlines()[0].split()[1:]]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)   # idle + iowait
    total = sum(vals)
    with _cpu_lock:
        prev, _cpu_prev = _cpu_prev, (total - idle, total)
    busy, total_now = total - idle, total
    if prev and total_now > prev[1]:
        return round(100 * (busy - prev[0]) / (total_now - prev[1]), 1)
    return round(100 * busy / total, 1) if total else None


def memory() -> dict | None:
    raw = _read("/proc/meminfo")
    if not raw:
        return None
    kb = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in raw.splitlines() if ":" in ln)}
    total, avail = kb.get("MemTotal", 0), kb.get("MemAvailable", kb.get("MemFree", 0))
    return {"total_mb": total // 1024, "used_mb": (total - avail) // 1024,
            "percent": round(100 * (total - avail) / total, 1) if total else None,
            "breakdown": monitoring_mem.breakdown(kb)}


def container_memory() -> dict | None:
    """cgroup v2 (Docker): zużycie i limit pamięci samego kontenera aplikacji."""
    cur = _read("/sys/fs/cgroup/memory.current")
    if cur is None:
        return None
    limit = (_read("/sys/fs/cgroup/memory.max") or "max").strip()
    return {"used_mb": int(cur) // 1_048_576,
            "limit_mb": None if limit == "max" else int(limit) // 1_048_576}


def process_rss_mb() -> int | None:
    raw = _read("/proc/self/status")
    for ln in (raw or "").splitlines():
        if ln.startswith("VmRSS:"):
            return int(ln.split()[1]) // 1024
    return None


def load_avg() -> list[float] | None:
    getloadavg = getattr(os, "getloadavg", None)   # brak na Windows (też dla mypy)
    if getloadavg is None:
        return None
    try:
        return [round(x, 2) for x in getloadavg()]
    except OSError:
        return None


def disks() -> list[dict]:
    out, seen = [], set()
    for label, path in (("system", "/"), ("załączniki", settings.uploads_dir),
                        ("kopie zapasowe", settings.backup_dir)):
        try:
            u = shutil.disk_usage(path)
        except OSError:
            continue
        key = (u.total, u.used)   # ten sam system plików pod kilkoma ścieżkami = jeden wiersz
        if key in seen:
            continue
        seen.add(key)
        out.append({"label": label, "path": path, "total_gb": round(u.total / 1e9, 1),
                    "used_gb": round(u.used / 1e9, 1), "free_gb": round(u.free / 1e9, 1),
                    "percent": round(100 * u.used / u.total, 1) if u.total else None})
    return out


def database(db: Session) -> dict:
    """Rozmiar bazy, największe tabele i połączenia (Postgres); SQLite = rozmiar pliku."""
    try:
        if db.bind.dialect.name == "postgresql":
            size = db.scalar(text("SELECT pg_database_size(current_database())"))
            tables = db.execute(text(
                "SELECT c.relname, pg_total_relation_size(c.oid), c.reltuples::bigint "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relkind = 'r' AND n.nspname = 'public' "
                "ORDER BY 2 DESC LIMIT 10")).all()
            conns = db.scalar(text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"))
            return {"engine": "postgresql", "size_mb": round(size / 1_048_576, 1), "connections": conns,
                    "tables": [{"name": n, "size_mb": round(s / 1_048_576, 2), "rows": max(r, 0)}
                               for n, s, r in tables]}
        path = db.bind.url.database or ""
        size = os.path.getsize(path) if path and os.path.exists(path) else 0
        return {"engine": db.bind.dialect.name, "size_mb": round(size / 1_048_576, 1),
                "connections": None, "tables": []}
    except Exception as exc:  # noqa: BLE001 — metryka pomocnicza nie wywala panelu
        logger.warning("monitor: metryki bazy niedostępne", exc_info=True)
        return {"engine": db.bind.dialect.name, "error": str(exc)[:200]}


def sample(_db=None) -> None:
    """Próbka do historii (zadanie tła co minutę). Sygnatura (db) jak inne zadania jobs.py."""
    mem = memory()
    HISTORY.append({"at": utcnow().isoformat(timespec="seconds"), "cpu": cpu_percent(),
                    "mem": mem["percent"] if mem else None, "rss_mb": process_rss_mb()})


def snapshot(db: Session, started: float) -> dict:
    return {
        "at": utcnow().isoformat(timespec="seconds"),
        "uptime_s": round(time.monotonic() - started),
        "cpu_percent": cpu_percent(), "cpu_count": os.cpu_count(), "load_avg": load_avg(),
        "memory": memory(), "container_memory": container_memory(),
        "process_rss_mb": process_rss_mb(), "threads": threading.active_count(),
        "processes": monitoring_mem.top_processes(),
        "disks": disks(), "database": database(db), "history": list(HISTORY),
    }

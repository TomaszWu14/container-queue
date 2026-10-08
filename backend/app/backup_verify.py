"""W14 #47: weryfikacja kopii zapasowej — odtworzenie najnowszego dumpu do bazy
tymczasowej i porównanie liczby wierszy kluczowych tabel z bazą źródłową.

Postgres-only (na prodzie); lokalnie na SQLite zwraca skip z komunikatem.
Wynik ostatniego przebiegu trzymany w pamięci procesu — panel System go pokazuje.
"""
import datetime
import gzip
import logging
import pathlib
import subprocess  # nosec B404 — psql z obrazu, argumenty stałe
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from .config import settings

logger = logging.getLogger(__name__)

KEY_TABLES = ("users", "containers", "orders", "audit_log", "refresh_tokens")

# wynik ostatniej weryfikacji (dict) — panel System; proces-lokalne, wystarczające
last_result: dict | None = None


def _newest_dump() -> pathlib.Path | None:
    backup_dir = pathlib.Path(settings.backup_dir)
    # .age = kopia zaszyfrowana (BACKUP_AGE_RECIPIENT, BACKUP-007); nazwa zaczyna się datą
    dumps = sorted([*backup_dir.glob("timporye-*.sql.gz"), *backup_dir.glob("timporye-*.sql.gz.age")],
                   key=lambda p: p.name, reverse=True)
    return dumps[0] if dumps else None


def _count_rows(url, tables) -> dict[str, int | None]:
    eng = create_engine(url)
    out: dict[str, int | None] = {}
    try:
        with eng.connect() as conn:
            for table in tables:
                try:
                    out[table] = conn.execute(
                        text(f"SELECT COUNT(*) FROM {table}")).scalar()  # nosec B608 — stałe nazwy
                except Exception:  # noqa: BLE001 — brak tabeli w dumpie = None
                    logger.warning("verify_backup: COUNT(%s) niedostępny", table, exc_info=True)
                    out[table] = None
    finally:
        eng.dispose()
    return out


def verify_backup() -> dict:
    """Przebieg weryfikacji; wynik do loga + notyfikacja adminów przy błędzie."""
    global last_result
    started = datetime.datetime.now(datetime.UTC).isoformat()
    result = {"started_at": started, "status": "error", "detail": ""}
    try:
        url = make_url(settings.database_url)
        if not url.drivername.startswith("postgresql"):
            result.update(status="skip",
                          detail="Baza nie jest Postgresem (dev/SQLite) — weryfikacja pominięta.")
            last_result = result
            logger.info("verify_backup: %s", result["detail"])
            return result
        dump = _newest_dump()
        if dump is None:
            result.update(detail=f"Brak plików kopii w {settings.backup_dir}.")
            raise RuntimeError(result["detail"])
        # stara kopia = backup nie działa, nawet jeśli sama się odtwarza (audyt BACKUP-005)
        age_h = (time.time() - dump.stat().st_mtime) / 3600
        if age_h > settings.backup_max_age_hours:
            result.update(dump=dump.name,
                          detail=f"Najnowsza kopia {dump.name} ma {age_h:.0f} h (limit "
                                 f"{settings.backup_max_age_hours} h) — harmonogram backupu nie działa?")
            raise RuntimeError(result["detail"])
        if dump.name.endswith(".age"):
            # klucz prywatny celowo NIE leży na serwerze — próbne odtworzenie robi się poza nim
            result.update(status="skip", dump=dump.name,
                          detail="Kopia zaszyfrowana (age) i świeża — próbne odtworzenie tylko "
                                 "poza serwerem, z kluczem prywatnym (docs/BACKUPY.md).")
            last_result = result
            logger.info("verify_backup: %s", result["detail"])
            return result
        temp_db = "timporye_verify"
        admin_url = url.set(database="postgres", drivername="postgresql")
        admin_eng = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_eng.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{temp_db}"'))
            conn.execute(text(f'CREATE DATABASE "{temp_db}"'))
        admin_eng.dispose()
        temp_url = url.set(database=temp_db, drivername="postgresql")
        try:
            with gzip.open(dump, "rb") as fh:
                proc = subprocess.run(  # nosec B603 B607 — psql z obrazu, URL z configu
                    ["psql", "--quiet", "--no-psqlrc", "-v", "ON_ERROR_STOP=1",
                     temp_url.render_as_string(hide_password=False)],
                    stdin=fh, capture_output=True, timeout=1800)
            if proc.returncode != 0:
                raise RuntimeError(f"psql restore rc={proc.returncode}: "
                                   f"{proc.stderr[-500:].decode(errors='replace')}")
            original = _count_rows(settings.database_url, KEY_TABLES)
            restored = _count_rows(temp_url, KEY_TABLES)
        finally:
            admin_eng = create_engine(admin_url, isolation_level="AUTOCOMMIT")
            with admin_eng.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{temp_db}"'))
            admin_eng.dispose()
        mismatched = [t for t in KEY_TABLES
                      if restored.get(t) is None
                      or original.get(t) is None
                      # kopia jest starsza od bazy — dopuszczamy, że baza urosła,
                      # ale odtworzone nie może być większe ani puste przy niepustym oryginale
                      or restored[t] > original[t]
                      or (original[t] > 0 and restored[t] == 0)]
        result.update(status="ok" if not mismatched else "error",
                      dump=dump.name, tables={t: {"original": original.get(t),
                                                  "restored": restored.get(t)}
                                              for t in KEY_TABLES},
                      detail="OK" if not mismatched
                      else f"Rozjazd liczby wierszy: {', '.join(mismatched)}")
        if mismatched:
            raise RuntimeError(result["detail"])
        logger.info("verify_backup OK: %s (%s)", dump.name, result["tables"])
    except Exception as exc:  # noqa: BLE001 — wynik + alert, pętla nie może paść
        result["detail"] = result["detail"] or str(exc)
        logger.error("verify_backup FAILED: %s", exc)
        _notify_admins_failure(result["detail"])
    last_result = result
    return result


def _notify_admins_failure(detail: str) -> None:
    try:
        from sqlalchemy import select

        from .database import SessionLocal
        from .models import Role, User
        from .notifications import notify
        with SessionLocal() as db:
            admins = db.scalars(select(User).where(
                User.role == Role.admin, User.is_active.is_(True))).all()
            notify(db, admins, kind="backup_verify_failed",
                   title="Weryfikacja backupu NIE powiodła się",
                   body=detail[:500])
            db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("verify_backup: nie udało się powiadomić adminów")


if __name__ == "__main__":  # użycie ręczne: python -m app.backup_verify
    out = verify_backup()
    print(out)
    raise SystemExit(0 if out["status"] in ("ok", "skip") else 1)

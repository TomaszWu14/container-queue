"""Kopie zapasowe (audyt BACKUP-003, BACKUP-005): błąd pg_dump nie może dać „udanej” kopii,
załączniki są archiwizowane, a weryfikacja nie przepuszcza starej kopii ani błędów SQL."""
import datetime as dt
import inspect
import os
import pathlib
import shutil
import subprocess  # nosec B404
import time

import pytest

from app import backup_verify
from app.config import settings

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "backup.sh"


def test_verify_rejects_stale_dump(tmp_path, monkeypatch):
    old = tmp_path / "timporye-20260901-020000.sql.gz"
    old.write_bytes(b"x")
    stale = time.time() - 200 * 3600   # starsza niż tydzień + zapas (194 h)
    os.utime(old, (stale, stale))
    monkeypatch.setattr(settings, "database_url", "postgresql://u:p@127.0.0.1:1/nie-ma")
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path))
    monkeypatch.setattr(backup_verify, "_notify_admins_failure", lambda detail: None)
    out = backup_verify.verify_backup()   # błąd PRZED jakimkolwiek połączeniem z bazą
    assert out["status"] == "error" and "limit 194 h" in out["detail"]


def test_verify_restore_stops_on_sql_error():
    assert "ON_ERROR_STOP=1" in inspect.getsource(backup_verify.verify_backup)


def _posix(path) -> str:
    # Git Bash na Windows: GNU tar czyta „C:\…” jako host:ścieżka — podajemy /c/…; na Linuksie bez zmian
    p = str(path)
    return "/" + p[0].lower() + p[2:].replace("\\", "/") if os.name == "nt" and p[1:2] == ":" else p


def _run_backup(tmp_path, pg_dump_body: str, **extra_env):
    sh = shutil.which("sh")
    if not sh:
        pytest.skip("brak sh")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "pg_dump"
    fake.write_text("#!/bin/sh\n" + pg_dump_body + "\n", newline="\n")
    fake.chmod(0o755)
    script = tmp_path / "backup.sh"   # kopia z LF (checkout na Windows może mieć CRLF)
    script.write_bytes(SCRIPT.read_bytes().replace(b"\r\n", b"\n"))
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "1_abc_faktura.pdf").write_bytes(b"%PDF")
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
           "DATABASE_URL": "postgresql+psycopg2://u:p@db/x", "BACKUP_DIR": _posix(tmp_path / "b"),
           "UPLOADS_DIR": _posix(uploads), **extra_env}
    proc = subprocess.run([sh, str(script)], env=env, capture_output=True, text=True)  # nosec
    return proc, tmp_path / "b"


def test_backup_fails_loudly_when_pg_dump_fails(tmp_path):
    proc, out = _run_backup(tmp_path, "echo 'CREATE TABLE czesc'; exit 3")
    assert proc.returncode != 0
    assert not list(out.glob("timporye-*.sql.gz"))   # żadnej uciętej „udanej” kopii


def test_backup_writes_dump_and_uploads_archive(tmp_path):
    proc, out = _run_backup(tmp_path, "echo 'SELECT 1;'")
    assert proc.returncode == 0, proc.stderr
    assert len(list(out.glob("timporye-*.sql.gz"))) == 1
    assert len(list(out.glob("uploads-*.tar.gz"))) == 1


def test_backup_pings_monitor_after_success(tmp_path):
    """Heartbeat (OBS-001): udana kopia woła BACKUP_PING_URL; nieudana — nie."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    hits = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/push/abc"
    (tmp_path / "ok").mkdir()
    (tmp_path / "bad").mkdir()
    try:
        ok, _ = _run_backup(tmp_path / "ok", "echo 'SELECT 1;'", BACKUP_PING_URL=url)
        bad, _ = _run_backup(tmp_path / "bad", "exit 3", BACKUP_PING_URL=url)
    finally:
        server.shutdown()
    assert ok.returncode == 0 and bad.returncode != 0
    assert hits == ["/push/abc"]


def test_backup_skip_uploads_dumps_only_database(tmp_path):
    """Kopia co 8 h: sama baza; załączniki archiwizuje tylko zadanie nocne."""
    proc, out = _run_backup(tmp_path, "echo 'SELECT 1;'", BACKUP_SKIP_UPLOADS="1")
    assert proc.returncode == 0, proc.stderr
    assert len(list(out.glob("timporye-*.sql.gz"))) == 1
    assert not list(out.glob("uploads-*.tar.gz"))


def test_retention_keeps_daily_weekly_monthly(tmp_path):
    """BACKUP-008: poza N najnowszymi zostaje najnowsza kopia z 8 tygodni i 12 miesięcy (GFS)."""
    sh = shutil.which("sh")
    if not sh:
        pytest.skip("brak sh")
    b = tmp_path / "b"
    b.mkdir()
    start = dt.datetime(2025, 8, 1, 6)
    stamps = [start + dt.timedelta(days=7 * i + (i % 3)) for i in range(60)]  # ~14 miesięcy
    for s in stamps:
        (b / f"timporye-{s:%Y%m%d-%H%M%S}.sql.gz").write_bytes(b"")
    (b / "uploads-20250801-060000.tar.gz").write_bytes(b"")   # nie kopia bazy — nie ruszamy

    newest_first = sorted(stamps, reverse=True)
    expected = set(newest_first[:3])
    for key, limit in ((lambda s: s.isocalendar()[:2], 8), (lambda s: (s.year, s.month), 12)):
        seen: list = []
        for s in newest_first:
            if key(s) not in seen and len(seen) < limit:
                seen.append(key(s))
                expected.add(s)
    script = tmp_path / "backup.sh"
    script.write_bytes(SCRIPT.read_bytes().replace(b"\r\n", b"\n"))
    env = {**os.environ, "BACKUP_DIR": _posix(b), "BACKUP_KEEP": "3"}
    env.pop("DATABASE_URL", None)   # sama retencja nie potrzebuje bazy
    proc = subprocess.run([sh, str(script), "--retencja"], env=env,
                          capture_output=True, text=True)  # nosec
    assert proc.returncode == 0, proc.stderr
    left = {p.name for p in b.glob("timporye-*.sql.gz")}
    assert left == {f"timporye-{s:%Y%m%d-%H%M%S}.sql.gz" for s in expected}
    assert 12 < len(left) < 30
    assert (b / "uploads-20250801-060000.tar.gz").exists()

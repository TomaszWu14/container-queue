"""Audyt BACKUP-007: opcjonalne szyfrowanie kopii kluczem publicznym age (BACKUP_AGE_RECIPIENT).
Bez zmiennej — zachowanie bez zmian (test_backup_scripts). Z nią: na dysku tylko pliki .age,
nieczytelne bez klucza prywatnego (który NIE leży na serwerze); retencja, świeżość kopii
i restore.sh rozumieją .age."""
import gzip
import os
import pathlib
import shutil
import subprocess  # nosec B404
import time

import pytest

from app import backup_verify
from app.config import settings
from tests.test_backup_scripts import _posix, _run_backup

RESTORE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "restore.sh"

needs_age = pytest.mark.skipif(not (shutil.which("age") and shutil.which("age-keygen")),
                               reason="brak programu age w systemie")


def _keypair(tmp_path) -> tuple[pathlib.Path, str]:
    identity = tmp_path / "klucz.txt"
    subprocess.run(["age-keygen", "-o", str(identity)], check=True,  # nosec
                   capture_output=True)
    public = next(line.split(": ", 1)[1] for line in identity.read_text().splitlines()
                  if line.startswith("# public key: "))
    return identity, public


@needs_age
def test_backup_encrypted_with_recipient(tmp_path):
    identity, public = _keypair(tmp_path)
    proc, out = _run_backup(tmp_path, "echo 'SELECT 1;'", BACKUP_AGE_RECIPIENT=public)
    assert proc.returncode == 0, proc.stderr
    assert not list(out.glob("*.sql.gz")) and not list(out.glob("*.tar.gz"))   # zero jawnych
    dump = next(out.glob("timporye-*.sql.gz.age"))
    assert len(list(out.glob("uploads-*.tar.gz.age"))) == 1
    with pytest.raises(OSError):
        gzip.decompress(dump.read_bytes())            # bez klucza — nieczytelne
    plain = subprocess.run(["age", "-d", "-i", str(identity), str(dump)],  # nosec
                           check=True, capture_output=True).stdout
    assert gzip.decompress(plain).strip() == b"SELECT 1;"


def test_backup_fails_loudly_when_age_unavailable(tmp_path):
    bindir = tmp_path / "agebin"
    bindir.mkdir()
    fake = bindir / "age"
    fake.write_text("#!/bin/sh\necho 'age: błąd' >&2\nexit 1\n", newline="\n")
    fake.chmod(0o755)
    proc, out = _run_backup(tmp_path, "echo 'SELECT 1;'", BACKUP_AGE_RECIPIENT="age1zly",
                            PATH=f"{bindir}{os.pathsep}{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    assert proc.returncode != 0
    assert not out.exists() or not [p for p in out.iterdir() if not p.name.endswith(".part")]


def test_newest_encrypted_dump_counts_for_freshness_and_skips_restore(tmp_path, monkeypatch):
    (tmp_path / "timporye-20260101-060000.sql.gz").write_bytes(b"x")
    enc = tmp_path / "timporye-20260928-060000.sql.gz.age"
    enc.write_bytes(b"age-encryption.org/v1")
    old = time.time() - 300 * 3600
    os.utime(tmp_path / "timporye-20260101-060000.sql.gz", (old, old))
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path))
    monkeypatch.setattr(settings, "database_url", "postgresql://u:p@127.0.0.1:1/nie-ma")
    monkeypatch.setattr(backup_verify, "_notify_admins_failure", lambda detail: None)
    assert backup_verify._newest_dump() == enc
    out = backup_verify.verify_backup()     # świeża, ale zaszyfrowana — bez próby odtworzenia
    assert out["status"] == "skip" and "zaszyfrowana" in out["detail"]


def test_restore_encrypted_requires_identity(tmp_path):
    sh = shutil.which("sh")
    if not sh:
        pytest.skip("brak sh")
    dump = tmp_path / "timporye-20260928-060000.sql.gz.age"
    dump.write_bytes(b"age-encryption.org/v1")
    env = {**os.environ, "DATABASE_URL": "postgresql://u:p@db/x"}
    env.pop("BACKUP_AGE_IDENTITY", None)
    proc = subprocess.run([sh, str(RESTORE), _posix(dump), "--force"], env=env,  # nosec
                          capture_output=True, text=True)
    assert proc.returncode != 0 and "BACKUP_AGE_IDENTITY" in proc.stdout + proc.stderr


@needs_age
def test_restore_decrypts_with_identity(tmp_path):
    identity, public = _keypair(tmp_path)
    _, out = _run_backup(tmp_path, "echo 'SELECT 42;'", BACKUP_AGE_RECIPIENT=public)
    dump = next(out.glob("timporye-*.sql.gz.age"))
    fake_bin = tmp_path / "psqlbin"
    fake_bin.mkdir()
    captured = tmp_path / "psql-stdin.sql"
    (fake_bin / "psql").write_text(f"#!/bin/sh\ncat > '{_posix(captured)}'\n", newline="\n")
    (fake_bin / "psql").chmod(0o755)
    env = {**os.environ, "DATABASE_URL": "postgresql://u:p@db/x",
           "BACKUP_AGE_IDENTITY": str(identity),
           "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}
    proc = subprocess.run([shutil.which("sh"), str(RESTORE), _posix(dump), "--force"],  # nosec
                          env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert captured.read_text().strip() == "SELECT 42;"

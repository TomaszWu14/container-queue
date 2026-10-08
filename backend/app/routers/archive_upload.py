"""Archiwum ZIP wgrane do kontenera (2026-10-06): rozpakowane jak „Wgraj folder zamówienia” —
PDF-y do paczki faktur (splitter rozpozna CI / PL / PI / B/L / inne), reszta do załączników.
Sam ZIP nie jest przechowywany (czarna skrzynka bez kafelków)."""
import io
import pathlib
import secrets
import zipfile
import zlib

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..deps import forwarder_may_see
from ..document_gate import CONFLICT, UNREADABLE, check_pdf, digest, duplicate_reason
from ..database import get_db
from ..deps import NonWarehouseViewers as non_warehouse
from ..models import Attachment, Role, User
from ..notifications import container_watchers, notify
from .containers import get_container_checked
from .forwarding_files import allowed_extensions, read_upload_capped, safe_filename, uploads_dir
from .invoices import _ingest, _resolve_supplier, _stored, _validate_pdf

router = APIRouter(prefix="/api", tags=["dokumenty"])

# anty zip-bomba: suma rozmiarów po rozpakowaniu (jak skoroszyty w tabular.py)
MAX_UNCOMPRESSED_MB = 200
_ARCHIVES = (".zip", ".7z", ".rar", ".tar", ".gz")
_SYSTEM = ("__macosx/", "thumbs.db", "desktop.ini", ".ds_store")
_INVOICE_ROLES = (Role.admin, Role.logistics, Role.purchasing)   # jak PurchasingReaders


def unpack(content: bytes) -> tuple[str, list[tuple[str, bytes]], list[str]]:
    """(folder, [(nazwa, bajty)], pominięte). Folder = katalog nadrzędny (numer zamówienia)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie udało się otworzyć archiwum ZIP.") from exc
    with archive:
        infos = [i for i in archive.infolist() if not i.is_dir()
                 and not any(m in i.filename.lower() for m in _SYSTEM)]
        if len(infos) > settings.archive_zip_max_files:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                f"Archiwum ma ponad {settings.archive_zip_max_files} plików.")
        if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_MB * 1024 * 1024:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                f"Archiwum po rozpakowaniu przekracza {MAX_UNCOMPRESSED_MB} MB.")
        dirs = {pathlib.PurePosixPath(i.filename).parts[0] for i in infos if "/" in i.filename}
        folder = dirs.pop() if len(dirs) == 1 else ""
        max_bytes = settings.max_upload_mb * 1024 * 1024
        files, skipped = [], []
        for info in infos:
            name = safe_filename(info.filename)
            if name.startswith(("~$", ".")):
                skipped.append(f"{name} (plik tymczasowy/systemowy)")
                continue
            ext = pathlib.PurePath(name).suffix.lower()
            if ext in _ARCHIVES:
                skipped.append(f"{name} (archiwum w archiwum)")
            elif ext.lstrip(".") not in allowed_extensions():
                skipped.append(f"{name} (niedozwolony typ)")
            elif info.file_size > max_bytes:
                skipped.append(f"{name} (ponad {settings.max_upload_mb} MB)")
            else:
                try:
                    with archive.open(info) as fh:
                        files.append((name, fh.read(max_bytes)))   # nie więcej niż limit
                except (RuntimeError, NotImplementedError, zipfile.BadZipFile, EOFError, zlib.error):
                    # hasło, nieobsługiwana kompresja (deflate64), zła suma CRC — §4 pkt 5
                    skipped.append(f"{name} (zaszyfrowany albo uszkodzony w archiwum)")
    return folder, files, skipped


@router.post("/containers/{container_id}/archive", status_code=201)
def upload_archive(container_id: int, file: UploadFile, db: Session = Depends(get_db),
                   user: User = non_warehouse) -> dict:
    container = get_container_checked(db, container_id, user)
    content = read_upload_capped(file, settings.max_upload_mb, label="Archiwum")
    folder, files, skipped = unpack(content)
    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "W archiwum nie ma plików do wgrania." + (
                                f" Pominięte: {'; '.join(skipped)}" if skipped else ""))
    to_invoices = user.role in _INVOICE_ROLES
    # bramki jak przy zwykłym uploadzie (spec 2026-10-06 §4 pkt 6, 15): dubel w kontenerze,
    # w paczce faktur i w SAMYM archiwum; PDF-y do załączników (role bez faktur) przez check_pdf
    fresh, seen = [], set()
    for name, data in files:
        sha = digest(data)
        is_pdf = name.lower().endswith(".pdf")
        dup = None if sha in seen else duplicate_reason(db, container_id, data, uploads_dir())
        gate = check_pdf(data, container.container_no) if is_pdf and not to_invoices else None
        if sha in seen:
            skipped.append(f"{name} (powtórzony w archiwum)")
        elif dup is not None:
            skipped.append(f"{name} ({dup})")
        elif gate and gate["status"] in (UNREADABLE, CONFLICT):
            skipped.append(f"{name} ({gate['message']})")
        else:
            fresh.append((name, data))
        seen.add(sha)
    files = fresh
    pdfs: list[tuple[str, bytes]] = []
    others: list[tuple[str, bytes]] = []
    for name, data in files:
        if to_invoices and name.lower().endswith(".pdf"):
            try:
                _validate_pdf(name, data)
            except HTTPException as exc:
                skipped.append(f"{name} ({exc.detail})")
                continue
            pdfs.append((name, data))
        else:
            others.append((name, data))

    # paczka faktur najpierw (sama commituje albo kolejkuje cięcie/OCR w tle) — zły PDF (422)
    # nie zostawia wtedy połowy archiwum w załącznikach
    batch_id = None
    if pdfs:
        supplier = _resolve_supplier(db, container, None)
        saved = [(name, _stored(container_id, name), data) for name, data in pdfs]
        batch, _ = _ingest(db, container, supplier, saved, uploads_dir(), user)
        batch_id = batch.id

    written: list[pathlib.Path] = []
    try:
        added = []
        for name, data in others:
            stored = f"{container_id}_{secrets.token_hex(8)}_{name}"
            (uploads_dir() / stored).write_bytes(data)
            written.append(uploads_dir() / stored)
            att = Attachment(container_id=container_id, filename=name, stored_name=stored,
                             content_type="", size=len(data), sha256=digest(data), uploaded_by_id=user.id)
            db.add(att)
            added.append(att)
        if others:
            audit.record(db, entity_type="containers", entity_id=container_id, field="attachment_upload",
                         old_value=None, new_value=f"{safe_filename(file.filename)} ({len(others)} plików)",
                         user=user, note=", ".join(n for n, _ in others)[:500])
            notify(db, [u for u in container_watchers(db, container)
                        if any(forwarder_may_see(a, u) for a in added)],
                   kind="file", title=f"Nowe pliki przy {container.container_no}: "
                                      f"{safe_filename(file.filename)} ({len(others)})",
                   container_id=container_id, exclude_user_id=user.id)
        db.commit()
    except BaseException:
        db.rollback()
        for path in written:
            path.unlink(missing_ok=True)
        raise

    return {"folder": folder, "pdfs": len(pdfs), "attachments": len(others),
            "skipped": skipped, "batch_id": batch_id}

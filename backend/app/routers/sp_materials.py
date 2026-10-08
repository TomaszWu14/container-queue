"""Dane materiałowe SharePoint: import pliku (wszystkie zakładki) i podgląd tabel.

Import pełnego pliku (~15 MB, ~218 tys. wierszy) trwa na 1-rdzeniowym serwerze dłużej niż
30 s limitu żądania w przeglądarce (2026-09-29: „Przekroczono czas oczekiwania”) — biegnie więc
w wątku tła; stan w `SapImport.counts["status"]` (running / done / error), front odpytuje
/import-status. Bez pętli tła (RUN_BACKGROUND_JOBS=false, testy) — w żądaniu."""
import datetime
import logging
import threading

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record
from ..config import settings
from ..database import SessionLocal, get_db
from ..deps import Editors as editors
from ..deps import GlobalDataEditors as global_editors
from ..importers import sp_materials as sp
from ..models import SapImport, SpMaterialRow, SpMaterialSheet, User, utcnow
from .forwarding import read_upload_capped

router = APIRouter(prefix="/api", tags=["dane materiałowe"])
logger = logging.getLogger(__name__)
KIND = "sp_materials"
# wątek padł razem z procesem (restart/deploy) = „running” na zawsze; po tym czasie → błąd
STALE_AFTER = datetime.timedelta(minutes=20)


def _run(import_id: int, content: bytes, filename: str) -> None:
    with SessionLocal() as db:
        job = db.get(SapImport, import_id)
        if job is None:   # wpis zadania skasowany zanim wątek ruszył — nie ma czego raportować
            return
        try:
            sheets = sp.parse(content)
            counts = {"sheets": [{"name": s["name"], "rows": len(s["rows"])} for s in sheets],
                      **sp.apply_materials(db, sheets, dry_run=False)}
            sp.store(db, sheets, filename, job.user_id)
            user = db.get(User, job.user_id) if job.user_id else None
            record(db, entity_type="sp_materials", entity_id=0, field="import", old_value=None,
                   new_value=f"{len(sheets)} zakładek, {sum(len(s['rows']) for s in sheets)} wierszy",
                   user=user, note=f"import danych materiałowych SharePoint ({filename})")
            job.counts = {**counts, "status": "done"}
            db.commit()
        except Exception as exc:  # noqa: BLE001 — błąd importu = stan zadania, nie cichy wątek
            db.rollback()
            logger.warning("import danych materiałowych %s padł", filename, exc_info=True)
            failed = db.get(SapImport, import_id)
            if failed is not None:
                detail = getattr(exc, "detail", None) or "Nie udało się zaimportować pliku."
                failed.counts, failed.errors = {"status": "error"}, [{"reason": str(detail)[:300]}]
                db.commit()


@router.post("/import/sp-materials")
def import_sp_materials(file: UploadFile, dry_run: bool = Query(default=True),
                        db: Session = Depends(get_db), user: User = global_editors) -> dict:
    content = read_upload_capped(file, settings.max_upload_mb, "Plik danych materiałowych")
    filename = file.filename or ""
    if dry_run:
        sheets = sp.parse(content)
        return {"dry_run": True, "counts": {
            "sheets": [{"name": s["name"], "rows": len(s["rows"])} for s in sheets],
            **sp.apply_materials(db, sheets, dry_run=True)}}
    running = _latest(db)
    if running and _state(running) == "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "Import tego pliku już trwa — poczekaj na koniec.")
    job = SapImport(kind=KIND, filename=filename[:255], user_id=user.id,
                    counts={"status": "running"}, errors=[])
    db.add(job)
    db.commit()
    if settings.run_background_jobs:
        threading.Thread(target=_run, args=(job.id, content, filename), daemon=True,
                         name=f"sp-materials-{job.id}").start()
    else:
        _run(job.id, content, filename)
    db.refresh(job)
    return {"dry_run": False, **_status(job)}


def _latest(db: Session) -> SapImport | None:
    return db.scalar(select(SapImport).where(SapImport.kind == KIND)
                     .order_by(SapImport.id.desc()).limit(1))


def _state(job: SapImport) -> str:
    state = (job.counts or {}).get("status", "done")
    if state == "running" and job.created_at and utcnow() - job.created_at > STALE_AFTER:
        return "error"
    return state


def _status(job: SapImport | None) -> dict:
    if job is None:
        return {"status": "none"}
    state = _state(job)
    errors = job.errors or ([{"reason": "Import przerwany (restart serwera) — wgraj plik ponownie."}]
                            if state == "error" else [])
    return {"status": state, "import_id": job.id, "filename": job.filename,
            "started_at": job.created_at.isoformat() if job.created_at else None,
            "counts": {k: v for k, v in (job.counts or {}).items() if k != "status"},
            "error": errors[0]["reason"] if state == "error" and errors else ""}


@router.get("/sp-materials/import-status")
def import_status(db: Session = Depends(get_db), user: User = editors) -> dict:
    return _status(_latest(db))


@router.get("/sp-materials/sheets")
def list_sheets(db: Session = Depends(get_db), user: User = editors) -> list[dict]:
    return [{"name": s.name, "rows": s.row_count, "filename": s.filename,
             "imported_at": s.imported_at.isoformat() if s.imported_at else None}
            for s in db.scalars(select(SpMaterialSheet).order_by(SpMaterialSheet.position))]


@router.get("/sp-materials/sheets/{name}")
def sheet_rows(name: str, q: str = "", limit: int = Query(default=100, ge=1, le=500),
               offset: int = Query(default=0, ge=0), db: Session = Depends(get_db),
               user: User = editors) -> dict:
    sheet = db.scalar(select(SpMaterialSheet).where(SpMaterialSheet.name == name))
    if sheet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brak takiej zakładki")
    query = select(SpMaterialRow).where(SpMaterialRow.sheet_id == sheet.id)
    needle = q.strip().lower()
    if needle:
        query = query.where(SpMaterialRow.search.contains(needle, autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(SpMaterialRow.row_no).limit(limit).offset(offset))
    return {"headers": sheet.headers or [], "total": total, "rows": [r.cells for r in rows]}

"""Wzory plików dla agencji (Master data → „Wzory plików dla agencji”): podgląd i edycja
układu kolumn, wgranie nowej próbki od agencji, pobranie zapisanej próbki."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import agency_templates as tpl
from ..audit import record
from ..config import settings
from ..database import get_db
from ..deps import Editors as editors   # jak sekcje Master data (admin + logistyka)
from ..models import User
from ..tabular import load_workbook_or_422
from .forwarding_files import read_upload_capped, uploads_dir

router = APIRouter(prefix="/api/agency-templates", tags=["wzory agencji"])


class ColumnIn(BaseModel):
    name: str
    source: str
    value: str = ""
    required: bool = False
    note: str = ""
    example: str = ""


class TemplateIn(BaseModel):
    columns: list[ColumnIn]


def _known(key: str) -> None:
    if key not in tpl.DEFAULTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma takiego wzoru.")


def _out(db: Session, key: str) -> dict:
    return {"key": key, **tpl.load(db, key),
            "has_sample": (uploads_dir() / tpl.sample_name(key)).is_file()}


@router.get("")
def list_templates(db: Session = Depends(get_db), user: User = editors) -> dict:
    return {"sources": tpl.SOURCES, "templates": [_out(db, key) for key in tpl.DEFAULTS]}


@router.put("/{key}")
def update_template(key: str, body: TemplateIn, db: Session = Depends(get_db),
                    user: User = editors) -> dict:
    _known(key)
    columns = [c.model_dump() for c in body.columns]
    errors = tpl.validate_columns(columns)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, " ".join(errors))
    tpl.save(db, key, {**tpl.load(db, key), "columns": columns})
    record(db, entity_type="settings", entity_id=0, field=tpl.setting_key(key),
           old_value=None, new_value=f"{len(columns)} kolumn", user=user)
    db.commit()
    return _out(db, key)


@router.post("/{key}/sample")
def upload_sample(key: str, file: UploadFile, db: Session = Depends(get_db),
                  user: User = editors) -> dict:
    """Nowy wzór od agencji (.xlsx): nagłówki z 1. wiersza = układ kolumn, 2. wiersz = przykłady."""
    _known(key)
    content = read_upload_capped(file, settings.max_upload_mb, label="Wzór")
    wb = load_workbook_or_422(content)
    rows = list(wb.active.iter_rows(min_row=1, max_row=2, values_only=True))
    headers = [str(h).strip() for h in (rows[0] if rows else ()) if h is not None and str(h).strip()]
    if not headers:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Pierwszy wiersz wzoru nie ma nagłówków kolumn.")
    template = tpl.merge_sample(tpl.load(db, key), headers, list(rows[1]) if len(rows) > 1 else [])
    template["sheet"] = wb.active.title
    tpl.save(db, key, template)
    record(db, entity_type="settings", entity_id=0, field=tpl.setting_key(key),
           old_value=None, new_value=f"nowy wzór: {file.filename} ({len(headers)} kolumn)", user=user)
    (uploads_dir() / tpl.sample_name(key)).write_bytes(content)
    db.commit()
    return _out(db, key)


@router.get("/{key}/sample")
def download_sample(key: str, user: User = editors) -> FileResponse:
    _known(key)
    path = uploads_dir() / tpl.sample_name(key)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wzór od agencji nie został jeszcze wgrany.")
    return FileResponse(path, filename=f"wzor_{key}.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

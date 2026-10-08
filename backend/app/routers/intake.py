"""Poczekalnia dokumentów — API (spec 2026-10-06-dokumenty-dostaw §2–§3): wgranie, podgląd części,
zmiana typu/kontenera/decyzji, „Potwierdź” i „Odrzuć wszystko”. Logika w routers/intake_flow.py; zakres
(kontener kontekstu, spedytor tylko własne wgrania) — deps._enforce_scope / may_see_intake."""
import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..database import get_db
from ..deps import Editors as editors
from ..deps import NonWarehouseViewers as non_warehouse
from ..deps import company_filter_ids, get_scoped, may_see_intake
from ..models import INTAKE_DOC_TYPES, Container, IntakeBatch, IntakeItem, User
from ..schemas.base import ORMModel
from .containers import get_container_checked
from . import intake_flow as intake
from . import intake_mail
from .forwarding_files import read_upload_capped, safe_filename, uploads_dir

router = APIRouter(prefix="/api", tags=["dokumenty"])

DocType = Literal[INTAKE_DOC_TYPES]  # type: ignore[valid-type]


class IntakeItemOut(ORMModel):
    id: int
    original_name: str
    page_from: int
    page_to: int
    pages: int
    sha256: str
    doc_type: str
    target_container_id: int | None
    target_container_no: str | None = None
    gate_status: str
    gate_message: str
    found_containers: list[dict]
    decision: str
    created_at: datetime.datetime


class IntakeBatchOut(ORMModel):
    id: int
    container_id: int | None
    company_id: int | None = None
    source: str
    note: str | None = None
    created_by_id: int | None
    created_at: datetime.datetime
    status: str
    items: list[IntakeItemOut]
    skipped: list[str] = []


class IntakeItemPatch(BaseModel):
    doc_type: DocType | None = None
    target_container_id: int | None = None
    decision: Literal["accepted", "rejected"] | None = None


def _out(db: Session, batch: IntakeBatch, skipped: list[str] | None = None) -> IntakeBatchOut:
    out = IntakeBatchOut.model_validate(batch)
    ids = {i.target_container_id for i in out.items if i.target_container_id}
    rows = db.execute(select(Container.id, Container.container_no).where(Container.id.in_(ids))).all()
    numbers = {cid: no for cid, no in rows}
    for item in out.items:
        item.target_container_no = numbers.get(item.target_container_id or 0)
    out.skipped = skipped or []
    return out


@router.post("/containers/{container_id}/intake", response_model=IntakeBatchOut, status_code=201)
def upload_intake(container_id: int, files: list[UploadFile] = File(...),
                  db: Session = Depends(get_db), user: User = non_warehouse):
    container = get_container_checked(db, container_id, user)
    contents = [(f.filename or "plik", read_upload_capped(f, settings.max_upload_mb)) for f in files]
    batch, skipped = intake.receive(db, container, contents, user)
    return _out(db, batch, skipped)


@router.get("/containers/{container_id}/intake", response_model=list[IntakeBatchOut])
def list_intake(container_id: int, status: Literal["pending", "confirmed", "discarded"] = "pending",
                db: Session = Depends(get_db), user: User = non_warehouse):
    """Pasek „N dokumentów czeka na potwierdzenie” (decyzja 12)."""
    get_container_checked(db, container_id, user)
    batches = db.scalars(select(IntakeBatch).where(IntakeBatch.container_id == container_id,
                                                   IntakeBatch.status == status)
                         .order_by(IntakeBatch.id))
    return [_out(db, b) for b in batches if may_see_intake(b, user)]


@router.post("/intake/inbox", status_code=201)
def intake_inbox(response: Response, file: UploadFile = File(...), subject: str = Form(""),
                 sender: str = Form(""), db: Session = Depends(get_db), user: User = editors) -> dict:
    """Automat (n8n, token X-Automation-Token; docs/POCZTA-DO-POCZEKALNI.md): cały mail albo
    załącznik → wgrania poczekalni per kontener z treści + „bez dopasowania”. 200 = ten sam mail."""
    data = read_upload_capped(file, settings.max_upload_mb)
    out, created = intake_mail.receive_mail(db, safe_filename(file.filename, "poczta.eml"), data,
                                            subject[:300], sender[:300], user)
    if not created:
        response.status_code = status.HTTP_200_OK
    return out


@router.get("/intake/unmatched", response_model=list[IntakeBatchOut])
def list_unmatched(db: Session = Depends(get_db), user: User = editors):
    """Poczta bez dopasowania — oczekujące wgrania bez kontenera ze spółek w zakresie."""
    ids = company_filter_ids(user)
    query = select(IntakeBatch).where(IntakeBatch.container_id.is_(None), IntakeBatch.status == "pending")
    if ids is not None:
        query = query.where(IntakeBatch.company_id.in_(ids))
    return [_out(db, b) for b in db.scalars(query.order_by(IntakeBatch.id))]


@router.get("/intake/{batch_id}", response_model=IntakeBatchOut)
def get_intake(batch_id: int, db: Session = Depends(get_db), user: User = non_warehouse):
    return _out(db, get_scoped(db, IntakeBatch, batch_id, user))


@router.patch("/intake/items/{item_id}", response_model=IntakeItemOut)
def update_intake_item(item_id: int, body: IntakeItemPatch, db: Session = Depends(get_db),
                       user: User = non_warehouse):
    item = get_scoped(db, IntakeItem, item_id, user)
    if item.batch.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "To wgranie jest już zamknięte.")
    before = (item.doc_type, item.target_container_id, item.decision)
    if body.target_container_id is not None:
        item.target_container_id = get_container_checked(db, body.target_container_id, user).id
    if body.doc_type is not None:
        item.doc_type = body.doc_type
    if body.decision is not None:
        item.decision = body.decision
    entity_id = item.batch.container_id or item.target_container_id   # poczta bez dopasowania
    if entity_id is not None:
        audit.record(db, entity_type="containers", entity_id=entity_id, field="intake_item",
                     old_value="/".join(map(str, before)), user=user, note=item.original_name,
                     new_value="/".join(map(str, (item.doc_type, item.target_container_id, item.decision))))
    db.commit()
    db.refresh(item)
    return next(i for i in _out(db, item.batch).items if i.id == item.id)


@router.post("/intake/{batch_id}/confirm")
def confirm_intake(batch_id: int, db: Session = Depends(get_db), user: User = non_warehouse) -> dict:
    return intake.confirm(db, get_scoped(db, IntakeBatch, batch_id, user), user)


@router.post("/intake/{batch_id}/discard", status_code=204)
def discard_intake(batch_id: int, db: Session = Depends(get_db), user: User = non_warehouse) -> None:
    intake.discard(db, get_scoped(db, IntakeBatch, batch_id, user), user)


@router.get("/intake/items/{item_id}/file")
def download_intake_item(item_id: int, db: Session = Depends(get_db), user: User = non_warehouse):
    item = get_scoped(db, IntakeItem, item_id, user)
    path = uploads_dir() / item.stored_name
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plik części nie jest już w poczekalni.")
    return FileResponse(path, filename=item.original_name)

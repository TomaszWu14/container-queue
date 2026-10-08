"""Agencja celna po wysłaniu faktur: potwierdzenie odbioru i drafty SAD (spec
2026-09-29-agencja-draft-sad, PR 1 — obieg ręczny). Uprawnienia jak szkic maila do agencji."""
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import PurchasingReaders as docs_senders
from ..document_gate import CONFLICT, UNREADABLE, check_pdf
from ..invoices import sad_drafts as flow
from ..invoices import sad_inbox
from ..models import User
from .forwarding_files import read_upload_capped, safe_filename
from .invoices import _get_batch

router = APIRouter(prefix="/api", tags=["faktury"])


class DecisionIn(BaseModel):
    decision: str = Field(max_length=12)
    comment: str = Field(default="", max_length=1000)


@router.get("/invoice-batches/{batch_id}/sad-drafts")
def sad_state(batch_id: int, db: Session = Depends(get_db), user: User = docs_senders) -> dict:
    return flow.state(db, _get_batch(db, batch_id, user))


@router.post("/invoice-batches/{batch_id}/agency-ack")
def agency_ack(batch_id: int, db: Session = Depends(get_db), user: User = docs_senders) -> dict:
    batch = _get_batch(db, batch_id, user)
    flow.acknowledge(db, batch, user, "manual")
    db.commit()
    return flow.state(db, batch)


@router.post("/invoice-batches/{batch_id}/sad-drafts", status_code=201)
def upload_sad_draft(batch_id: int, file: UploadFile, response: Response,
                     db: Session = Depends(get_db), user: User = docs_senders) -> dict:
    batch = _get_batch(db, batch_id, user)
    name = safe_filename(file.filename, "draft_SAD.pdf")
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Draft SAD: wymagany plik PDF.")
    content = read_upload_capped(file, settings.max_upload_mb, "Draft SAD")
    # §4 pkt 19: jak skrzynka automatu — czytelny PDF i nie draft innego kontenera
    gate = check_pdf(content, batch.container.container_no)
    if gate["status"] == UNREADABLE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, gate["message"])
    if gate["status"] == CONFLICT:
        raise HTTPException(status.HTTP_409_CONFLICT, gate["message"])
    draft, created = flow.add_draft(db, batch, name, content, user, "manual")
    if not created:
        response.status_code = status.HTTP_200_OK
    current = flow.state(db, batch)
    return {"draft": next(d for d in current["drafts"] if d["id"] == draft.id),
            "created": created, "state": current}


@router.post("/invoice-batches/{batch_id}/sad-drafts/{draft_id}/xml", status_code=201)
def upload_sad_xml(batch_id: int, draft_id: int, file: UploadFile, response: Response,
                   db: Session = Depends(get_db), user: User = docs_senders) -> dict:
    """XML z WinSAD dosłany po PDF → dane tej wersji z XML i od razu nowe porównanie z fakturami."""
    batch = _get_batch(db, batch_id, user)
    name = safe_filename(file.filename, "draft_SAD.xml")
    if not name.lower().endswith(".xml"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Draft SAD: wymagany plik XML.")
    content = read_upload_capped(file, settings.max_upload_mb, "Draft SAD (XML)")
    draft, created = flow.attach_xml(db, batch, draft_id, name, content, user, "manual")
    if created:
        flow.compare_draft(db, batch, draft.id, user)
    else:
        response.status_code = status.HTTP_200_OK
    return {"created": created, "state": flow.state(db, batch)}


@router.post("/sad-drafts/inbox", status_code=201)
def sad_inbox_upload(file: UploadFile, response: Response, db: Session = Depends(get_db),
                     user: User = docs_senders) -> dict:
    """Automat (n8n, token X-Automation-Token): PDF/XML draftu z maila agencji → paczka faktur
    rozpoznana po kontenerze z pliku. 409 = spróbuj później (brak paczki / XML przed PDF)."""
    name = safe_filename(file.filename, "draft_SAD.pdf")
    content = read_upload_capped(file, settings.max_upload_mb, "Draft SAD")
    out = sad_inbox.receive(db, name, content, user)
    if not out["created"]:
        response.status_code = status.HTTP_200_OK
    return out


@router.post("/invoice-batches/{batch_id}/sad-drafts/{draft_id}/decision")
def sad_decision(batch_id: int, draft_id: int, body: DecisionIn,
                 db: Session = Depends(get_db), user: User = docs_senders) -> dict:
    batch = _get_batch(db, batch_id, user)
    flow.decide(db, batch, draft_id, body.decision, body.comment, user)
    return flow.state(db, batch)


@router.post("/invoice-batches/{batch_id}/sad-drafts/{draft_id}/compare")
def compare_sad_draft(batch_id: int, draft_id: int, db: Session = Depends(get_db),
                      user: User = docs_senders) -> dict:
    return flow.compare_draft(db, _get_batch(db, batch_id, user), draft_id, user)


@router.get("/invoice-batches/{batch_id}/sad-drafts/{draft_id}/pages/{page}")
def sad_draft_page(batch_id: int, draft_id: int, page: int, db: Session = Depends(get_db),
                   user: User = docs_senders) -> Response:
    png = flow.page_png(db, _get_batch(db, batch_id, user), draft_id, page)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=600"})

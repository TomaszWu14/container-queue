"""W5 #36 — szablony wysyłki dokumentów do agencji celnej: CRUD szablonów,
render tematu/treści (render_docs_message, używany przez customs.py) i podgląd."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..audit import record, record_changes
from ..database import get_db
from ..date_pl import date_pl
from ..deps import AdminOnly as admin_only
from ..deps import PurchasingReaders as docs_senders
from ..models import Attachment, Container, CustomsAgency, DocSendTemplate, User
from ..notifications import customs_agency_users
from ..schemas import DocSendTemplateIn, DocSendTemplateOut
from .containers import get_container_checked
from .customs import missing_document_types

# podpinany w routers/documents.py (router.include_router) — main.py bez zmian
router = APIRouter()   # prefiks /api i tag dziedziczy z routera nadrzędnego

# podgląd/wysyłka dokumentów do agencji — jak docs_senders w customs.py


# --- 36: szablony wysyłki dokumentów do agencji -------------------------------

# domyślna treść = dotychczasowy komunikat send_docs_to_agency (bez szablonu w bazie
# zachowanie się nie zmienia)
DEFAULT_DOCS_SUBJECT = "Dokumenty do odprawy: {container_no}"
DEFAULT_DOCS_BODY = ("Przekazano {liczba} plik(ów): {lista_dokumentow}. "
                     "Pobierzesz je w zakładce plików kontenera.")


class _Keep(dict):
    """format_map: nieznany placeholder zostaje w tekście zamiast rzucać KeyError."""
    def __missing__(self, key):  # noqa: D105
        return "{" + key + "}"


def template_for(db: Session, customs_agency_id: int | None) -> DocSendTemplate | None:
    """Szablon agencji, a gdy brak — domyślny (customs_agency_id IS NULL)."""
    if customs_agency_id is not None:
        specific = db.scalar(select(DocSendTemplate)
                             .where(DocSendTemplate.customs_agency_id == customs_agency_id)
                             .order_by(DocSendTemplate.id))
        if specific:
            return specific
    return db.scalar(select(DocSendTemplate)
                     .where(DocSendTemplate.customs_agency_id.is_(None))
                     .order_by(DocSendTemplate.id))


def render_docs_message(db: Session, container: Container,
                        attachments: list[Attachment]) -> tuple[str, str]:
    """(temat, treść) wysyłki dokumentów wg szablonu; brak szablonu = obecna treść."""
    template = template_for(db, container.customs_agency_id)
    subject = (template.subject if template and template.subject.strip()
               else DEFAULT_DOCS_SUBJECT)
    body = template.body if template and template.body.strip() else DEFAULT_DOCS_BODY
    values = _Keep(
        container_no=container.container_no,
        eta=date_pl(container.eta) or "—",
        lista_dokumentow=", ".join(a.filename for a in attachments) or "—",
        liczba=len(attachments),
    )
    return subject.format_map(values), body.format_map(values)


@router.get("/customs/doc-templates", response_model=list[DocSendTemplateOut])
def list_doc_templates(db: Session = Depends(get_db), user: User = docs_senders):
    rows = db.scalars(select(DocSendTemplate)
                      .options(selectinload(DocSendTemplate.customs_agency))
                      .order_by(DocSendTemplate.customs_agency_id.is_not(None),
                                DocSendTemplate.id)).all()
    out = []
    for row in rows:
        entry = DocSendTemplateOut.model_validate(row)
        entry.customs_agency_name = row.customs_agency.name if row.customs_agency else None
        out.append(entry)
    return out


def _validate_template(db: Session, body: DocSendTemplateIn) -> None:
    if body.customs_agency_id is not None and not db.get(CustomsAgency, body.customs_agency_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono agencji celnej.")


def _scope(template: DocSendTemplate) -> str:
    """Opis szablonu w audycie: agencja albo szablon domyślny."""
    return (f"agencja {template.customs_agency_id}" if template.customs_agency_id is not None
            else "domyślny")


@router.post("/customs/doc-templates", response_model=DocSendTemplateOut, status_code=201)
def create_doc_template(body: DocSendTemplateIn, db: Session = Depends(get_db),
                        user: User = admin_only):
    _validate_template(db, body)
    template = DocSendTemplate(**body.model_dump())
    db.add(template)
    db.flush()
    record(db, entity_type=DocSendTemplate.__tablename__, entity_id=template.id, field="created",
           old_value=None, new_value=_scope(template), user=user)
    db.commit()
    return template


@router.patch("/customs/doc-templates/{template_id}", response_model=DocSendTemplateOut)
def update_doc_template(template_id: int, body: DocSendTemplateIn,
                        db: Session = Depends(get_db), user: User = admin_only):
    template = db.get(DocSendTemplate, template_id)
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono szablonu.")
    _validate_template(db, body)
    record_changes(db, template, body.model_dump(exclude_unset=True), user, note=_scope(template))
    db.commit()
    return template


@router.delete("/customs/doc-templates/{template_id}", status_code=204)
def delete_doc_template(template_id: int, db: Session = Depends(get_db),
                        user: User = admin_only):
    template = db.get(DocSendTemplate, template_id)
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono szablonu.")
    record(db, entity_type=DocSendTemplate.__tablename__, entity_id=template.id, field="delete",
           old_value=_scope(template), new_value=None, user=user)
    db.delete(template)
    db.commit()


@router.get("/customs/containers/{container_id}/send-docs/preview")
def send_docs_preview(container_id: int, db: Session = Depends(get_db),
                      user: User = docs_senders):
    """Podgląd wiadomości do agencji przed wysyłką (wyrenderowany szablon)."""
    container = get_container_checked(db, container_id, user)
    attachments = db.scalars(select(Attachment)
                             .where(Attachment.container_id == container_id)
                             .order_by(Attachment.created_at)).all()
    subject, body = render_docs_message(db, container, attachments)
    # audyt 2026-10-06 #18: kto dostanie powiadomienie i jakie pliki — nie tylko temat i treść
    agency = container.customs_agency_rel
    users = customs_agency_users(db, container.customs_agency_id) if agency else []
    return {"subject": subject, "body": body,
            "missing": missing_document_types(db, container),
            "attachments": len(attachments),
            "agency": agency.name if agency else None,
            "recipients": [u.full_name or u.login for u in users],
            "files": [{"name": a.filename,
                       "type": a.document_type.name if a.document_type else None} for a in attachments]}

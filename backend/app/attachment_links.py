"""Wspólny plik dla kilku kontenerów (spec 2026-10-06 decyzja 24, §2): `Attachment.container_id`
to właściciel, `AttachmentLink` — pozostałe kontenery tej samej spółki („wspólny z X”).
Plik powiązany liczy się w kontenerze jak własny: lista plików, kafelki, mail do agencji, bramka dubli."""
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from . import audit
from .audit import record_changes
from .models import Attachment, AttachmentLink, Container, DocumentStatus, User


def in_container(container_id: int) -> ColumnElement[bool]:
    """Warunek: załącznik należy do kontenera albo jest z nim powiązany."""
    linked = select(AttachmentLink.attachment_id).where(AttachmentLink.container_id == container_id)
    return or_(Attachment.container_id == container_id, Attachment.id.in_(linked))


def containers_of(db: Session, attachment_ids: list[int]) -> dict[int, list[str]]:
    """id załącznika → numery wszystkich jego kontenerów (właściciel pierwszy, potem powiązane)."""
    if not attachment_ids:
        return {}
    out: dict[int, list[str]] = {}
    owners = db.execute(select(Attachment.id, Container.container_no)
                        .join(Container, Attachment.container_id == Container.id)
                        .where(Attachment.id.in_(attachment_ids))).all()
    linked = db.execute(select(AttachmentLink.attachment_id, Container.container_no)
                        .join(Container, AttachmentLink.container_id == Container.id)
                        .where(AttachmentLink.attachment_id.in_(attachment_ids))
                        .order_by(AttachmentLink.id)).all()
    for att_id, no in [*owners, *linked]:
        out.setdefault(att_id, []).append(no)
    return out


def add_link(db: Session, attachment: Attachment, target: Container, user: User) -> AttachmentLink:
    """Powiązanie (bez commitu) + historia w obu kontenerach; otypowany plik przesuwa obieg
    dokumentów celu BRAK→ZALACZONE jak zwykłe wgranie. Walidacja (spółka, zakres) — u wołającego."""
    link = AttachmentLink(attachment=attachment, container_id=target.id, created_by_id=user.id)
    db.add(link)
    owner = db.get(Container, attachment.container_id) if attachment.container_id else None
    owner_no = owner.container_no if owner else ""
    for cid, note in ((target.id, f"wspólny z {owner_no}"), (attachment.container_id, f"wspólny z {target.container_no}")):
        if cid is not None:
            audit.record(db, entity_type="containers", entity_id=cid, field="attachment_link",
                         old_value=None, new_value=attachment.filename, user=user, note=note)
    if attachment.document_type is not None and target.document_status == DocumentStatus.BRAK:
        record_changes(db, target, {"document_status": DocumentStatus.ZALACZONE},
                       user, note="pierwszy otypowany dokument")
    return link

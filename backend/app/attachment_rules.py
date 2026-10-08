"""Kto i kiedy może usunąć / podmienić dokument kontenera (decyzje usera 2026-10-06,
spec docs/superpowers/specs/2026-10-06-dokumenty-dostaw-design.md, §1 pkt 5, §4 pkt 1–3, 47):

- partnerzy (spedytor, agencja celna) — tylko pliki wgrane przez siebie;
- Excel paczki faktur i pliki draftu SAD mają własny obieg — nie tu;
- po wysłaniu dokumentów do agencji albo po odprawie — tylko „Podmień” z powodem (bez „Usuń”).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CUSTOMS_CLEARED, Attachment, Container, DocumentStatus, InvoiceBatch, Role, SadDraft, User

PARTNER_ROLES = (Role.forwarder, Role.customs)


def removal_block(db: Session, attachment: Attachment, user: User) -> tuple[int, str] | None:
    """(kod HTTP, komunikat), gdy pliku nie wolno ani usunąć, ani podmienić; None = wolno."""
    if user.role in PARTNER_ROLES and attachment.uploaded_by_id != user.id:
        return 403, "Możesz usunąć lub podmienić tylko pliki wgrane przez siebie."
    if db.scalar(select(InvoiceBatch.id).where(InvoiceBatch.attachment_id == attachment.id)):
        return 409, "To Excel paczki faktur — wygeneruj go ponownie albo usuń paczkę."
    if db.scalar(select(SadDraft.id).where((SadDraft.attachment_id == attachment.id)
                                           | (SadDraft.xml_attachment_id == attachment.id))):
        return 409, "To plik draftu SAD — wersjami draftu zarządza sekcja „Agencja”."
    return None


def is_sent(container: Container) -> bool:
    """Dokumenty poszły do agencji albo odprawa zakończona — usuwanie tylko przez Podmień z powodem."""
    return (container.document_status == DocumentStatus.WYSLANE
            or container.customs_status in CUSTOMS_CLEARED)


SENT_DELETE = ("Dokumenty zostały już wysłane do agencji albo odprawa się zakończyła — "
               "zamiast usuwać, użyj „Podmień” i podaj powód.")
REASON_REQUIRED = "Podaj powód podmiany — dokumenty były już wysłane do agencji."


def flags(db: Session, attachment: Attachment, container: Container, user: User) -> dict:
    """Pola dla UI: czy pokazać Usuń / Podmień i czy podmiana wymaga powodu."""
    blocked = removal_block(db, attachment, user) is not None
    sent = is_sent(container)
    return {"can_delete": not blocked and not sent, "can_replace": not blocked,
            "replace_needs_reason": sent}

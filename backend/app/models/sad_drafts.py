"""Wymiana z agencją celną po wysłaniu faktur (spec 2026-09-29-agencja-draft-sad): potwierdzenie
odbioru paczki i wersjonowane drafty SAD z decyzją operatora. Agencja nie loguje się do
aplikacji — dane wprowadza operator albo automat (n8n) przez to samo wejście."""
import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .enums import utcnow
from .transport import Attachment

__all__ = ["DECISIONS", "SOURCES", "AgencyAck", "SadDraft"]

SOURCES = ("manual", "automation")
DECISIONS = ("pending", "accepted", "rejected")


class AgencyAck(Base):
    """Agencja potwierdziła odbiór paczki faktur (1:1 z paczką)."""
    __tablename__ = "agency_acks"
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("invoice_batches.id", ondelete="CASCADE"), primary_key=True)
    acked_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    source: Mapped[str] = mapped_column(String(12), default="manual")
    acked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class SadDraft(Base):
    """Wersja draftu SAD od agencji; plik = załącznik kontenera (typ „Draft SAD”)."""
    __tablename__ = "sad_drafts"
    __table_args__ = (UniqueConstraint("batch_id", "version", name="uq_sad_drafts_batch_version"),
                      UniqueConstraint("batch_id", "sha256", name="uq_sad_drafts_batch_sha"))
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("invoice_batches.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    attachment_id: Mapped[int] = mapped_column(ForeignKey("attachments.id"), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(12), default="manual")
    decision: Mapped[str] = mapped_column(String(12), default="pending",
                                          server_default=text("'pending'"))
    comment: Mapped[str] = mapped_column(String(1000), default="", server_default=text("''"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # PR 2: odczyt PDF (invoices/sad_parse) i ostatni wynik porównania (invoices/sad_compare)
    parsed: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    comparison: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # XML z WinSAD dosyłany po PDF (dołącza do tej wersji, dane z niego zastępują odczyt PDF)
    xml_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True)
    xml_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attachment: Mapped[Attachment] = relationship(foreign_keys=[attachment_id])
    xml_attachment: Mapped[Attachment | None] = relationship(foreign_keys=[xml_attachment_id])

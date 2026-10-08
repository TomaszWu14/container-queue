"""Poczekalnia dokumentów (spec 2026-10-06-dokumenty-dostaw §2, decyzje 2, 11, 12): wgrane pliki
pocięte na części czekają tu z typem, kontenerem docelowym i wynikiem bramki — do dostawy
trafiają dopiero po „Potwierdź”. Bez limitu czasu."""
import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .enums import utcnow

__all__ = ["INTAKE_DECISIONS", "INTAKE_DOC_TYPES", "INTAKE_GATES", "INTAKE_STATUSES",
           "IntakeBatch", "IntakeItem"]

INTAKE_STATUSES = ("pending", "confirmed", "discarded")
INTAKE_DECISIONS = ("pending", "accepted", "rejected")
INTAKE_GATES = ("ok", "uncertain", "conflict", "duplicate", "unreadable")
# kody typów = DocumentType.tile_code tam, gdzie kafelek istnieje (CMR, MAIL i OTHER bez kafelka);
# MAIL = wiadomość .eml/.msg jako korespondencja (załączniki osobno)
INTAKE_DOC_TYPES = ("CI", "PI", "PL", "BL", "SAD_DRAFT", "SAD_PZ", "SAD_PW", "CMR", "MAIL", "OTHER")


class IntakeBatch(Base):
    """Jedno wgranie do poczekalni (kontener kontekstu = karta, z której wgrano). Poczta (source
    „mail”, decyzja 27): kontener z treści; NULL = „poczta bez dopasowania” dla logistyki spółki."""
    __tablename__ = "intake_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[int | None] = mapped_column(ForeignKey("containers.id"), index=True, nullable=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(12), default="manual")   # manual | mail
    note: Mapped[str | None] = mapped_column(Text, nullable=True)   # poczta: nadawca · temat
    mail_sha256: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    items: Mapped[list["IntakeItem"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="IntakeItem.id",
        lazy="selectin")


class IntakeItem(Base):
    """Część wgranego pliku (dokument po cięciu) — plik części leży w uploads (`stored_name`)."""
    __tablename__ = "intake_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("intake_batches.id", ondelete="CASCADE"), index=True)
    stored_name: Mapped[str] = mapped_column(String(255))
    original_name: Mapped[str] = mapped_column(String(255))
    page_from: Mapped[int] = mapped_column(Integer, default=0)
    page_to: Mapped[int] = mapped_column(Integer, default=0)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64))
    doc_type: Mapped[str] = mapped_column(String(12), default="OTHER")
    target_container_id: Mapped[int | None] = mapped_column(ForeignKey("containers.id"), nullable=True)
    gate_status: Mapped[str] = mapped_column(String(12), default="ok")
    gate_message: Mapped[str] = mapped_column(Text, default="")
    # [{container_no, container_id|None}] — id tylko dla kontenerów w zakresie wgrywającego
    found_containers: Mapped[list] = mapped_column(JSON, default=list)
    decision: Mapped[str] = mapped_column(String(12), default="pending")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    batch: Mapped[IntakeBatch] = relationship(back_populates="items")

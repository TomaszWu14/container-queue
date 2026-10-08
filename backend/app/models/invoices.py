"""Faktury CIPL → Excel: partie, zadania, pozycje, sugestie załączników, szablony wysyłki."""
import datetime
import enum

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .container import Container
from .dictionaries import CustomsAgency, DocumentType, Supplier
from .enums import utcnow
from .transport import Attachment


class InvoiceDocKind(str, enum.Enum):
    """Typ dokumentu wyciętego z PDF-zestawu (CIPL / komplet kontenerowy)."""
    invoice = "invoice"            # Commercial Invoice
    proforma = "proforma"
    packing_list = "packing_list"  # źródło wag, nie faktura
    other = "other"                # B/L, skan bez tekstu, nierozpoznane


class InvoiceJobStatus(str, enum.Enum):
    """Cykl życia jednego dokumentu w module Faktury → Excel."""
    uploaded = "uploaded"
    extracted = "extracted"        # pozycje wyciągnięte — czeka na weryfikację
    confirmed = "confirmed"        # zatwierdzone przez użytkownika — wchodzi do Excela
    error = "error"
    packing_list = "packing_list"  # sklasyfikowany jako PL — poza pipeline'em faktur
    ignored = "ignored"            # B/L, skan itp.


class InvoiceMatchStatus(str, enum.Enum):
    """Dopasowanie pozycji faktury do master daty materiałów."""
    matched = "matched"
    ambiguous = "ambiguous"        # kilku kandydatów (X vs X1) — blokuje zatwierdzenie
    unmatched = "unmatched"        # brak w master — puste pola, NIE blokuje


INVOICE_LIKE_KINDS = (InvoiceDocKind.invoice, InvoiceDocKind.proforma)


class InvoiceBatch(Base):
    """Paczka faktur (CIPL) wgrana przy kontenerze: dokumenty → weryfikacja → Excel.

    `ready` = wygenerowany Excel odpowiada bieżącemu stanowi (każda edycja po eksporcie
    zeruje); „wszystkie zatwierdzone” liczy pipeline.batch_counts z dokumentów. Gotowy Excel
    ląduje w zwykłych `attachments` — pobieranie istniejącym /api/attachments/{id}/download."""
    __tablename__ = "invoice_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    # indeksy FK (DB-010): filtr dokumentów po dostawcy; kasowanie załączników (FK check)
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id"), nullable=True, index=True)
    ready: Mapped[bool] = mapped_column(Boolean, default=False)
    attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachments.id"), nullable=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    attachment: Mapped["Attachment | None"] = relationship()
    supplier: Mapped[Supplier | None] = relationship()
    container: Mapped[Container] = relationship()
    jobs: Mapped[list["InvoiceJob"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="InvoiceJob.id",
        lazy="selectin")


class InvoiceJob(Base):
    """Jeden dokument (część PDF-zestawu) w paczce faktur."""
    __tablename__ = "invoice_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("invoice_batches.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255))      # plik części w uploads_dir
    source_name: Mapped[str] = mapped_column(String(255), default="")  # oryginalny PDF
    # skrót oryginalnego PDF — zostaje po przeniesieniu/kopii (source_name wtedy ""), sha001
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    page_from: Mapped[int] = mapped_column(Integer, default=0)
    page_to: Mapped[int] = mapped_column(Integer, default=0)
    doc_kind: Mapped[InvoiceDocKind] = mapped_column(
        Enum(InvoiceDocKind), default=InvoiceDocKind.invoice)
    status: Mapped[InvoiceJobStatus] = mapped_column(
        Enum(InvoiceJobStatus), default=InvoiceJobStatus.uploaded)
    error: Mapped[str] = mapped_column(Text, default="")
    invoice_number: Mapped[str] = mapped_column(String(80), default="")
    container_no: Mapped[str] = mapped_column(String(20), default="")
    delivery_terms: Mapped[str] = mapped_column(String(60), default="")
    # początek tekstu dokumentu — dane treningowe klasyfikatora typu (invoices/ml)
    text_excerpt: Mapped[str] = mapped_column(Text, default="")
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)   # skan czytany OCR-em
    # kolejka w tle (que001): start bieżącego przetwarzania zaślepki i liczba podejść —
    # przerwane (restart, OOM) 2× = błąd z przyczyną zamiast wiecznego „WGRANE”
    processing_started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    # {doc_total, pl_qty: {REF: ilość}} z ekstrakcji — wejście kontroli (invoices/checks)
    check_data: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    batch: Mapped[InvoiceBatch] = relationship(back_populates="jobs")
    # bez lazy="selectin": lista paczek nie potrzebuje pozycji (liczy je jednym zapytaniem
    # GROUP BY), a każdy dostęp do paczki ładowałby setki wierszy pozycji
    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="InvoiceItem.line_no")
    suggestions: Mapped[list["AttachmentSuggestion"]] = relationship(
        back_populates="job", cascade="all, delete-orphan")


class InvoiceItem(Base):
    """Pozycja faktury po ekstrakcji, wzbogacona master datą; edytowana w weryfikacji.

    Ilości/kwoty trzymamy jako tekst tak, jak stoją na fakturze — Excel ma je oddać 1:1,
    a nie po własnym zaokrągleniu."""
    __tablename__ = "invoice_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("invoice_jobs.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer, default=0)
    raw_ref: Mapped[str] = mapped_column(String(100), default="")
    descr: Mapped[str] = mapped_column(String(500), default="")
    qty: Mapped[str] = mapped_column(String(40), default="")
    uom_src: Mapped[str] = mapped_column(String(20), default="")
    net_amount: Mapped[str] = mapped_column(String(40), default="")
    amount: Mapped[str] = mapped_column(String(40), default="")
    weight_net: Mapped[str] = mapped_column(String(40), default="")
    weight_gross: Mapped[str] = mapped_column(String(40), default="")
    cartons: Mapped[str] = mapped_column(String(40), default="")
    weight_source: Mapped[str] = mapped_column(String(10), default="")   # pl / brak
    master_ref: Mapped[str] = mapped_column(String(100), default="")
    name_pl: Mapped[str] = mapped_column(String(500), default="")
    tariff_cn: Mapped[str] = mapped_column(String(30), default="")
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    uom_factor: Mapped[str] = mapped_column(String(40), default="")
    match_status: Mapped[InvoiceMatchStatus] = mapped_column(
        Enum(InvoiceMatchStatus), default=InvoiceMatchStatus.unmatched)
    match_source: Mapped[str] = mapped_column(String(10), default="")   # rules / ml / user
    # najlepsza sugestia ML (gdy reguły nie dopasowały) — operator widzi ją w weryfikacji
    ml_suggestion: Mapped[str] = mapped_column(String(100), default="")
    ml_confidence: Mapped[float | None] = mapped_column(Numeric(5, 3), nullable=True)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    job: Mapped[InvoiceJob] = relationship(back_populates="items")


class SuggestionStatus(str, enum.Enum):
    """Cykl życia propozycji podpięcia dokumentu z OCR do kontenera."""
    proposed = "proposed"
    accepted = "accepted"
    rejected = "rejected"


class AttachmentSuggestion(Base):
    """Propozycja podpięcia dokumentu z pipeline'u faktur (OCR) do kontenera.

    Powstaje po przetworzeniu InvoiceJob, gdy w tekście dokumentu wykryto numer
    kontenera (ISO 6346) istniejący w spółce. Akceptacja kopiuje plik części PDF
    (wycinek stron ze splittera) jako zwykły Attachment; odrzucenie tylko oznacza.
    Izolacja per zasób: przez container_id (ogólna gałąź w deps._enforce_scope)."""
    __tablename__ = "attachment_suggestions"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("invoice_jobs.id"), index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    doc_kind: Mapped[str] = mapped_column(String(20), default="")   # z klasyfikatora części
    status: Mapped[SuggestionStatus] = mapped_column(
        Enum(SuggestionStatus), default=SuggestionStatus.proposed, index=True)
    document_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_types.id"), nullable=True)
    attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachments.id"), nullable=True, index=True)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    job: Mapped["InvoiceJob"] = relationship(back_populates="suggestions")
    document_type: Mapped[DocumentType | None] = relationship()


class DocSendTemplate(Base):
    """Szablon maila/powiadomienia wysyłki dokumentów do agencji celnej.

    customs_agency_id=None → szablon domyślny (wspólny). Placeholdery w temacie
    i treści: {container_no}, {eta}, {lista_dokumentow}."""
    __tablename__ = "doc_send_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    customs_agency_id: Mapped[int | None] = mapped_column(
        ForeignKey("customs_agencies.id"), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow)
    customs_agency: Mapped[CustomsAgency | None] = relationship()

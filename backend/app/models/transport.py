"""Moduł spedytora: zlecenia transportowe, wyceny (RFQ), wiadomości, załączniki, faktury frachtowe."""
import datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .checks import in_check
from .container import Container
from .dictionaries import Carrier, DocumentType, Forwarder, User
from .enums import QuoteStatus, TransportJobStatus, TransportOrderStatus, utcnow


class TransportOrder(Base):
    """Zlecenie transportowe dla spedytora — pełny obieg statusów."""
    __tablename__ = "transport_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    forwarder_id: Mapped[int] = mapped_column(ForeignKey("forwarders.id"), index=True)
    status: Mapped[TransportOrderStatus] = mapped_column(
        Enum(TransportOrderStatus), default=TransportOrderStatus.WYSTAWIONE)
    pickup_location: Mapped[str] = mapped_column(String(200), default="")
    delivery_location: Mapped[str] = mapped_column(String(200), default="")
    pickup_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    delivery_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    instructions: Mapped[str] = mapped_column(Text, default="")
    rejection_reason: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    container: Mapped[Container] = relationship()
    forwarder: Mapped[Forwarder] = relationship()
    created_by: Mapped[User | None] = relationship()


class TransportJob(Base):
    """Zlecenie transportowe = paczka kontenerów wysyłana spedycjom do wyceny (RFQ)."""
    __tablename__ = "transport_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    status: Mapped[TransportJobStatus] = mapped_column(
        Enum(TransportJobStatus), default=TransportJobStatus.SZKIC, index=True)
    pickup_location: Mapped[str] = mapped_column(String(200), default="")
    delivery_location: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    chosen_quote_id: Mapped[int | None] = mapped_column(
        ForeignKey("quotes.id", use_alter=True, name="fk_job_chosen_quote"), nullable=True)
    chosen_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # termin odpowiedzi spedycji (domyślnie 24h od wysłania, edytowalny) + indeks SCFI
    response_hours: Mapped[int] = mapped_column(Integer, default=24)
    response_deadline: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    scfi_index: Mapped[str] = mapped_column(String(60), default="")  # referencyjna stawka rynkowa
    # po wyborze zwycięzcy: numer przesyłki (podaje logistyka) + dane agenta (podaje spedytor)
    shipment_number: Mapped[str] = mapped_column(String(80), default="")
    agent_name: Mapped[str] = mapped_column(String(160), default="")
    agent_phone: Mapped[str] = mapped_column(String(60), default="")
    agent_company: Mapped[str] = mapped_column(String(160), default="")
    agent_submitted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # anulowanie zlecenia z podaniem powodu (wiersz 20)
    cancel_reason: Mapped[str] = mapped_column(Text, default="")
    cancelled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[User | None] = relationship()
    items: Mapped[list["TransportJobContainer"]] = relationship(
        back_populates="job", cascade="all, delete-orphan")
    quotes: Mapped[list["Quote"]] = relationship(
        back_populates="job", cascade="all, delete-orphan",
        foreign_keys="Quote.job_id")


class TransportJobContainer(Base):
    """Kontener wchodzący w skład zlecenia transportowego (paczki)."""
    __tablename__ = "transport_job_containers"
    __table_args__ = (UniqueConstraint("job_id", "container_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("transport_jobs.id"), index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    job: Mapped[TransportJob] = relationship(back_populates="items")
    container: Mapped[Container] = relationship()


class Quote(Base):
    """Oferta spedytora na zlecenie transportowe (jedna na zaproszoną spedycję)."""
    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("job_id", "forwarder_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("transport_jobs.id"), index=True)
    forwarder_id: Mapped[int] = mapped_column(ForeignKey("forwarders.id"), index=True)
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus), default=QuoteStatus.ZAPYTANIE, index=True)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="PLN")
    valid_until: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    # dane oferty spedytora: armator, daty rejsu, transit time i informacje dodatkowe
    carrier_id: Mapped[int | None] = mapped_column(ForeignKey("carriers.id"), nullable=True)
    etd: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)   # wyjście statku
    eta: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)   # przybycie
    transit_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    no_equipment: Mapped[bool] = mapped_column(Boolean, default=False)       # brak sprzętu
    can_roll_booking: Mapped[bool] = mapped_column(Boolean, default=False)   # możliwe rolowanie
    submitted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # pilna zmiana ceny zgłoszona przez spedycję (wiersz 21 / Q55) — czeka na akceptację
    # logistyki (Q56); po akceptacji revised_amount przechodzi do amount i jest czyszczone
    revised_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    revised_note: Mapped[str] = mapped_column(Text, default="")
    revised_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    job: Mapped[TransportJob] = relationship(back_populates="quotes", foreign_keys=[job_id])
    forwarder: Mapped[Forwarder] = relationship()
    carrier: Mapped["Carrier | None"] = relationship()
    revisions: Mapped[list["QuoteRevision"]] = relationship(
        back_populates="quote", cascade="all, delete-orphan", order_by="QuoteRevision.created_at")


class QuoteRevision(Base):
    """Historia wersji oferty spedytora (Q47) — snapshot ceny przy każdym złożeniu/korekcie."""
    __tablename__ = "quote_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id"), index=True)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="PLN")
    note: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="wycena")  # wycena / korekta / akceptacja
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    quote: Mapped[Quote] = relationship(back_populates="revisions")
    created_by: Mapped["User | None"] = relationship()


class Message(Base):
    """Wątek wiadomości przy kontenerze — zamiast maili i telefonów."""
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    user: Mapped[User] = relationship()


class Attachment(Base):
    """Załącznik do kontenera (dokumenty transportowe: CMR, zlecenia, kwity)."""
    __tablename__ = "attachments"
    # ten sam plik raz na kontener (sha001) — zamyka wyścig równoległych wgrań; NULL = stare
    # wiersze i pliki generowane (Excel, XML draftu SAD)
    __table_args__ = (UniqueConstraint("container_id", "sha256", name="uq_attachments_container_sha"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # typ dokumentu ze słownika admina (checklista kompletności); stare pliki bez typu
    document_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_types.id"), nullable=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    uploaded_by: Mapped[User | None] = relationship()
    document_type: Mapped[DocumentType | None] = relationship()
    # „wspólny z X” (spec 2026-10-06 decyzja 24): usunięcie pliku zdejmuje go ze wszystkich kontenerów
    links: Mapped[list["AttachmentLink"]] = relationship(
        back_populates="attachment", cascade="all, delete-orphan")


class AttachmentLink(Base):
    """Dokument zbiorczy: plik właściciela (`Attachment.container_id`) widoczny też w innym
    kontenerze tej samej spółki. Podmiana u właściciela przepina powiązania na nowy wiersz."""
    __tablename__ = "attachment_links"
    __table_args__ = (UniqueConstraint("attachment_id", "container_id", name="uq_attachment_links"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    attachment_id: Mapped[int] = mapped_column(
        ForeignKey("attachments.id", ondelete="CASCADE"), index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    attachment: Mapped[Attachment] = relationship(back_populates="links")


# obieg akceptacji faktury transportowej (#42) — CHECK ck_freight_invoices_status (DB-007)
FREIGHT_STATUSES = ("NOWA", "DO_AKCEPTACJI", "ZAAKCEPTOWANA", "ODRZUCONA")


class FreightInvoice(Base):
    """Faktura transportowa (BL) — JEDNA faktura obejmująca zestaw kontenerów.

    Osobny kanał od załączników per kontener (Attachment): armator/spedytor wystawia
    jedną fakturę frachtu na cały Bill of Lading, który zwykle obejmuje wiele kontenerów.
    Powiązanie wiele-do-wielu przez FreightInvoiceContainer (jak TransportJobContainer)."""
    __tablename__ = "freight_invoices"
    __table_args__ = (in_check("freight_invoices", "status", FREIGHT_STATUSES),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    bl_number: Mapped[str] = mapped_column(String(80), default="")       # numer B/L
    invoice_number: Mapped[str] = mapped_column(String(80), default="")  # numer faktury
    forwarder_id: Mapped[int | None] = mapped_column(ForeignKey("forwarders.id"), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    note: Mapped[str] = mapped_column(Text, default="")
    # plik faktury (przechowywanie jak Attachment)
    filename: Mapped[str] = mapped_column(String(255), default="")
    stored_name: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    # obieg akceptacji (#42): NOWA → DO_AKCEPTACJI → ZAAKCEPTOWANA | ODRZUCONA (przed zapłatą)
    status: Mapped[str] = mapped_column(String(20), default="NOWA", server_default=text("'NOWA'"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    approval_note: Mapped[str] = mapped_column(String(300), default="", server_default=text("''"))
    forwarder: Mapped["Forwarder | None"] = relationship()
    uploaded_by: Mapped["User | None"] = relationship(foreign_keys=[uploaded_by_id])
    approved_by: Mapped["User | None"] = relationship(foreign_keys=[approved_by_id])
    items: Mapped[list["FreightInvoiceContainer"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan")


class FreightInvoiceContainer(Base):
    """Kontener objęty fakturą BL (m2m faktura↔kontener)."""
    __tablename__ = "freight_invoice_containers"
    __table_args__ = (UniqueConstraint("invoice_id", "container_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("freight_invoices.id"), index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    invoice: Mapped[FreightInvoice] = relationship(back_populates="items")
    container: Mapped[Container] = relationship()

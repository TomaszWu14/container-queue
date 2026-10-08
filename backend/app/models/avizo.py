"""Awizacje dostaw: zapytania, pozycje, tokeny formularza, potwierdzenia, propozycje zmian."""
import datetime
import enum

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .container import Container
from .dictionaries import Company, Forwarder, User
from .enums import utcnow


class AvizoStatus(str, enum.Enum):
    """Maszyna stanów awizacji — przejścia wyłącznie przez app/avizo_workflow.transition."""
    DRAFT = "DRAFT"
    SENT_STAGE1 = "SENT_STAGE1"
    CONFIRMED_BY_FORWARDER = "CONFIRMED_BY_FORWARDER"
    APPROVED_BY_US = "APPROVED_BY_US"
    REJECTED = "REJECTED"
    SENT_STAGE2 = "SENT_STAGE2"
    DRIVERS_SUBMITTED = "DRIVERS_SUBMITTED"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class AvizoRequest(Base):
    """Prośba o awizację wysłana do spedycji — etap 1 (potwierdzenie dostaw) i etap 2
    (dane kierowców), oba przez jednorazowe linki tokenowe (AvizoFormToken)."""
    __tablename__ = "avizo_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    # hash SHA-256 tokenu (surowy token tylko w linku e-mail) — wyciek bazy nie daje linków
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    forwarder_id: Mapped[int] = mapped_column(ForeignKey("forwarders.id"), index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    # publiczny link wygasa — po tym czasie formularz przestaje działać
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[AvizoStatus] = mapped_column(
        Enum(AvizoStatus, native_enum=False, length=30), default=AvizoStatus.SENT_STAGE1,
        server_default=AvizoStatus.SENT_STAGE1.value, index=True)
    language: Mapped[str] = mapped_column(String(2), default="pl", server_default=text("'pl'"))
    reject_comment: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # retencja RODO: kiedy wyczyszczono dane kierowców kontenerów tego zlecenia
    driver_data_purged_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    forwarder: Mapped[Forwarder] = relationship()
    company: Mapped[Company] = relationship()
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    items: Mapped[list["AvizoItem"]] = relationship(back_populates="request")


class AvizoItem(Base):
    __tablename__ = "avizo_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("avizo_requests.id"), index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    request: Mapped[AvizoRequest] = relationship(back_populates="items")
    container: Mapped["Container"] = relationship()


class AvizoFormToken(Base):
    """Jednorazowy token formularza awizacji (etap 1 = dostawy, etap 2 = kierowcy).
    W bazie tylko hash SHA-256; surowy token istnieje wyłącznie w linku e-mail."""
    __tablename__ = "avizo_form_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("avizo_requests.id"), index=True)
    stage: Mapped[int] = mapped_column(Integer)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    request: Mapped[AvizoRequest] = relationship()


class DeliveryConfirmation(Base):
    """Odpowiedź spedycji z etapu 1 per kontener — stosowana dopiero po zatwierdzeniu."""
    __tablename__ = "avizo_delivery_confirmations"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("avizo_requests.id"), index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    decision: Mapped[str] = mapped_column(String(20))   # confirmed / date_change / problem
    proposed_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    proposed_time: Mapped[str] = mapped_column(String(5), default="")   # slot HH:MM
    comment: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    submit_ip: Mapped[str] = mapped_column(String(64), default="")
    container: Mapped["Container"] = relationship()


class AvizoMailLog(Base):
    """Wynik wysyłki maila awizacji — źródło „błąd wysyłki” i „Wyślij ponownie” w panelu."""
    __tablename__ = "avizo_mail_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("avizo_requests.id"), index=True)
    stage: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20), default="")   # stage1 / stage2 / rejected
    recipients: Mapped[str] = mapped_column(Text, default="")
    cc: Mapped[str] = mapped_column(Text, default="")
    backend: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(10), default="")   # sent / failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class AvizoProposalStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class AvizoChangeProposal(Base):
    """Propozycja zmiany terminu awizacji zgłoszona przez spedycję na tokenowym linku.

    Akceptacja przez logistykę zmienia notify_date kontenera (confirm_plan + audyt);
    odrzucenie z powodem wraca na publiczny formularz."""
    __tablename__ = "avizo_change_proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("avizo_requests.id"), index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    proposed_date: Mapped[datetime.date] = mapped_column(Date)
    proposed_time: Mapped[str] = mapped_column(String(5), default="")   # HH:MM lub puste
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[AvizoProposalStatus] = mapped_column(
        Enum(AvizoProposalStatus), default=AvizoProposalStatus.pending, index=True)
    reject_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    request: Mapped[AvizoRequest] = relationship()
    container: Mapped["Container"] = relationship()
    decided_by: Mapped[User | None] = relationship()


class UnloadPhoto(Base):
    """Zdjęcie z rozładunku przypięte do kontenera (karta rozładunku) —
    wzorzec jak ComplaintPhoto (magic bytes, limit, losowa nazwa)."""
    __tablename__ = "unload_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    caption: Mapped[str] = mapped_column(String(300), default="")
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

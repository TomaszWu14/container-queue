"""Reklamacje / zgłoszenia problemów i checklista kontroli przyjęcia."""
import datetime
import enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .container import Container
from .dictionaries import User
from .enums import utcnow


class ProblemType(Base):
    """Słownik problemów na dostawie (definiowany w panelu admina)."""
    __tablename__ = "problem_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ComplaintKind(str, enum.Enum):
    PROBLEM = "PROBLEM"          # zgłoszenie problemu do magazyniera
    REKLAMACJA = "REKLAMACJA"    # formalna reklamacja (unikalny nr, do spedycji/ubezpieczyciela)


class ComplaintStatus(str, enum.Enum):
    SZKIC = "SZKIC"                      # auto-szkic (np. z opóźnienia) — czeka na logistykę
    NOWA = "NOWA"                        # utworzona
    ZGLOSZONA = "ZGLOSZONA"              # zgłoszona do magazyniera
    WYSLANA = "WYSLANA"                  # wysłana do spedycji/ubezpieczyciela
    ODPOWIEDZ = "ODPOWIEDZ"             # otrzymano odpowiedź
    ZAMKNIETA = "ZAMKNIETA"             # zamknięta / rozwiązana


class Complaint(Base):
    """Zgłoszenie problemu lub reklamacja przypięta do dostawy (kontenera)."""
    __tablename__ = "complaints"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    kind: Mapped[ComplaintKind] = mapped_column(Enum(ComplaintKind),
                                                default=ComplaintKind.PROBLEM)
    status: Mapped[ComplaintStatus] = mapped_column(
        Enum(ComplaintStatus), default=ComplaintStatus.NOWA, index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    driver_note: Mapped[str] = mapped_column(Text, default="")   # komentarz do kierowcy
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    reported_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    sent_target: Mapped[str] = mapped_column(String(200), default="")  # e-mail spedycji/ubezpieczyciela
    response_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    reminders_sent: Mapped[str] = mapped_column(String(120), default="")  # progi dni już przypomniane
    # W11: typ adresata (PRZEWOZNIK/UBEZPIECZYCIEL/DOSTAWCA) — sterowany stringiem,
    # nie enumem DB (bez migracji typu przy zmianie słownika); "" = nie wskazano
    recipient_type: Mapped[str] = mapped_column(
        String(20), default="", server_default=text("''"))
    # W11: auto-szkic z opóźnienia (jeden na kontener — dedup w check_complaint_auto_drafts)
    auto_draft: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), index=True)
    # W11: koszty reklamacji (kwota roszczenia / odzyskana) w walucie roszczenia
    claim_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    recovered_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    claim_currency: Mapped[str] = mapped_column(
        String(3), default="PLN", server_default=text("'PLN'"))
    container: Mapped["Container"] = relationship()
    created_by: Mapped[User | None] = relationship()
    problems: Mapped[list["ComplaintProblem"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan")
    photos: Mapped[list["ComplaintPhoto"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan")


class ComplaintProblem(Base):
    __tablename__ = "complaint_problems"
    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    problem_type_id: Mapped[int] = mapped_column(ForeignKey("problem_types.id"))
    complaint: Mapped[Complaint] = relationship(back_populates="problems")
    problem_type: Mapped[ProblemType] = relationship()


class ComplaintPhoto(Base):
    """Zdjęcie dowodowe (aparat lub załącznik) do zgłoszenia/reklamacji."""
    __tablename__ = "complaint_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    caption: Mapped[str] = mapped_column(String(300), default="")
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    complaint: Mapped[Complaint] = relationship(back_populates="photos")


class ChecklistPoint(Base):
    """Słownik punktów kontroli przyjęcia kontenera (panel admina) — W11 #72."""
    __tablename__ = "checklist_points"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ChecklistResult(Base):
    """Wynik punktu kontroli przyjęcia dla kontenera: OK / NOK / UWAGA + notatka."""
    __tablename__ = "checklist_results"
    __table_args__ = (UniqueConstraint("container_id", "point_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    point_id: Mapped[int] = mapped_column(ForeignKey("checklist_points.id"))
    result: Mapped[str] = mapped_column(String(10))          # OK / NOK / UWAGA
    note: Mapped[str] = mapped_column(Text, default="")
    checked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    checked_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow)
    point: Mapped[ChecklistPoint] = relationship()
    checked_by: Mapped[User | None] = relationship()

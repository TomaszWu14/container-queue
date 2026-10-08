"""Klienci (znacznik), propozycje SENT i SMS-y — bez linków publicznych (decyzja 2026-10-07)."""
import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .dictionaries import User
from .enums import utcnow


class SentLink(Base):
    """Powiązanie numeru SENT z numerem zamówienia."""
    __tablename__ = "sent_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    sent_number: Mapped[str] = mapped_column(String(120))
    order_number: Mapped[str] = mapped_column(String(60), index=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class Customer(Base):
    """Lekki słownik klientów (portal kliencki) — per spółka, przypinany do kontenera."""
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    contact: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class CustomerOrder(Base):
    """Zamówienie specjalnej troski — ręcznie założone zamówienie własnej marki,
    dopasowywane do kontenerów po numerach zamówień (order_refs ⊂ Container.order_numbers).
    Ryzyko liczone w locie w routerze (2 wyzwalacze), nic tu nie cache'ujemy."""
    __tablename__ = "customer_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    customer_name: Mapped[str] = mapped_column(String(200), default="")
    order_refs: Mapped[str] = mapped_column(Text, default="")
    deadline: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    max_etd: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    buffer_days: Mapped[int] = mapped_column(Integer, default=5)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    alert_on_delay: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

    responsible: Mapped["User | None"] = relationship(foreign_keys=[responsible_id])
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])


class SmsMessage(Base):
    """Historia SMS-ów do kierowców (per kontener): status wysyłki + błąd providera."""
    __tablename__ = "sms_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    phone: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent / error
    error: Mapped[str] = mapped_column(String(300), default="")
    # data planowanej dostawy w momencie wysyłki — dedup auto-wysyłki per kontener+data
    delivery_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

"""Audyt, limity dzienne, kalendarz, tokeny, bezpieczeństwo i ustawienia aplikacji."""
import datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .dictionaries import User
from .enums import utcnow


class AuditLog(Base):
    """Ślad zmian wszystkich pól: kto, kiedy, stara i nowa wartość."""
    __tablename__ = "audit_log"
    # Historia encji czytana zawsze po (entity_type, entity_id) z sortem po created_at
    # — złożony indeks pokrywa cały ten wzorzec. Istniejące pojedyncze indeksy
    # entity_type/entity_id zostają (nie usuwamy bez potwierdzenia pg_stat).
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    field: Mapped[str] = mapped_column(String(60))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    # indeks: filtr „kto zmienił” w dziennikach zmian (DB-010)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    user: Mapped[User | None] = relationship()


class DailyLimit(Base):
    """Nadpisanie dziennego limitu rozładunków dla magazynu na konkretny dzień."""
    __tablename__ = "daily_limits"
    __table_args__ = (UniqueConstraint("warehouse_id", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    day: Mapped[datetime.date] = mapped_column(Date)
    limit: Mapped[int] = mapped_column(Integer)


class CalendarDay(Base):
    """Wyjątki kalendarza pracy magazynu: dodatkowy dzień wolny lub pracująca sobota."""
    __tablename__ = "calendar_days"
    __table_args__ = (UniqueConstraint("warehouse_id", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    day: Mapped[datetime.date] = mapped_column(Date)
    is_working: Mapped[bool] = mapped_column(Boolean)  # True = pracujący mimo weekendu/święta
    note: Mapped[str] = mapped_column(String(200), default="")


class RefreshToken(Base):
    """Wydane refresh tokeny — rotowane przy odświeżeniu, odwoływalne przy wylogowaniu."""
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    # moment ROTACJI (nie każdego odwołania) — otwiera okno łaski dla wyścigu kart;
    # odwołanie rodziny (wylogowanie/kradzież) zostawia NULL i łaski nie daje
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class ClientError(Base):
    """Błąd JS z panelu (beacon z ErrorBoundary/window.onerror) — do panelu System."""
    __tablename__ = "client_errors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    stack: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class BlockedIP(Base):
    """Adres IP zablokowany przez admina — logowanie z niego dostaje 403 przed rate-limitem."""
    __tablename__ = "blocked_ips"
    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class LoginFailure(Base):
    """Nieudana próba logowania / 2FA / resetu hasła — stan limitera logowań (ARCH-003,
    SEC-012; rate_limit.LoginRateLimiter). W bazie, nie w pamięci procesu: restart nie
    zeruje liczników, a workery/instancje na wspólnej bazie liczą razem. `key` to SHA-256
    klucza limitera (ip:…, para ip+login, acct:<login>…) — bez jawnego IP i loginu.
    Wiersze starsze niż okno logowań sprząta limiter i dobowa retencja."""
    __tablename__ = "login_failures"
    __table_args__ = (Index("ix_login_failures_key_created", "key", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PasswordResetToken(Base):
    """Jednorazowy token resetu hasła — w bazie trzymamy tylko hash SHA-256,
    z wygaśnięciem. Wyciek bazy nie ujawnia użytecznych tokenów (jak refresh)."""
    __tablename__ = "password_reset_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class AppSetting(Base):
    """Konfiguracja edytowalna z panelu admina (klucz→wartość), np. progi przypomnień."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")

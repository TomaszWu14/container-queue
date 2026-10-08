"""Powiadomienia i śledzenie: obserwowane kontenery, statki, zawinięcia, pozycje AIS, zdarzenia."""
import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .enums import utcnow


class Notification(Base):
    """Powiadomienie w aplikacji (kanały e-mail/Teams wysyłane przy utworzeniu)."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # eta/delay/order/message/file/demurrage
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    # indeks: kasowanie kontenera odpina powiadomienia po tej kolumnie (DB-010)
    container_id: Mapped[int | None] = mapped_column(
        ForeignKey("containers.id"), nullable=True, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class NotificationRule(Base):
    """Matryca reguł powiadomień (admin): kind × rola × kanał → włącz/wyłącz.

    Brak wiersza = zachowanie domyślne (kanał włączony). role='*' dla kanałów
    globalnych (Teams — webhook nie jest per-user)."""
    __tablename__ = "notification_rules"
    __table_args__ = (UniqueConstraint("kind", "role", "channel"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(20))      # wartość Role albo '*'
    channel: Mapped[str] = mapped_column(String(10))   # bell / email / teams
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class WatchedContainer(Base):
    """Gwiazdka „moje kontenery" — subskrypcja usera na kontener (+ kiedy i dlaczego)."""
    __tablename__ = "watched_containers"
    __table_args__ = (UniqueConstraint("user_id", "container_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # unique (user_id, container_id) nie pokrywa samego container_id (kasowanie kontenera)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    reason: Mapped[str] = mapped_column(String(200), default="", server_default="")
    # NULL = obserwacja sprzed 2026-09-24 (brak daty)
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True, default=utcnow)


class WatchedVessel(Base):
    """Gwiazdka na statku (karta statku) — kto, kiedy, dlaczego."""
    __tablename__ = "watched_vessels"
    __table_args__ = (UniqueConstraint("user_id", "vessel_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    vessel_id: Mapped[int] = mapped_column(ForeignKey("tracked_vessels.id"), index=True)
    reason: Mapped[str] = mapped_column(String(200), default="", server_default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class TrackedVessel(Base):
    """Statek śledzony przez AIS (aisstream.io) — pozycja na żywo dla statków z kolejki.

    Klucz dopasowania to znormalizowana NAZWA statku (kolejka zna tylko nazwy);
    MMSI uczymy się automatycznie z metadanych AIS przy pierwszym trafieniu."""
    __tablename__ = "tracked_vessels"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)     # znormalizowana (upper, bez @)
    mmsi: Mapped[int | None] = mapped_column(nullable=True, unique=True, index=True)
    imo: Mapped[int | None] = mapped_column(nullable=True)
    lat: Mapped[float | None] = mapped_column(nullable=True)
    lon: Mapped[float | None] = mapped_column(nullable=True)
    sog: Mapped[float | None] = mapped_column(nullable=True)        # prędkość (kn)
    cog: Mapped[float | None] = mapped_column(nullable=True)        # kurs (deg)
    destination: Mapped[str] = mapped_column(String(80), default="")
    ais_eta: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # geofence: nazwa portu, przy którym statek stoi/manewruje (puste = pełne morze)
    near_port: Mapped[str] = mapped_column(String(40), default="")
    near_port_since: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # wymiary z AIS ShipStaticData (Dimension A+B / C+D) — metry
    length_m: Mapped[int | None] = mapped_column(nullable=True)
    beam_m: Mapped[int | None] = mapped_column(nullable=True)
    # zdjęcie statku: nazwa pliku w uploads/vessels/ (upload admina lub auto-fetch)
    photo: Mapped[str] = mapped_column(String(255), default="", server_default="")


class VesselPortCall(Base):
    """Historia wejść/wyjść statku z portu (geofence) — jeden wiersz = jeden postój."""
    __tablename__ = "vessel_port_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[int] = mapped_column(ForeignKey("tracked_vessels.id"), index=True)
    port: Mapped[str] = mapped_column(String(40))
    arrived_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    departed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


class VesselPosition(Base):
    """Punkt trasy statku z AIS — historia pozycji do rysowania linii przebytej."""
    __tablename__ = "vessel_positions"
    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[int] = mapped_column(ForeignKey("tracked_vessels.id"), index=True)
    lat: Mapped[float]
    lon: Mapped[float]
    at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class PortCongestion(Base):
    """Dzienny zapis kongestii portu: ilu NASZYCH statków stoi na redzie (near_port).

    Lekki INSERT/UPDATE raz na cykl tracking_loop; trend 14 dni zasila mini-wykres
    przy chipie portu i alert »dziś > 2× mediana«."""
    __tablename__ = "port_congestion"
    __table_args__ = (UniqueConstraint("port", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    port: Mapped[str] = mapped_column(String(40), index=True)
    day: Mapped[datetime.date] = mapped_column(Date)
    waiting: Mapped[int] = mapped_column(Integer, default=0)


class TrackingEvent(Base):
    """Zdarzenie z trackingu armatora (oś zdarzeń kontenera)."""
    __tablename__ = "tracking_events"
    __table_args__ = (UniqueConstraint("container_id", "event_code", "occurred_at", "location"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    event_code: Mapped[str] = mapped_column(String(40))       # np. LOAD, DEPART, TRANSSHIP, DISCHARGE
    description: Mapped[str] = mapped_column(String(300), default="")
    location: Mapped[str] = mapped_column(String(160), default="")
    vessel: Mapped[str] = mapped_column(String(160), default="")
    occurred_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(40), default="")  # nazwa providera
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

"""Wywołania-DLT: tokeny Power BI, stany palet, PAZ, wywołania palet i cele stanów."""
import datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .enums import PalletCallStatus, utcnow

# --- Wywołania-DLT ---

class PowerBIToken(Base):
    """Jednorządkowy serializowany cache MSAL (delegated device-code)."""
    __tablename__ = "powerbi_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    cache: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class PalletStockCache(Base):
    """Jednorządkowy cache policzonej analizy per produkt (JSON)."""
    __tablename__ = "pallet_stock_cache"
    id: Mapped[int] = mapped_column(primary_key=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    payload: Mapped[str] = mapped_column(Text, default="[]")        # JSON: list[dict]
    discrepancies: Mapped[str] = mapped_column(Text, default="[]")  # JSON: list[dict]


class ProductPaz(Base):
    """Słownik PAZ: ile sztuk (podst. jedn. miary) mieści się na palecie, per produkt."""
    __tablename__ = "product_paz"
    id: Mapped[int] = mapped_column(primary_key=True)
    produkt: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    sztuk_na_palete: Mapped[float] = mapped_column(Numeric(14, 3))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class MaterialIssue(Base):
    """Historia wydań materiałów (dzienna, per produkt) — podstawa prognozy popytu."""
    __tablename__ = "material_issues"
    __table_args__ = (UniqueConstraint("source_file", "produkt", "date", "magazyn",
                                       name="uq_material_issue"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    produkt: Mapped[str] = mapped_column(String(60), index=True)
    date: Mapped[datetime.date] = mapped_column(Date, index=True)
    qty: Mapped[float] = mapped_column(Numeric(14, 3))
    firma: Mapped[str] = mapped_column(String(60), default="")
    magazyn: Mapped[str] = mapped_column(String(60), default="")
    kontrahent: Mapped[str] = mapped_column(String(120), default="")
    source_file: Mapped[str] = mapped_column(String(200), default="")


class PalletCall(Base):
    __tablename__ = "pallet_calls"
    __table_args__ = (UniqueConstraint("company_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    number: Mapped[str] = mapped_column(String(30))
    status: Mapped[PalletCallStatus] = mapped_column(
        Enum(PalletCallStatus), default=PalletCallStatus.draft)
    needed_by: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    lines: Mapped[list["PalletCallLine"]] = relationship(
        back_populates="call", cascade="all, delete-orphan")
    trucks: Mapped[list["PalletCallTruck"]] = relationship(
        back_populates="call", cascade="all, delete-orphan",
        order_by="PalletCallTruck.ordinal")


class PalletCallLink(Base):
    """Publiczny link DLT do potwierdzeń wywołania — token hashowany jak driver_links.

    Nowa wysyłka wywołania generuje świeży link i wygasza poprzednie;
    „Wysłane" (wyslane_z_dlt) dezaktywuje link na stałe."""
    __tablename__ = "pallet_call_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # SHA-256
    pallet_call_id: Mapped[int] = mapped_column(
        ForeignKey("pallet_calls.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    deactivated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True)
    call: Mapped[PalletCall] = relationship()


class PalletCallTruck(Base):
    """Auto (naczepa) w wywołaniu — 1..4 aut po 33 miejsca paletowe (132 łącznie)."""
    __tablename__ = "pallet_call_trucks"
    __table_args__ = (UniqueConstraint("pallet_call_id", "ordinal",
                                       name="uq_pallet_call_truck"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    pallet_call_id: Mapped[int] = mapped_column(
        ForeignKey("pallet_calls.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)            # 1..4
    capacity: Mapped[int] = mapped_column(Integer, default=33)
    call: Mapped[PalletCall] = relationship(back_populates="trucks")
    lines: Mapped[list["PalletCallLine"]] = relationship(back_populates="truck")


class PalletCallLine(Base):
    """Pozycja wywołania — per produkt, w paletach."""
    __tablename__ = "pallet_call_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    pallet_call_id: Mapped[int] = mapped_column(
        ForeignKey("pallet_calls.id", ondelete="CASCADE"), index=True)
    produkt: Mapped[str] = mapped_column(String(60))
    krotki_opis: Mapped[str] = mapped_column(String(200), default="")
    ilosc_pal: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    data_dostawy: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    truck_id: Mapped[int | None] = mapped_column(
        ForeignKey("pallet_call_trucks.id"), nullable=True)
    hu_numbers: Mapped[str] = mapped_column(Text, default="")   # CSV nr HU z DLT
    pallets: Mapped[float | None] = mapped_column(Numeric(7, 3), nullable=True)  # ułamkowe
    call: Mapped[PalletCall] = relationship(back_populates="lines")
    truck: Mapped[PalletCallTruck | None] = relationship(back_populates="lines")

    @property
    def truck_no(self) -> int | None:
        return self.truck.ordinal if self.truck else None


class DltStock(Base):
    """Ręcznie zaimportowane stany DLT (xlsx) — fallback, gdy Power BI ich nie podaje.

    Snapshot ostatniego importu: każdy import kasuje poprzednie wiersze i wgrywa nowe.
    Wszystkie wiersze traktowane jako DLT (plik = stany magazynu DLT)."""
    __tablename__ = "dlt_stock"
    id: Mapped[int] = mapped_column(primary_key=True)
    produkt: Mapped[str] = mapped_column(String(60), index=True)
    hu: Mapped[str] = mapped_column(String(64), default="")   # nr HU (opcjonalny)
    ilosc: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    lokalizacja: Mapped[str] = mapped_column(String(120), default="")
    source_file: Mapped[str] = mapped_column(String(200), default="")
    imported_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class MaterialStockTarget(Base):
    """Nadpisanie globalnego celu pokrycia zapasu (dni) per materiał."""
    __tablename__ = "material_stock_targets"
    id: Mapped[int] = mapped_column(primary_key=True)
    material_no: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    days: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

"""Dane z SAP: pozycje zamówień, przyjęcia, jednostki materiałów, nagłówki zamówień."""
import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .checks import in_check
from .enums import utcnow
from .typed_text import mirror, parse_quantity


class OrderItem(Base):
    """Pozycja zamówienia (REF) z eksportu SAP — zawartość kontenerów."""
    __tablename__ = "order_items"
    __table_args__ = (UniqueConstraint("company_id", "order_number", "position"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    order_number: Mapped[str] = mapped_column(String(60), index=True)
    position: Mapped[str] = mapped_column(String(20), default="")
    material: Mapped[str] = mapped_column(String(120), default="")   # REF / indeks
    description: Mapped[str] = mapped_column(String(300), default="")
    quantity: Mapped[str] = mapped_column(String(40), default="")   # surowy tekst z pliku
    # DB-008: ilość jako liczba (z `quantity` przy każdym zapisie — mirror niżej); None =
    # tekst nieparsowalny. Obliczenia czytają to pole, tekst zostaje do wglądu
    quantity_num: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="")
    net_weight: Mapped[str] = mapped_column(String(30), default="")
    gross_weight: Mapped[str] = mapped_column(String(30), default="")
    volume: Mapped[str] = mapped_column(String(30), default="")
    volume_unit: Mapped[str] = mapped_column(String(20), default="")
    planned_ship_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class GoodsReceiptLine(Base):
    """Przyjęcie zakupowe — ile faktycznie przyjęto per pozycja zamówienia (OrderItem/EKPO)
    w dostawie kontenera. Klucz (spółka, kontener, order_number, position) 1:1 z OrderItem,
    więc cykl zamówienie→przyjęcie→faktura liczy się pozycyjnie (3-way match: zamówiono
    ↔ przyjęto ↔ zafakturowano). Ilość jako tekst — spójnie z OrderItem.quantity."""
    __tablename__ = "goods_receipt_lines"
    __table_args__ = (UniqueConstraint("company_id", "container_id", "order_number", "position"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    order_number: Mapped[str] = mapped_column(String(60), index=True)
    position: Mapped[str] = mapped_column(String(20), default="", server_default=text("''"))
    material: Mapped[str] = mapped_column(String(120), default="", server_default=text("''"))
    qty_received: Mapped[str] = mapped_column(String(40), default="", server_default=text("''"))
    qty_received_num: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)  # DB-008
    received_at: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(String(300), default="", server_default=text("''"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


mirror(OrderItem.quantity, "quantity_num", parse_quantity)
mirror(GoodsReceiptLine.qty_received, "qty_received_num", parse_quantity)

ACTIVE, MISSING_IN_SAP = "aktywny", "brak_w_sap"


class MaterialUnit(Base):
    """Jednostka alternatywna materiału z eksportu SAP MARM (przeliczniki + objętość).
    Master data globalne (bez company_id) — numer materiału jest wspólny dla spółek."""
    __tablename__ = "material_units"
    __table_args__ = (UniqueConstraint("material_no", "unit", name="uq_material_unit"),
                      in_check("material_units", "sap_status", (ACTIVE, MISSING_IN_SAP)))
    id: Mapped[int] = mapped_column(primary_key=True)
    material_no: Mapped[str] = mapped_column(String(60), index=True)
    unit: Mapped[str] = mapped_column(String(10))                     # MEINH
    numerator: Mapped[int] = mapped_column(Integer, default=1)        # UMREZ
    denominator: Mapped[int] = mapped_column(Integer, default=1)      # UMREN
    volume: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)  # VOLUM
    volume_unit: Mapped[str] = mapped_column(String(10), default="")  # VOLEH
    gross_weight: Mapped[float | None] = mapped_column(Numeric(14, 3), nullable=True)  # BRGEW
    weight_unit: Mapped[str] = mapped_column(String(10), default="")  # GEWEI
    length: Mapped[float | None] = mapped_column(Numeric(14, 3), nullable=True)   # LAENG
    width: Mapped[float | None] = mapped_column(Numeric(14, 3), nullable=True)    # BREIT
    height: Mapped[float | None] = mapped_column(Numeric(14, 3), nullable=True)   # HOEH
    dimension_unit: Mapped[str] = mapped_column(String(10), default="")           # MEABM
    # DATA-003: „brak_w_sap” = nieobecny w pełnym eksporcie SAP (nie kasujemy); powrót → „aktywny”
    sap_status: Mapped[str] = mapped_column(String(20), default="aktywny",
                                            server_default=text("'aktywny'"))
    ean: Mapped[str] = mapped_column(String(20), default="", server_default=text("''"))   # EAN11
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

    _DIM_TO_CM = {"MM": 0.1, "CM": 1.0, "M": 100.0, "MTR": 100.0}

    def dims_cm(self) -> tuple[float, float, float] | None:
        """Wymiary jednostki (dł, szer, wys) znormalizowane do cm; None gdy brak
        kompletu wymiarów albo nieznana jednostka MEABM."""
        factor = self._DIM_TO_CM.get((self.dimension_unit or "").upper())
        if factor is None or not (self.length and self.width and self.height):
            return None
        return (float(self.length) * factor, float(self.width) * factor,
                float(self.height) * factor)


class SapOrder(Base):
    """Nagłówek zamówienia zakupu z eksportu SAP (EKKO) — warstwa nad OrderItem (EKPO):
    ten sam `order_number`, ale dane zamówienia jako całości (dostawca, incoterms,
    port załadunku, wartość, daty wysyłki). Odpowiedź na „co płynie, skąd i kiedy”
    zanim pojawi się fizyczny kontener.

    Kolumny stałe w eksporcie (jednostka gosp. ZP01, schemat RM0000, NIP) pominięte —
    nie niosą informacji. Flagi SAP („X”/pusto) trzymamy jako bool."""
    __tablename__ = "sap_orders"
    __table_args__ = (UniqueConstraint("company_id", "order_number"),
                      in_check("sap_orders", "sap_status", (ACTIVE, MISSING_IN_SAP)))
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    order_number: Mapped[str] = mapped_column(String(60), index=True)
    container_id: Mapped[int | None] = mapped_column(
        ForeignKey("containers.id"), nullable=True, index=True)
    doc_kind: Mapped[str] = mapped_column(String(10), default="")       # ZTF / ZTFC / ZTD
    supplier_sap: Mapped[str] = mapped_column(String(20), default="", index=True)  # LIFNR
    buyer: Mapped[str] = mapped_column(String(40), default="")          # utworzone przez
    buyer_group: Mapped[str] = mapped_column(String(10), default="")    # grupa zaopatrzeniowa
    payment_terms: Mapped[str] = mapped_column(String(20), default="")
    payment_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="")
    fx_rate: Mapped[float | None] = mapped_column(Numeric(12, 5), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)  # w PLN
    incoterms: Mapped[str] = mapped_column(String(10), default="")      # FOB / DAP / EXW
    incoterms_place: Mapped[str] = mapped_column(String(60), default="")  # port załadunku
    doc_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    delivery_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    required_ship_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    planned_ship_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    supplier_order_no: Mapped[str] = mapped_column(String(60), default="")
    is_asap: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    supplier_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"))
    artwork_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"))
    # DATA-003: „brak_w_sap” = nieobecny w pełnym eksporcie SAP (nie kasujemy); powrót → „aktywny”
    sap_status: Mapped[str] = mapped_column(String(20), default="aktywny",
                                            server_default=text("'aktywny'"))
    imported_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow)

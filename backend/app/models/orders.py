"""Materiały, przeliczniki jednostek i zamówienia (Order / PurchaseOrder)."""
import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
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
from .typed_text import mirror, parse_text_date
from .dictionaries import Company, ContainerType, Port, Supplier, SupplierContact, User
from .enums import CartStatus, MainMode, SeaService, utcnow

if TYPE_CHECKING:  # cykl: container importuje orders; w runtime relację rozwiązuje rejestr
    from .container import Container


class Material(Base):
    """Master data materiałów (REF → nazwa PL, kod CN, SENT, jm bazowa) — globalna dla grupy.

    Zasila dopasowanie pozycji faktur (invoices/matching) i Excel „Faktury → Excel”.
    `ref_norm` = REF bez separatorów (NL753-S-40 → NL753S40): faktury dostawców piszą ten
    sam kod na kilka sposobów. Wartości per spółka nadpisuje `MaterialOverride`."""
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref_code: Mapped[str] = mapped_column(String(100), unique=True)
    ref_norm: Mapped[str] = mapped_column(String(100), index=True, default="")
    name_pl: Mapped[str] = mapped_column(String(500), default="")
    name_en: Mapped[str] = mapped_column(String(500), default="")
    ean: Mapped[str] = mapped_column(String(14), default="")
    family: Mapped[str] = mapped_column(String(160), default="")
    base_uom: Mapped[str] = mapped_column(String(20), default="")
    producer_code: Mapped[str] = mapped_column(String(60), default="")
    tariff_cn: Mapped[str] = mapped_column(String(30), default="")
    customs_code: Mapped[str] = mapped_column(String(30), default="")
    vat_rate: Mapped[str] = mapped_column(String(10), default="")
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    supplier_codes: Mapped[str] = mapped_column(String(500), default="")
    # poziomy opakowań (sztuka/op/opz/karton/paz/ppa: wymiar, ean, artwork, qty_base)
    levels_json: Mapped[str] = mapped_column(Text, default="{}")
    # jednostka uzupełniająca taryfy (np. „pary") i przelicznik z jednostki podstawowej
    suppl_unit: Mapped[str] = mapped_column(String(20), default="", server_default=text("''"))
    suppl_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    overrides: Mapped[list["MaterialOverride"]] = relationship(
        back_populates="material", cascade="all, delete-orphan", lazy="selectin")


class MaterialOverride(Base):
    """Nadpisanie pól materiału dla jednej spółki (np. inny kod CN w Iberia).

    Puste pole tekstowe / NULL w `sent` = bez nadpisania (obowiązuje wartość globalna)."""
    __tablename__ = "material_overrides"
    __table_args__ = (UniqueConstraint("material_id", "company_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name_pl: Mapped[str] = mapped_column(String(500), default="")
    tariff_cn: Mapped[str] = mapped_column(String(30), default="")
    customs_code: Mapped[str] = mapped_column(String(30), default="")
    base_uom: Mapped[str] = mapped_column(String(20), default="")
    sent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    material: Mapped[Material] = relationship(back_populates="overrides")


class SupplierMaterialMap(Base):
    """Mapowanie: numer artykułu u dostawcy → nasz indeks (Material.ref_code), per spółka
    i dostawca. Najwyższy priorytet przy dopasowaniu pozycji faktury — operator ustala je
    na stałe, zanim zadziałają reguły REF i ML. Dedykowany słownik zamiast luźnego
    Material.supplier_codes (string), więc da się nim zarządzać i testować."""
    __tablename__ = "supplier_material_maps"
    __table_args__ = (UniqueConstraint("company_id", "supplier_id", "supplier_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    supplier_code: Mapped[str] = mapped_column(String(120))
    ref_code: Mapped[str] = mapped_column(String(120))
    note: Mapped[str] = mapped_column(String(300), default="", server_default=text("''"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class UomConversion(Base):
    """Przelicznik jednostek: 1 `unit_from` = `factor` × `unit_to` (np. CTN→PCS 24).

    `ref_norm` = '*' to reguła globalna; import master daty tworzy reguły per REF
    z przeliczników poziomów opakowań (qty_base)."""
    __tablename__ = "uom_conversions"
    __table_args__ = (UniqueConstraint("ref_norm", "unit_from", "unit_to"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ref_norm: Mapped[str] = mapped_column(String(100), default="*")
    unit_from: Mapped[str] = mapped_column(String(20))
    unit_to: Mapped[str] = mapped_column(String(20))
    factor: Mapped[float] = mapped_column(Numeric(14, 4))


class Order(Base):
    """Zamówienie (PO) — może obejmować wiele kontenerów."""
    __tablename__ = "orders"
    # *_trgm: GIN pg_trgm pod ?q= kolejki po numerze PO (migracja fkidx001); SQLite: zwykły
    __table_args__ = (UniqueConstraint("company_id", "number"),
                      Index("ix_orders_number_trgm", "number", postgresql_using="gin",
                            postgresql_ops={"number": "gin_trgm_ops"}))
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(60))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id"), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    # --- pola zlecenia (Borealis/Cobalt): dane spedycyjne uzupełniane przy zakładaniu ---
    supplier_contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_contacts.id"), nullable=True)
    departure_port_id: Mapped[int | None] = mapped_column(ForeignKey("ports.id"), nullable=True)
    container_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("container_types.id"), nullable=True)
    # VARCHAR(9) jak w migracji e4f5a6b7c8d9 (nie natywny enum PG — DB-003)
    main_mode: Mapped[MainMode | None] = mapped_column(
        Enum(MainMode, native_enum=False, length=9), nullable=True)
    sea_service: Mapped[SeaService | None] = mapped_column(
        Enum(SeaService, native_enum=False, length=9), nullable=True)
    container_count: Mapped[int] = mapped_column(Integer, default=1)
    goods_type: Mapped[str] = mapped_column(String(200), default="")
    is_adr: Mapped[bool] = mapped_column(Boolean, default=False)
    goods_classification: Mapped[str] = mapped_column(String(200), default="")
    goods_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    goods_currency: Mapped[str] = mapped_column(String(3), default="USD")
    goods_weight: Mapped[str] = mapped_column(String(60), default="")
    readiness_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    company: Mapped[Company] = relationship()
    supplier: Mapped[Supplier | None] = relationship()
    supplier_contact: Mapped["SupplierContact | None"] = relationship()
    departure_port: Mapped["Port | None"] = relationship()
    container_type: Mapped["ContainerType | None"] = relationship()
    created_by: Mapped["User | None"] = relationship()
    containers: Mapped[list["Container"]] = relationship(back_populates="order")


class PurchaseOrder(Base):
    """Zamówienie zakupowe z arkusza ETD (co ACME zamówił u dostawców z Chin) —
    wcześniejszy etap niż kontener: pozycja istnieje zanim dostanie fizyczny kontener
    i numer. Linkowana do Container po numerze zamówienia (order_no ⊂ Container.order_numbers).
    Osobny byt od Order (zlecenie spedycyjne) — inny cel i cykl życia.

    Pola ready_date/oem_sample_date jako tekst: źródłowy arkusz miesza daty z wpisami
    typu „Confirmed" w tych kolumnach — trzymamy 1:1, bez utraty."""
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("company_id", "order_no"),
                      in_check("purchase_orders", "cart_status", [c.value for c in CartStatus]))
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    order_no: Mapped[str] = mapped_column(String(120), index=True)
    container_id: Mapped[int | None] = mapped_column(
        ForeignKey("containers.id"), nullable=True, index=True)
    etd: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    supplier: Mapped[str] = mapped_column(String(160), default="")
    pi_no: Mapped[str] = mapped_column(String(120), default="")
    products: Mapped[str] = mapped_column(Text, default="")
    cbm: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    crd: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    crd_target: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    cart_status: Mapped[str] = mapped_column(
        String(20), default=CartStatus.w_koszyku.value,
        server_default=CartStatus.w_koszyku.value)
    tt_type: Mapped[str] = mapped_column(String(40), default="")
    transport_mode: Mapped[str] = mapped_column(String(40), default="")
    purchase_decision: Mapped[str] = mapped_column(String(20), default="")
    port_of_departure: Mapped[str] = mapped_column(String(120), default="")
    container_type: Mapped[str] = mapped_column(String(40), default="")
    expected_inland_charge: Mapped[str] = mapped_column(String(80), default="")
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    ready_date: Mapped[str] = mapped_column(String(60), default="")
    oem_sample_date: Mapped[str] = mapped_column(String(60), default="")
    # DB-008: te same daty jako Date (sortowanie/filtry); None = wpis nie-data („Confirmed”)
    ready_on: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    oem_sample_on: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    shipper_contact: Mapped[str] = mapped_column(String(200), default="")
    consignee: Mapped[str] = mapped_column(String(120), default="")
    port_of_discharge: Mapped[str] = mapped_column(String(120), default="")
    forwarder: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow)


mirror(PurchaseOrder.ready_date, "ready_on", parse_text_date)
mirror(PurchaseOrder.oem_sample_date, "oem_sample_on", parse_text_date)

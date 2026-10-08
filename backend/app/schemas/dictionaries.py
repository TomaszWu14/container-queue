"""Słowniki i master data: dostawcy, spedycje, agencje, porty, typy kontenerów, magazyny."""
import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import MainMode, PortCategory, SeaService
from .base import ORMModel, _validate_email

# --- dictionaries ---

class NamedIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    is_active: bool = True


class NamedOut(ORMModel):
    id: int
    name: str


class CarrierIn(NamedIn):
    # dni wolne od demurrage u armatora (2026-09-28); pusty = domyślna z konfiguracji
    demurrage_free_days: int | None = Field(default=None, ge=0, le=60)

    @field_validator("demurrage_free_days", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return None if v in ("", None) else v


class CarrierOut(NamedOut):
    demurrage_free_days: int | None = None


class MergeIn(BaseModel):
    """Scalenie duplikatu słownika: rekordy wskazujące na źródło przepinamy na cel."""
    target_id: int


class MergeOut(BaseModel):
    target_id: int
    repinned: dict[str, int]   # tabela -> liczba przepiętych wierszy


class SupplierIn(NamedIn):
    # tylko przy tworzeniu: spółka-klient → nadawca tej spółki; spółka z materiałami Acme
    # albo brak → kartoteka (deps.is_material_company). PATCH ignoruje.
    company_id: int | None = None
    address: str = ""
    note: str = ""
    # mapa kolumn faktur tego dostawcy: "ref=Item No.; qty=Q'ty; net=Amount" (puste = auto)
    column_map: str = Field(default="", max_length=2000)


class SupplierOut(NamedOut):
    # None = kartoteka dostawców Acme; id = nadawca kontenerów tej spółki-klienta
    client_company_id: int | None = None
    is_active: bool
    address: str = ""
    note: str = ""
    column_map: str = ""
    sap_code: str = ""   # LIFNR z importu LFA1 (przeglądarka master data)
    country: str = ""


class SupplierStatContainerOut(BaseModel):
    id: int
    container_no: str
    status: str
    eta: datetime.date | None
    atd: datetime.date | None
    notify_date: datetime.date | None
    model_config = ConfigDict(from_attributes=True)


class SupplierStatsOut(BaseModel):
    active_containers: int
    on_time_pct: float | None      # % ukończonych dostaw z atd <= eta
    avg_transit_days: float | None  # średnio dni etd -> atd
    recent_containers: list[SupplierStatContainerOut]


class ForwarderOut(NamedOut):
    is_active: bool
    email: str = ""
    contact_person: str = ""
    contact_phone: str = ""
    address: str = ""
    note: str = ""
    language: str = "pl"


class ForwarderIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str = ""
    is_active: bool = True
    contact_person: str = ""
    contact_phone: str = ""
    address: str = ""
    note: str = ""
    language: Literal["pl", "en"] = "pl"   # język maili/formularzy awizacji

    _check_email = field_validator("email")(_validate_email)


class CustomsAgencyOut(NamedOut):
    is_active: bool
    email: str = ""
    contact_person: str = ""
    contact_phone: str = ""
    address: str = ""
    note: str = ""
    export_format: str = "standard"
    export_params: dict | None = None


class CustomsAgencyIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str = ""
    is_active: bool = True
    contact_person: str = ""
    contact_phone: str = ""
    address: str = ""
    note: str = ""
    export_format: Literal["standard", "symbols"] = "standard"
    export_params: dict = {}

    _check_email = field_validator("email")(_validate_email)


# --- master data portów / typy kontenerów / kontakty dostawcy ---

class PortIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    country: str = Field(default="CN", max_length=2)
    category: PortCategory = PortCategory.OUT
    transit_time_days: int | None = Field(default=None, ge=0, le=200)
    transit_time_long_days: int | None = Field(default=None, ge=0, le=200)
    is_active: bool = True
    # sezonowy transit time: miesiąc (1-12) -> dni. Pusta mapa = brak danych miesięcznych,
    # wtedy liczy się transit_time_days. Pełne nadpisanie przy każdym zapisie.
    monthly_transit: dict[int, int] = Field(default_factory=dict)

    @field_validator("monthly_transit")
    @classmethod
    def _check_months(cls, value: dict[int, int]) -> dict[int, int]:
        for month, days in value.items():
            if not 1 <= month <= 12:
                raise ValueError("Miesiąc musi być z zakresu 1-12.")
            if not 0 <= days <= 200:
                raise ValueError("Transit time musi być z zakresu 0-200 dni.")
        return value


class PortOut(NamedOut):
    country: str = "CN"
    category: PortCategory = PortCategory.OUT
    transit_time_days: int | None = None
    transit_time_long_days: int | None = None
    is_active: bool = True
    monthly_transit: dict[int, int] = Field(default_factory=dict)


class ContainerTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    inner_length_m: Decimal | None = Field(default=None, ge=0)
    inner_width_m: Decimal | None = Field(default=None, ge=0)
    inner_height_m: Decimal | None = Field(default=None, ge=0)
    max_payload_kg: int | None = Field(default=None, ge=0)
    teu: Decimal | None = Field(default=None, ge=0)


class ContainerTypeOut(NamedOut):
    inner_length_m: Decimal | None = None
    inner_width_m: Decimal | None = None
    inner_height_m: Decimal | None = None
    max_payload_kg: int | None = None
    teu: Decimal | None = None
    volume_m3: float | None = None
    is_active: bool = True


class SupplierContactIn(BaseModel):
    supplier_id: int
    full_name: str = Field(min_length=1, max_length=160)
    email: str = ""
    phone: str = Field(default="", max_length=60)

    _check_email = field_validator("email")(_validate_email)


class SupplierContactOut(ORMModel):
    id: int
    supplier_id: int
    full_name: str
    email: str = ""
    phone: str = ""
    is_active: bool = True


# --- zakładanie zlecenia (Borealis/Cobalt): jedno zamówienie → N rekordów kontenerów ---

class FoundOrderIn(BaseModel):
    number: str = Field(min_length=1, max_length=60)
    company_id: int | None = None
    company_code: str | None = None   # użyte gdy company_id brak (np. admin bez wczytanej listy spółek)
    supplier_id: int | None = None
    supplier_name: str | None = Field(default=None, max_length=160)  # tworzy dostawcę w locie
    supplier_contact_id: int | None = None
    departure_port_id: int | None = None
    container_type_id: int | None = None
    main_mode: MainMode | None = None
    sea_service: SeaService | None = None
    container_count: int = Field(default=1, ge=1, le=50)
    goods_type: str = Field(default="", max_length=200)
    is_adr: bool = False
    goods_classification: str = Field(default="", max_length=200)
    goods_value: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    goods_currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    goods_weight: str = Field(default="", max_length=60)
    readiness_date: datetime.date | None = None
    notes: str = ""


class FxConvertOut(BaseModel):
    amount: Decimal
    currency: str
    rates: dict[str, float]          # waluta → kurs w PLN (z NBP)
    converted: dict[str, float]      # waluta → kwota po przeliczeniu
    as_of: str | None = None         # data notowania NBP
    available: bool = True           # False gdy NBP nieosiągalne (fallback)


class DriverIn(BaseModel):
    """Dane kierowcy uzupełniane przez spedycję."""
    driver_name: str = ""
    driver_id_no: str = ""
    truck_no: str = ""
    trailer_no: str = ""
    driver_phone: str = ""
    # blokada optymistyczna jak w PATCH kontenera: updated_at z chwili otwarcia formularza
    expected_updated_at: datetime.datetime | None = None


class QueueEmailIn(BaseModel):
    company_code: str
    day: datetime.date
    warehouse_id: int | None = None


class OrderItemOut(ORMModel):
    id: int
    order_number: str
    position: str
    material: str
    description: str
    quantity: str
    unit: str
    net_weight: str
    gross_weight: str
    volume: str
    volume_unit: str
    planned_ship_date: datetime.date | None
    computed_volume_m3: float | None = None   # objętość z MARM (ilość × obj. jednostki)


class MaterialUnitOut(ORMModel):
    id: int
    material_no: str
    unit: str
    numerator: int
    denominator: int
    volume: float | None
    volume_unit: str
    gross_weight: float | None
    weight_unit: str
    length: float | None
    width: float | None
    height: float | None
    dimension_unit: str
    sap_status: str = "aktywny"


class ContainerPortOut(ORMModel):
    id: int
    code: str
    name: str
    country_code: str
    country_name: str
    lat: float | None
    lon: float | None
    is_active: bool


class SentLinkOut(ORMModel):
    id: int
    sent_number: str
    order_number: str
    note: str
    created_at: datetime.datetime


class SentLinkIn(BaseModel):
    sent_number: str = Field(min_length=3, max_length=120)
    order_number: str = Field(min_length=1, max_length=60)
    note: str = ""


class WarehouseIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str = ""
    company_id: int | None = None
    country: str = Field(default="PL", pattern="^(PL|PT)$")
    default_daily_limit: int = Field(default=7, ge=0)
    # dane dla kierowcy (strona dostawy z linku SMS)
    address: str = Field(default="", max_length=300)
    contact_phone: str = Field(default="", max_length=40)
    entry_instructions: str = ""
    # #13 sloty: "07:00,08:00" (puste = wyłączone) + pojemność okna
    slot_windows: str = Field(default="", max_length=200, pattern=r"^(\s*\d{2}:\d{2}\s*(,\s*\d{2}:\d{2}\s*)*)?$")
    slot_capacity: int = Field(default=1, ge=1, le=50)

    _check_email = field_validator("email")(_validate_email)


class WarehouseOut(NamedOut):
    company_id: int
    country: str
    default_daily_limit: int
    is_active: bool
    email: str = ""
    address: str = ""
    contact_phone: str = ""
    entry_instructions: str = ""
    slot_windows: str = ""
    slot_capacity: int = 1


class WarehouseNameIn(BaseModel):
    """Zmiana magazynu rozładunku po nazwie (menu kontekstowe w kolejce)."""
    name: str = Field(min_length=1, max_length=160)

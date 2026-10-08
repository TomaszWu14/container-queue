"""Kontenery (tworzenie, edycja, odczyt), szczegóły zamówienia z kontenerami, tracking."""
import datetime

from pydantic import BaseModel, Field, field_validator

from .. import iso6346
from ..models import (
    SPECIAL_REASONS, ContainerStatus, CustomsStatus, DocumentStatus, OnCarriage, PurchasingStatus,
    TransportType,
)
from .base import ORMModel, _validate_op_date
from .orders import OrderOut

_OP_DATES = ("eta", "atd", "notify_date", "proposed_delivery_date", "customs_date")


class OrderDetailOut(OrderOut):
    containers: list["ContainerOut"] = []


# --- containers ---

class ContainerBase(BaseModel):
    container_no: str
    order_id: int | None = None
    order_number: str | None = None  # wygodne tworzenie PO w locie
    supplier_id: int | None = None
    forwarder_id: int | None = None
    warehouse_id: int | None = None
    is_transit: bool = False
    customer_name: str = ""
    customer_address: str = ""
    customer_contact: str = ""
    port_id: int | None = None
    carrier_id: int | None = None
    vessel: str = ""
    eta: datetime.date | None = None
    atd: datetime.date | None = None
    notify_date: datetime.date | None = None
    proposed_delivery_date: datetime.date | None = None
    transport_type: TransportType | None = None
    transport_details: str = ""
    on_carriage: OnCarriage | None = None
    container_size: str = ""
    documents_ok: bool = False
    document_status: DocumentStatus = DocumentStatus.BRAK
    customs_status: CustomsStatus = CustomsStatus.BRAK
    customs_note: str = ""
    customs_date: datetime.date | None = None
    customs_agency: str = ""
    demurrage_free_days: int | None = None
    incoming_delivery_no: str = ""
    rf_number: str = ""
    notes: str = ""
    order_numbers: str = ""
    delivery_note: str = ""
    purchase_note: str = ""
    document_flow: str = ""
    sent_required: bool | None = None
    sent_number: str = ""
    sent_status: str = ""
    materials_list: str = Field(default="", max_length=8000)
    palletization_note: str = Field(default="", max_length=4000)
    pallet_count: int | None = Field(default=None, ge=0, le=100000)
    _check_op_dates = field_validator(*_OP_DATES)(_validate_op_date)

    @field_validator("container_no")
    @classmethod
    def validate_container_no(cls, v: str) -> str:
        n = iso6346.normalize(v)
        ok, message = iso6346.validate(n)
        if not ok:
            raise ValueError(message)
        return n


class ContainerCreate(ContainerBase):
    company_id: int | None = None  # admin/Acme mogą wskazać spółkę
    status: ContainerStatus = ContainerStatus.ZAPOWIEDZIANY


class ContainerUpdate(BaseModel):
    # wszystkie pola opcjonalne; None = bez zmiany
    container_no: str | None = None
    order_id: int | None = None
    supplier_id: int | None = None
    forwarder_id: int | None = None
    warehouse_id: int | None = None
    is_transit: bool | None = None
    customer_name: str | None = None
    customer_address: str | None = None
    customer_contact: str | None = None
    port_id: int | None = None
    carrier_id: int | None = None
    vessel: str | None = None
    eta: datetime.date | None = None
    atd: datetime.date | None = None
    notify_date: datetime.date | None = None
    proposed_delivery_date: datetime.date | None = None
    transport_type: TransportType | None = None
    transport_details: str | None = None
    on_carriage: OnCarriage | None = None
    container_size: str | None = None
    documents_ok: bool | None = None
    document_status: DocumentStatus | None = None
    customs_status: CustomsStatus | None = None
    customs_note: str | None = None
    customs_date: datetime.date | None = None
    customs_agency: str | None = None
    purchasing_status: PurchasingStatus | None = None
    demurrage_free_days: int | None = None
    incoming_delivery_no: str | None = None
    rf_number: str | None = None
    notes: str | None = None
    order_numbers: str | None = None
    delivery_note: str | None = None
    purchase_note: str | None = None
    document_flow: str | None = None
    sent_required: bool | None = None
    sent_number: str | None = None
    sent_status: str | None = None
    materials_list: str | None = Field(default=None, max_length=8000)
    palletization_note: str | None = Field(default=None, max_length=4000)
    pallet_count: int | None = Field(default=None, ge=0, le=100000)
    change_note: str = ""  # opcjonalny komentarz do zmiany (np. powód przeniesienia awizacji)
    # blokada optymistyczna (audyt DB-005): `updated_at` z chwili otwarcia formularza; inny = 409
    expected_updated_at: datetime.datetime | None = None
    _check_op_dates = field_validator(*_OP_DATES)(_validate_op_date)

    @field_validator("container_no")
    @classmethod
    def validate_container_no(cls, v: str | None) -> str | None:
        if v is None:
            return v
        n = iso6346.normalize(v)
        ok, message = iso6346.validate(n)
        if not ok:
            raise ValueError(message)
        return n


class StatusChange(BaseModel):
    status: ContainerStatus
    note: str = ""


# powody flagi „specjalny" (dropdown śledzenia) — wspólny kontrakt FE/BE; definicja w
# models.enums (CHECK ck_containers_special_reason, DB-007)


class SpecialIn(BaseModel):
    """Ustawienie flagi śledzenia: włącz/wyłącz + powód (dropdown) + komentarz."""
    is_special: bool
    reason: str | None = None
    note: str = ""

    @field_validator("reason")
    @classmethod
    def _reason_known(cls, v: str | None) -> str | None:
        if v and v not in SPECIAL_REASONS:
            raise ValueError(f"nieznany powód śledzenia: {v}")
        return v


class WatchIn(BaseModel):
    """Gwiazdka „Obserwuj": opcjonalny powód (szybki powód albo własny tekst)."""
    reason: str = Field("", max_length=200)


class ContainerOut(ORMModel):
    id: int
    container_no: str
    is_transit: bool = False
    is_special: bool = False
    special_reason: str | None = None
    special_note: str = ""
    customs_t1: bool = False
    needs_forwarding: bool = False
    customer_id: int | None = None
    customer_name: str = ""
    customer_address: str = ""
    customer_contact: str = ""
    planning_status: str = "PROPOZYCJA"
    notify_date_manual: bool = False
    slot_time: str = ""
    ramp_stage: str | None = None
    # ostrzeżenie (nie blokada): inne kontenery tego samego dostawcy z tą samą datą
    # awizacji — ustawiane tylko w odpowiedzi PATCH przy zmianie notify_date
    notify_conflict: int | None = None
    # ostrzeżenie (nie blokada): to samo zlecenie transportowe ma tego samego dnia
    # dostawy do RÓŻNYCH magazynów — lista nazw magazynów; tylko w odpowiedzi zapisu
    transport_conflict: list[str] | None = None
    # ostrzeżenie (nie blokada, decyzja 9): status ZWOLNIONY/ODPRAWIONY/DOSTARCZONY przy brakach
    # wymaganych dokumentów — tylko w odpowiedzi zmiany statusu
    docs_warning: str | None = None
    planning_sent_at: datetime.datetime | None = None
    planning_confirmed_at: datetime.datetime | None = None
    planning_eta_at_send: datetime.date | None = None
    company_id: int
    company_name: str | None = None
    order_id: int | None
    order_number: str | None = None
    supplier_id: int | None
    supplier_name: str | None = None
    supplier_raw: str = ""
    forwarder_id: int | None
    forwarder_name: str | None = None
    warehouse_id: int | None
    warehouse_name: str | None = None
    port_id: int | None
    port_name: str | None = None
    carrier_id: int | None
    carrier_name: str | None = None
    status: ContainerStatus
    customs_status: CustomsStatus
    purchasing_status: PurchasingStatus = PurchasingStatus.BRAK
    customs_note: str
    customs_date: datetime.date | None
    customs_agency: str
    customs_agency_id: int | None = None
    customs_agency_name: str | None = None
    customs_agent_name: str = ""
    customs_agent_phone: str = ""
    customs_agent_email: str = ""
    customs_assigned_at: datetime.datetime | None = None
    customs_case_status_id: int | None = None
    customs_case_status_name: str | None = None
    # braki checklisty dokumentów — wypełniane tylko przez tablicę odpraw
    missing_documents: list[str] | None = None
    vessel: str
    eta: datetime.date | None
    etd: datetime.date | None = None
    eta_estimate: datetime.date | None = None   # D12: ETD + transit portu, gdy brak ETA
    atd: datetime.date | None = None
    notify_date: datetime.date | None
    proposed_delivery_date: datetime.date | None
    transport_type: TransportType | None
    transport_details: str
    on_carriage: OnCarriage | None = None
    container_size: str
    documents_ok: bool
    document_status: DocumentStatus = DocumentStatus.BRAK
    demurrage_free_days: int | None
    # termin demurrage (przybycie/ETA + dni wolne) — liczony tylko na liście kolejki
    demurrage_deadline: datetime.date | None = None
    incoming_delivery_no: str
    rf_number: str
    notes: str
    transport_id: str | None
    order_numbers: str
    delivery_note: str
    purchase_note: str
    document_flow: str
    sent_required: bool | None
    sent_number: str
    sent_status: str
    materials_list: str = ""
    palletization_note: str = ""
    pallet_count: int | None = None
    driver_name: str
    driver_id_no: str
    truck_no: str
    trailer_no: str
    driver_phone: str
    # pomiar czasu rozładunku (karta rozładunku, #61)
    unload_started_at: datetime.datetime | None = None
    unload_finished_at: datetime.datetime | None = None
    is_delayed: bool
    is_stuck: bool = False   # w porcie po ETA, bez awizacji — inna akcja niż opóźnienie
    status_age_days: int | None = None
    customer_order: str | None = None   # flaga „pod klienta": klient z modułu specjalnej troski
    vessel_mismatch: bool = False   # #35: rozne statki w eventach = mozliwy przeladunek
    created_at: datetime.datetime
    updated_at: datetime.datetime
    completed_at: datetime.datetime | None
    tracked_at: datetime.datetime | None
    tracking_error: str


class TrackingEventOut(ORMModel):
    id: int
    event_code: str
    description: str
    location: str
    vessel: str
    occurred_at: datetime.datetime | None
    is_estimated: bool
    source: str


class TrackedVesselOut(ORMModel):
    id: int
    name: str
    mmsi: int | None
    imo: int | None = None
    lat: float | None
    lon: float | None
    sog: float | None
    cog: float | None
    destination: str
    ais_eta: datetime.datetime | None
    last_seen: datetime.datetime | None
    trail: list[list[float]] = []        # przebyta trasa [[lat, lon], …]
    companies: list[str] = []            # kody spółek z kontenerami na pokładzie (+TRANZYT)
    containers: int = 0                  # kontenery na pokładzie (w zakresie usera)
    delayed: int = 0                     # z tego opóźnione → wskaźnik pilności
    drift_days: int | None = None        # ETA statku (AIS) − najwcześniejsze ETA kontenera
    eta_alert: bool = False              # drift >= tracking_eta_alert_days
    hours_to_dest: float | None = None   # godziny żeglugi do portu docelowego
    near_port: str = ""                  # geofence: port, przy którym statek stoi
    predicted_late: bool = False         # prognoza z pozycji+prędkości: nie zdąży na ETA
    length_m: int | None = None          # długość (AIS Dimension A+B)
    beam_m: int | None = None            # szerokość (AIS Dimension C+D)
    has_photo: bool = False              # jest zdjęcie w uploads/vessels/
    watchers: list[dict] = []            # {user_id, name, has_avatar} wg can_see_watcher
    watched: list[dict] = []             # WŁASNE obserwowane kontenery na pokładzie: {id, container_no, reason}


class TimelineEntryOut(BaseModel):
    kind: str        # order | carrier | vessel | system | planned
    code: str        # np. PO_ETD, DEPART, PORT_ARRIVE, STATUS_W_PORCIE, ETA, NOTIFY
    title: str       # etykieta PL (fallback gdy front nie zna kodu)
    location: str
    at: datetime.datetime | None
    estimated: bool
    source: str


class TrackingSyncOut(BaseModel):
    eta_changed: bool
    status_changed: bool
    new_events: int
    container: "ContainerOut"

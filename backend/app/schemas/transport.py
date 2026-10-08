"""Moduł spedytora: zlecenia transportowe, wyceny (RFQ), wiadomości, załączniki."""
import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from ..models import QuoteStatus, Role, TransportJobStatus, TransportOrderStatus
from .base import ORMModel

# --- moduł spedytora ---

class TransportOrderIn(BaseModel):
    container_id: int
    forwarder_id: int | None = None  # domyślnie spedytor przypisany do kontenera
    pickup_location: str = ""
    delivery_location: str = ""
    pickup_date: datetime.date | None = None
    delivery_date: datetime.date | None = None
    instructions: str = ""


class TransportOrderStatusIn(BaseModel):
    status: TransportOrderStatus
    reason: str = ""  # wymagany przy odrzuceniu


class TransportOrderOut(ORMModel):
    id: int
    container_id: int
    container_no: str | None = None
    company_id: int
    forwarder_id: int
    forwarder_name: str | None = None
    status: TransportOrderStatus
    pickup_location: str
    delivery_location: str
    pickup_date: datetime.date | None
    delivery_date: datetime.date | None
    instructions: str
    rejection_reason: str
    created_by_login: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


# --- wyceny (RFQ): zlecenie transportowe = paczka kontenerów do wyceny ---

class TransportJobCreate(BaseModel):
    container_ids: list[int] = Field(min_length=1)
    forwarder_ids: list[int] = Field(min_length=1)  # zaproszone spedycje
    pickup_location: str = ""
    delivery_location: str = ""
    note: str = ""
    response_hours: int = Field(default=24, ge=1, le=336)   # termin odpowiedzi (domyślnie 24h)
    scfi_index: str = Field(default="", max_length=60)


class JobUpdateIn(BaseModel):
    """Edycja zlecenia (logistyka): termin/SCFI/nr przesyłki oraz dane odbioru/dostawy."""
    response_hours: int | None = Field(default=None, ge=1, le=336)
    scfi_index: str | None = Field(default=None, max_length=60)
    shipment_number: str | None = Field(default=None, max_length=80)
    pickup_location: str | None = Field(default=None, max_length=200)
    delivery_location: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=4000)


class AgentIn(BaseModel):
    """Dane agenta uzupełniane przez wygrywającą spedycję po wyborze oferty.
    Wszystkie pola wymagane (imię i nazwisko, telefon, firma)."""
    agent_name: str = Field(min_length=1, max_length=160)
    agent_phone: str = Field(min_length=1, max_length=60)
    agent_company: str = Field(min_length=1, max_length=160)
    shipment_number: str = Field(default="", max_length=80)  # Q49: numer przesyłki podaje zwycięska spedycja


class CancelJobIn(BaseModel):
    """Anulowanie zlecenia z obowiązkowym powodem (wiersz 20)."""
    reason: str = Field(min_length=1, max_length=2000)


class PriceRevisionIn(BaseModel):
    """Pilna zmiana ceny zgłaszana przez zwycięską spedycję (wiersz 21)."""
    revised_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    revised_note: str = Field(default="", max_length=2000)


class QuoteSubmitIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="PLN", pattern="^(PLN|USD|EUR)$")
    valid_until: datetime.date | None = None
    note: str = ""
    carrier_id: int | None = None
    etd: datetime.date | None = None
    eta: datetime.date | None = None
    transit_time_days: int | None = Field(default=None, ge=0, le=200)
    no_equipment: bool = False
    can_roll_booking: bool = False


class ChooseQuoteIn(BaseModel):
    quote_id: int
    reason: str = Field(default="", max_length=2000)  # wymagany przy wyborze spoza rekomendacji (Q40)


class QuoteOut(ORMModel):
    id: int
    forwarder_id: int
    forwarder_name: str | None = None
    status: QuoteStatus
    amount: Decimal | None = None
    currency: str
    valid_until: datetime.date | None
    note: str
    carrier_id: int | None = None
    carrier_name: str | None = None
    etd: datetime.date | None = None
    eta: datetime.date | None = None
    transit_time_days: int | None = None
    no_equipment: bool = False
    can_roll_booking: bool = False
    submitted_at: datetime.datetime | None
    # pilna zmiana ceny (wiersz 21 / Q55-56) — niepuste = oczekuje na akceptację logistyki
    revised_amount: Decimal | None = None
    revised_note: str = ""
    revised_at: datetime.datetime | None = None
    # ranking ważony ofert (Q39) — score 0-100 i flaga rekomendacji (tylko dla logistyki)
    score: int | None = None
    recommended: bool = False


class QuoteRevisionOut(ORMModel):
    id: int
    amount: Decimal | None = None
    currency: str
    note: str = ""
    kind: str = "wycena"
    created_by_login: str | None = None
    created_at: datetime.datetime


class JobContainerOut(BaseModel):
    container_id: int
    container_no: str
    supplier_name: str | None = None
    # Q34: kontakt do dostawcy widoczny dla spedycji w RFQ (ułatwia awizację załadunku)
    supplier_contact_name: str | None = None
    supplier_contact_email: str | None = None
    supplier_contact_phone: str | None = None
    order_numbers: str = ""
    warehouse_name: str | None = None
    eta: datetime.date | None = None
    notify_date: datetime.date | None = None


class JobKpi(BaseModel):
    invited: int = 0            # zaproszone spedycje
    responded: int = 0          # ile podało cenę
    expired: int = 0            # ile nie zdążyło przed terminem
    response_rate: int = 0      # % odpowiedzi
    deadline_passed: bool = False


class TransportJobOut(BaseModel):
    id: int
    number: str
    status: TransportJobStatus
    pickup_location: str
    delivery_location: str
    note: str
    created_at: datetime.datetime
    sent_at: datetime.datetime | None
    response_hours: int = 24
    response_deadline: datetime.datetime | None = None
    scfi_index: str = ""
    shipment_number: str = ""
    agent_name: str = ""
    agent_phone: str = ""
    agent_company: str = ""
    agent_submitted_at: datetime.datetime | None = None
    cancel_reason: str = ""
    cancelled_at: datetime.datetime | None = None
    chosen_quote_id: int | None
    container_count: int
    kpi: JobKpi = JobKpi()
    containers: list[JobContainerOut] = []
    quotes: list[QuoteOut] = []      # dla spedytora tylko własna oferta
    my_quote: QuoteOut | None = None  # oferta zalogowanego spedytora


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class MessageOut(ORMModel):
    id: int
    container_id: int
    body: str
    user_login: str | None = None
    user_full_name: str | None = None
    user_role: Role | None = None
    created_at: datetime.datetime


class AttachmentOut(ORMModel):
    id: int
    container_id: int
    filename: str
    content_type: str
    size: int
    uploaded_by_login: str | None = None
    document_type_id: int | None = None
    document_type_name: str | None = None
    created_at: datetime.datetime
    # bramka wgrania (document_gate): „niepewny” — wpuszczony, ale z ostrzeżeniem dla użytkownika
    gate_warning: str | None = None
    # attachment_rules.flags: co pokazać w UI (backend i tak pilnuje)
    can_delete: bool = False
    can_replace: bool = False
    replace_needs_reason: bool = False
    # wspólny plik (attachment_links): pozostałe kontenery pliku; właściciel — gdy oglądany z powiązanego
    shared_with: list[str] = []
    owner_container_no: str | None = None
    can_unlink: bool = False

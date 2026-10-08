"""Zamówienia: zamówienia zakupu, mapy materiałów dostawcy, przyjęcia, linie zamówień."""
import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, computed_field

from ..consolidation import crd_deviation_days
from ..models import MainMode, SeaService
from .base import ORMModel

# --- orders ---

class OrderIn(BaseModel):
    number: str = Field(min_length=1, max_length=60)
    company_id: int | None = None
    supplier_id: int | None = None
    notes: str = ""


class OrderProgress(BaseModel):
    total: int = 0
    delivered: int = 0            # DOSTARCZONY + ZREALIZOWANY
    at_port_or_customs: int = 0   # W_PORCIE + ODPRAWA + AWIZOWANY + W_DOSTAWIE
    in_transit: int = 0           # etapy 1–3 (zapowiedziany/produkcja/wstępny) + W_TRANSPORCIE
    delayed: int = 0
    percent: int = 0              # % kontenerów dostarczonych
    derived_status: str = "PUSTE"  # PUSTE / NOWE / W_TOKU / ZAKONCZONE


class PurchaseOrderOut(ORMModel):
    """Zamówienie zakupowe z ETD (wczesny etap przed kontenerem)."""
    id: int
    order_no: str
    supplier: str
    pi_no: str
    products: str
    cbm: float | None = None
    container_type: str
    tt_type: str
    transport_mode: str
    etd: datetime.date | None = None
    ready_date: str
    port_of_departure: str
    forwarder: str
    amount: float | None = None
    container_id: int | None = None
    # przeglądarka master data: spółka, decyzja zakupowa i data utworzenia rekordu
    company_id: int
    purchase_decision: str
    created_at: datetime.datetime
    crd: datetime.date | None = None
    crd_target: datetime.date | None = None
    cart_status: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def deviation_days(self) -> int | None:
        return crd_deviation_days(self)


class SupplierMaterialMapOut(ORMModel):
    """Wpis słownika mapowań: kod artykułu dostawcy → nasz ref_code."""
    id: int
    company_id: int
    supplier_id: int
    supplier_code: str
    ref_code: str
    note: str


class SupplierMaterialMapIn(BaseModel):
    company_code: str | None = None   # wymagane przy tworzeniu; PATCH używa spółki wpisu
    supplier_id: int | None = None
    supplier_code: str
    ref_code: str
    note: str = ""


class ReceiptLineIn(BaseModel):
    """Zapis przyjęcia zakupowego dla pozycji zamówienia (upsert po order_number+position)."""
    order_number: str
    position: str = ""
    material: str = ""
    qty_received: str = ""
    received_at: datetime.date | None = None
    note: str = ""


class ReceiptLineOut(ORMModel):
    id: int
    container_id: int
    order_number: str
    position: str
    material: str
    qty_received: str
    received_at: datetime.date | None = None
    note: str


class OrderLineOut(BaseModel):
    """3-way per pozycja: zamówiono (OrderItem) vs przyjęto (GoodsReceiptLine) vs
    zafakturowano (InvoiceItem po ref). `status`/`status_invoice` porównują odpowiednio
    przyjęte i zafakturowane do zamówionego. Zafakturowano liczone per ref (materiał)."""
    order_number: str
    position: str
    material: str
    description: str
    ordered_qty: str
    received_qty: str
    invoiced_qty: str = ""
    receipt_id: int | None = None
    status: str            # zamówiono vs przyjęto: ok | partial | over | none | unknown
    status_invoice: str = "none"   # zamówiono vs zafakturowano


class OrderOut(ORMModel):
    id: int
    number: str
    company_id: int
    company_name: str | None = None
    supplier_id: int | None
    supplier_name: str | None = None
    notes: str
    container_count: int = 0            # faktyczna liczba rekordów kontenerów
    planned_container_count: int = 0    # liczba kontenerów zaplanowana przy zakładaniu zlecenia
    progress: OrderProgress = OrderProgress()
    # --- pola zlecenia (Borealis/Cobalt) ---
    supplier_contact_id: int | None = None
    supplier_contact_name: str | None = None
    departure_port_id: int | None = None
    departure_port_name: str | None = None
    container_type_id: int | None = None
    container_type_name: str | None = None
    main_mode: MainMode | None = None
    sea_service: SeaService | None = None
    goods_type: str = ""
    is_adr: bool = False
    goods_classification: str = ""
    goods_value: Decimal | None = None
    goods_currency: str = "USD"
    goods_weight: str = ""
    readiness_date: datetime.date | None = None
    created_by_id: int | None = None
    created_by_login: str | None = None
    created_at: datetime.datetime | None = None

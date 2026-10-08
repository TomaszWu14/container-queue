"""Faktury (CIPL) → Excel: pozycje, zadania, partie, przegląd."""
import datetime

from pydantic import BaseModel, Field

from ..models import InvoiceDocKind, InvoiceJobStatus, InvoiceMatchStatus
from .base import ORMModel

# --- faktury (CIPL) → Excel ---

class InvoiceItemOut(ORMModel):
    id: int
    line_no: int
    raw_ref: str
    descr: str
    qty: str
    uom_src: str
    net_amount: str
    amount: str
    weight_net: str
    weight_gross: str
    cartons: str
    weight_source: str
    master_ref: str
    name_pl: str
    tariff_cn: str
    sent: bool
    uom_factor: str
    match_status: InvoiceMatchStatus
    match_source: str = ""
    ml_suggestion: str = ""
    ml_confidence: float | None = None
    skipped: bool


class InvoiceJobOut(ORMModel):
    id: int
    batch_id: int
    filename: str
    doc_kind: InvoiceDocKind
    status: InvoiceJobStatus
    error: str
    invoice_number: str
    container_no: str
    delivery_terms: str
    page_from: int
    page_to: int
    ocr_used: bool = False
    items_count: int = 0
    updated_at: datetime.datetime
    processing_started_at: datetime.datetime | None = None   # „przetwarzanie od …” w UI
    attempts: int = 0


class InvoiceJobDetailOut(InvoiceJobOut):
    items: list[InvoiceItemOut] = []


class InvoiceBatchOut(ORMModel):
    id: int
    container_id: int
    supplier_id: int | None = None
    supplier_name: str | None = None
    total: int = 0          # dokumenty faktura-podobne
    confirmed: int = 0
    errors: int = 0
    ready: bool                 # wszystkie dokumenty faktura-podobne zatwierdzone (wyliczane)
    excel_current: bool = False   # wygenerowany Excel odpowiada bieżącemu stanowi pozycji
    jobs: list[InvoiceJobOut] = []
    attachment_id: int | None = None
    attachment_filename: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    skipped: list[str] = []   # tylko odpowiedź wgrania: pliki pominięte jako duble (§4 pkt 16)


class InvoiceItemIn(BaseModel):
    """Pola edytowalne w weryfikacji — pole pominięte w JSON (None) zostaje bez zmian,
    żeby częściowa aktualizacja (np. samo „pomiń”) nie zerowała ilości i kwoty."""
    id: int
    master_ref: str | None = Field(default=None, max_length=100)
    qty: str | None = Field(default=None, max_length=40)
    amount: str | None = Field(default=None, max_length=40)
    weight_net: str | None = Field(default=None, max_length=40)
    weight_gross: str | None = Field(default=None, max_length=40)
    skipped: bool | None = None


class InvoiceReviewIn(BaseModel):
    items: list[InvoiceItemIn] = []
    invoice_number: str | None = Field(default=None, max_length=80)
    confirm: bool = False
    # powód zatwierdzenia dokumentu „niepewnego” (bramka zgodności z dostawą)
    conformity_reason: str | None = Field(default=None, max_length=500)

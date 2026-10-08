"""Master data materiałów, moduł agencji celnej, dokumenty, powiadomienia, audyt."""
import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import CustomsStatus, PurchasingStatus
from .base import ORMModel, _validate_email

# --- master data materiałów ---

class MaterialOverrideIn(BaseModel):
    company_id: int
    name_pl: str = Field(default="", max_length=500)
    tariff_cn: str = Field(default="", max_length=30)
    customs_code: str = Field(default="", max_length=30)
    base_uom: str = Field(default="", max_length=20)
    sent: bool | None = None


class MaterialOverrideOut(ORMModel):
    company_id: int
    name_pl: str
    tariff_cn: str
    customs_code: str
    base_uom: str
    sent: bool | None = None


class MaterialOut(ORMModel):
    id: int
    ref_code: str
    name_pl: str
    name_en: str
    ean: str
    family: str
    base_uom: str
    producer_code: str
    tariff_cn: str
    customs_code: str
    vat_rate: str
    sent: bool
    is_active: bool
    overrides: list[MaterialOverrideOut] = []
    updated_at: datetime.datetime
    suppl_unit: str = ""
    suppl_factor: float | None = None


class MaterialIn(BaseModel):
    """Ręczna edycja pojedynczego materiału (PATCH): tylko pola podane w JSON są zmieniane."""
    name_pl: str | None = Field(default=None, max_length=500)
    name_en: str | None = Field(default=None, max_length=500)
    base_uom: str | None = Field(default=None, max_length=20)
    tariff_cn: str | None = Field(default=None, max_length=30)
    customs_code: str | None = Field(default=None, max_length=30)
    sent: bool | None = None
    is_active: bool | None = None
    suppl_unit: str | None = Field(default=None, max_length=20)
    suppl_factor: float | None = Field(default=None, gt=0)


class MaterialImportOut(BaseModel):
    dry_run: bool
    counts: dict[str, int]


class MlStatsOut(BaseModel):
    ref_materials: int = 0
    ref_examples: int = 0
    ref_trained_at: str | None = None
    dockind_examples: int = 0
    dockind_classes: list[str] = []
    dockind_trained: bool = False
    dockind_trained_at: str | None = None
    auto_apply_threshold: float
    min_examples: int


class CustomsUpdateIn(BaseModel):
    """Spedytor aktualizuje status odprawy. Agencję celną przypisuje wyłącznie logistyka ze słownika
    (POST /customs/containers/{id}/assign) — wolny tekst agencji usunięty (decyzja 2026-09-28),
    a nieznane pola dają 422, żeby stary klient nie myślał, że zapisał agencję."""
    model_config = ConfigDict(extra="forbid")
    customs_status: CustomsStatus | None = None
    customs_note: str | None = None
    customs_date: datetime.date | None = None


# --- moduł agencji celnej (nowy obieg) ---

class CustomsAssignIn(BaseModel):
    """Logistyka zleca odprawę wskazanej agencji celnej (lub zmienia agencję)."""
    customs_agency_id: int
    customs_date: datetime.date | None = None
    customs_note: str = ""


class CustomsAgentIn(BaseModel):
    """Agencja celna wyznacza/zmienia agenta prowadzącego odprawę."""
    customs_agent_name: str = Field(default="", max_length=160)
    customs_agent_phone: str = Field(default="", max_length=40)
    customs_agent_email: str = Field(default="", max_length=160)

    _check_email = field_validator("customs_agent_email")(_validate_email)


class CustomsStatusIn(BaseModel):
    """Zmiana statusu odprawy (obie strony) + notatka do drugiej strony."""
    customs_status: CustomsStatus
    customs_note: str = ""
    customs_date: datetime.date | None = None
    customs_t1: bool | None = None


class CustomsCaseStatusOut(ORMModel):
    """Wpis słownika statusów sprawy celnej (panel admina)."""
    id: int
    name: str
    sort_order: int
    is_active: bool


class CustomsCaseStatusIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    sort_order: int = 100
    is_active: bool = True


class CustomsCaseStatusSetIn(BaseModel):
    """Agencja (lub nasi) ustawia status sprawy ze słownika; None = wyczyść."""
    customs_case_status_id: int | None
    customs_note: str = ""


class DocumentTypeOut(ORMModel):
    """Typ dokumentu (checklista kompletności, panel admina)."""
    id: int
    name: str
    sort_order: int
    is_active: bool
    is_required: bool
    tile_code: str | None = None


class DocumentTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    sort_order: int = 100
    is_active: bool = True
    is_required: bool = False
    # kafelek dokumentów dostawy: PI / CI / PL / BL / SAD_DRAFT / SAD_PZ / SAD_PW (albo brak)
    tile_code: Literal["PI", "CI", "PL", "BL", "SAD_DRAFT", "SAD_PZ", "SAD_PW"] | None = None


class SendDocsIn(BaseModel):
    """Wysyłka dokumentów do agencji; force=True wysyła mimo braków w checkliście."""
    force: bool = False


class AttachmentSuggestionOut(ORMModel):
    """Propozycja podpięcia dokumentu z OCR do kontenera (W5 #31)."""
    id: int
    job_id: int
    container_id: int
    doc_kind: str
    status: str
    document_type_id: int | None = None
    attachment_id: int | None = None
    created_at: datetime.datetime
    # kontekst z joba — bez drugiego zapytania na froncie
    filename: str | None = None
    invoice_number: str | None = None
    page_from: int | None = None
    page_to: int | None = None
    container_no: str | None = None


class SuggestionAcceptIn(BaseModel):
    """Akceptacja propozycji: opcjonalny typ dokumentu ze słownika admina."""
    document_type_id: int | None = None


class DocSendTemplateIn(BaseModel):
    """Szablon wysyłki dokumentów do agencji (W5 #36). Placeholdery:
    {container_no}, {eta}, {lista_dokumentow}."""
    customs_agency_id: int | None = None
    subject: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=8000)


class DocSendTemplateOut(ORMModel):
    id: int
    customs_agency_id: int | None = None
    customs_agency_name: str | None = None
    subject: str
    body: str
    updated_at: datetime.datetime


class PurchasingStatusIn(BaseModel):
    """Zmiana statusu działu zakupów (jedyne pole edytowalne przez rolę purchasing)."""
    purchasing_status: PurchasingStatus


class NotificationOut(ORMModel):
    id: int
    kind: str
    title: str
    body: str
    container_id: int | None
    is_read: bool
    created_at: datetime.datetime


class AuditOut(ORMModel):
    id: int
    entity_type: str
    entity_id: int
    field: str
    old_value: str | None
    new_value: str | None
    note: str
    user_id: int | None
    user_login: str | None = None
    created_at: datetime.datetime

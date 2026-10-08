import datetime

from pydantic import BaseModel, Field, field_validator

from ..invoices.extractor import COLUMN_ROLES, ROLE_ALIASES


def _check_map(v: dict[str, list[str]]) -> dict[str, list[str]]:
    # nazwy ról z compare (description, net_weight…) → nazwy ekstraktora
    v = {ROLE_ALIASES.get(k, k): al for k, al in v.items()}
    bad = sorted(set(v) - set(COLUMN_ROLES))
    if bad:
        raise ValueError(f"nieznane role kolumn: {', '.join(bad)}")
    return {k: [a.strip() for a in al if a.strip()] for k, al in v.items() if any(a.strip() for a in al)}


class SupplierDocProfileIn(BaseModel):
    status: str = Field(default="draft", pattern="^(draft|active)$")
    currency: str = Field(default="", max_length=3)
    doc_language: str = Field(default="", max_length=10)
    keywords: list[str] = []
    ci_map: dict[str, list[str]] = {}
    pl_map: dict[str, list[str]] = {}
    ref_kind: str = Field(default="ours", pattern="^(ours|supplier)$")
    split_marker: str = Field(default="", max_length=60)
    tol_amount_pct: float = Field(default=0.5, ge=0, le=100)
    tol_qty_pct: float = Field(default=0.0, ge=0, le=100)

    _maps = field_validator("ci_map", "pl_map")(_check_map)

    @field_validator("keywords")
    @classmethod
    def _kw(cls, v: list[str]) -> list[str]:
        return [k.strip() for k in v if k.strip()]


class SampleOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    filename: str
    created_at: datetime.datetime | None
    last_test: dict = {}
    last_test_at: datetime.datetime | None


class SupplierDocProfileOut(SupplierDocProfileIn):
    model_config = {"from_attributes": True}
    id: int | None = None          # None = dostawca nie ma jeszcze profilu (karta: „brak”)
    supplier_id: int
    samples: list[SampleOut] = []
    required_docs: list[str] | None = None   # None = domyślny zestaw kafelków (decyzja 16)


class RequiredDocsIn(BaseModel):
    codes: list[str] | None = None            # None = przywróć domyślne

    @field_validator("codes")
    @classmethod
    def _known(cls, v: list[str] | None) -> list[str] | None:
        from ..document_tiles import TILES
        if v is None:
            return v
        bad = sorted(set(v) - set(TILES))
        if bad:
            raise ValueError(f"nieznane kody dokumentów: {', '.join(bad)}")
        return [c for c in TILES if c in v]

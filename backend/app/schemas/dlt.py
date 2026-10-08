"""Wywołania-DLT: analiza, PAZ, wywołania palet, cele stanów."""
import datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Wywołania-DLT ---
class AnalysisRow(BaseModel):
    produkt: str
    stan_mag_pal: float | None = None
    stan_dlt_pal: float | None = None
    dostawy_pal: float = 0
    zlec_niepotw_pal: float = 0
    zlec_potw_pal: float = 0
    wywolane_pal: float = 0
    projekcja_mag_pal: float | None = None
    dni_zapasu: float | None = None
    pilne: bool = False
    sugestia_pal: float | None = None
    # rozszerzony dataset PBI (feature-detect — stare cache/kostki bez tych pól)
    stan_mag_szt: float = 0
    stan_dlt_szt: float = 0
    zuzycie_szt_dzien: float = 0
    cel_dni: int | None = None
    hu: list[dict] = []                    # stany DLT per HU: {hu, ilosc}


class AnalysisPage(BaseModel):
    items: list[AnalysisRow]
    total: int
    fetched_at: datetime.datetime | None = None
    discrepancies: list[dict] = []
    features: dict = {}                    # {hu: bool, daily_usage: bool}


class PazIn(BaseModel):
    produkt: str
    sztuk_na_palete: float = Field(gt=0)


class PazOut(PazIn):
    id: int
    updated_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)


class PalletCallLineIn(BaseModel):
    produkt: str
    krotki_opis: str = ""
    ilosc_pal: float = Field(gt=0)         # zajmowane miejsca paletowe (pełne palety)
    data_dostawy: datetime.date | None = None
    note: str = ""
    truck_no: int | None = Field(default=None, ge=1, le=4)   # przydział do auta 1..4
    hu_numbers: str = ""                   # CSV wskazanych HU z DLT
    pallets: float | None = Field(default=None, gt=0)        # ułamkowe palety (np. 7.3)


class PalletCallLineOut(PalletCallLineIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class PalletCallTruckOut(BaseModel):
    id: int
    ordinal: int
    capacity: int
    model_config = ConfigDict(from_attributes=True)


class PalletCallCreate(BaseModel):
    company_id: int | None = None      # wymagane dla admina (cross-company)
    needed_by: datetime.date | None = None
    notes: str = ""
    allow_over_dlt: bool = False       # pozwól wywołać więcej palet niż stan w DLT
    lines: list[PalletCallLineIn]


class PalletCallUpdate(BaseModel):
    needed_by: datetime.date | None = None
    notes: str | None = None
    lines: list[PalletCallLineIn] | None = None


class PalletCallOut(BaseModel):
    id: int
    number: str
    status: str
    needed_by: datetime.date | None
    notes: str
    created_at: datetime.datetime
    sent_at: datetime.datetime | None
    lines: list[PalletCallLineOut]
    trucks: list[PalletCallTruckOut] = []
    model_config = ConfigDict(from_attributes=True)


class StockTargetIn(BaseModel):
    material_no: str = Field(min_length=1, max_length=60)
    days: int = Field(ge=0, le=365)


class StockTargetOut(StockTargetIn):
    id: int
    updated_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)


class StockTargetsPage(BaseModel):
    global_days: int
    items: list[StockTargetOut]

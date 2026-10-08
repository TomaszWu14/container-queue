# Profil dostawcy — etap 1: model danych i API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tabele profilu dokumentów dostawcy i próbek, nowe pola materiału (jednostka uzupełniająca) i agencji (format eksportu), przeniesienie `Supplier.column_map` do profilu oraz API odczytu/zapisu profilu.

**Architecture:** Nowy moduł modeli `app/models/supplier_profiles.py` (re-eksport w `app/models/__init__.py`), jedna migracja alembica od aktualnej głowy z backfillem `column_map → ci_map`, nowy router `app/routers/supplier_profiles.py` (GET/PUT profilu, scoping jak słownik dostawców). Etapy 2–5 (ekstrakcja, kontrole, kreator, eksport) mają osobne plany i korzystają z tych nazw.

**Tech Stack:** FastAPI, SQLAlchemy 2 (Mapped), Alembic, Pydantic v2, pytest (SQLite w testach, Postgres na prodzie).

Spec: `docs/superpowers/specs/2026-09-24-profil-dostawcy-ci-pl-agencja-design.md`.

## Global Constraints

- Gałąź `claude/profil-dostawcy-1-model`, jeden PR; commit z liniami `Co-Authored-By`/`Claude-Session` wg repo.
- Pliki ≤ 500 linii (`python scripts/check_file_lengths.py` musi przejść).
- Migracja od **jedynej** głowy alembica (sprawdź `alembic heads` przed pisaniem; na 2026-09-24 = `trgm001`).
- Test przy każdej zmianie; przed PR: pełny `pytest` w `backend/` (jeden przebieg na katalog roboczy).
- Role kolumn = istniejące `COLUMN_ROLES` z `app/invoices/extractor.py` (`ref, desc, qty, price, net, unit, lot, weight_net, weight_gross, cartons, no`); rodzaj kolumny `ref` rozstrzyga pole profilu `ref_kind` (`ours` = nasz REF, `supplier` = kod dostawcy → `SupplierMaterialMap`). *Odstępstwo od nazw z spec (`ref_ours/supplier_code`) — zgodność z działającym ekstraktorem.*
- Format eksportu agencji: `standard` | `symbols`; `export_params` JSON (domyślnie `{}`; dla `symbols` spodziewane `IDZestawu`).

---

### Task 1: Modele + migracja z backfillem

**Files:**
- Create: `backend/app/models/supplier_profiles.py`
- Modify: `backend/app/models/__init__.py` (dopisz import)
- Modify: `backend/app/models/orders.py` (klasa `Material`: 2 pola)
- Modify: `backend/app/models/dictionaries.py` (klasa `CustomsAgency`: 2 pola)
- Create: `backend/migrations/versions/profil001_profil_dostawcy.py`
- Test: `backend/tests/test_supplier_profiles.py`

**Interfaces:**
- Produces: `SupplierDocProfile(id, supplier_id, currency, doc_language, status, keywords:list[str], ci_map:dict[str,list[str]], pl_map:dict[str,list[str]], ref_kind:str, split_marker:str, tol_amount_pct:float, tol_qty_pct:float, updated_at)`, `SupplierDocSample(id, profile_id, filename, stored_path, created_at, last_test:dict, last_test_at)`, `Material.suppl_unit:str`, `Material.suppl_factor:float|None`, `CustomsAgency.export_format:str`, `CustomsAgency.export_params:dict`; w migracji funkcja modułowa `ci_map_from_column_map(text:str) -> dict[str, list[str]]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_supplier_profiles.py
"""Profil dokumentów dostawcy (etap 1): model, backfill column_map, API."""
import importlib.util
import pathlib

from app.database import SessionLocal
from app.models import CustomsAgency, Material, Supplier, SupplierDocProfile, SupplierDocSample


def _migration():
    path = pathlib.Path(__file__).parents[1] / "migrations/versions/profil001_profil_dostawcy.py"
    spec = importlib.util.spec_from_file_location("profil001", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ci_map_from_column_map():
    conv = _migration().ci_map_from_column_map
    assert conv("ref=Item No.; qty=Q'ty; net=Amount") == {
        "ref": ["Item No."], "qty": ["Q'ty"], "net": ["Amount"]}
    assert conv("") == {}
    assert conv("foo=Bar; qty=") == {}          # nieznana rola / pusty alias pomijane


def test_models_roundtrip(client, admin_headers):
    company = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    sup = client.post("/api/suppliers", headers=admin_headers,
                      json={"name": "Pulp House", "company_id": company}).json()
    with SessionLocal() as db:
        p = SupplierDocProfile(supplier_id=sup["id"], keywords=["PULP HOUSE"],
                               ci_map={"qty": ["Quantity"]}, pl_map={}, ref_kind="ours")
        db.add(p)
        db.flush()
        db.add(SupplierDocSample(profile_id=p.id, filename="a.pdf", stored_path="x/a.pdf"))
        db.add(CustomsAgency(name="Delta Brokers", export_format="symbols",
                             export_params={"IDZestawu": 106}))
        db.add(Material(ref_code="145851", suppl_unit="pary", suppl_factor=0.5))
        db.commit()
        got = db.get(SupplierDocProfile, p.id)
        assert (got.status, got.currency, got.tol_amount_pct, got.tol_qty_pct) == ("draft", "", 0.5, 0.0)
        assert got.ci_map == {"qty": ["Quantity"]} and len(got.samples) == 1
        assert db.query(CustomsAgency).filter_by(name="Delta Brokers").one().export_params == {"IDZestawu": 106}
        assert db.get(Supplier, sup["id"]).doc_profile.id == p.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_supplier_profiles.py -q`
Expected: FAIL — `ImportError: cannot import name 'SupplierDocProfile'` / brak pliku migracji.

- [ ] **Step 3: Implement models**

```python
# backend/app/models/supplier_profiles.py
"""Profil dokumentów dostawcy (CI + packing list) i próbki do testu — spec
2026-09-24-profil-dostawcy-ci-pl-agencja. Mapy kolumn: rola (COLUMN_ROLES ekstraktora)
→ lista aliasów nagłówka. `ref_kind`: kolumna `ref` to nasz REF (`ours`) albo kod
dostawcy (`supplier`, tłumaczony przez SupplierMaterialMap)."""
import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .enums import utcnow

__all__ = ["SupplierDocProfile", "SupplierDocSample"]


class SupplierDocProfile(Base):
    __tablename__ = "supplier_doc_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="draft")        # draft | active
    currency: Mapped[str] = mapped_column(String(3), default="")
    doc_language: Mapped[str] = mapped_column(String(10), default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    ci_map: Mapped[dict] = mapped_column(JSON, default=dict)
    pl_map: Mapped[dict] = mapped_column(JSON, default=dict)
    ref_kind: Mapped[str] = mapped_column(String(10), default="ours")      # ours | supplier
    split_marker: Mapped[str] = mapped_column(String(60), default="")      # np. „PACKING LIST"
    tol_amount_pct: Mapped[float] = mapped_column(Float, default=0.5)
    tol_qty_pct: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    supplier: Mapped["Supplier"] = relationship(back_populates="doc_profile")  # noqa: F821
    samples: Mapped[list["SupplierDocSample"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", lazy="selectin")


class SupplierDocSample(Base):
    __tablename__ = "supplier_doc_samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("supplier_doc_profiles.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    last_test: Mapped[dict] = mapped_column(JSON, default=dict)
    last_test_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    profile: Mapped[SupplierDocProfile] = relationship(back_populates="samples")
```

W `backend/app/models/__init__.py` dopisz w kolejności alfabetycznej: `from .supplier_profiles import *  # noqa: F401,F403`.

W `backend/app/models/dictionaries.py`, klasa `Supplier`, pod `column_map` dopisz:

```python
    # profil dokumentów (CI + PL) — zastępuje column_map (czytane zapasowo do usunięcia)
    doc_profile: Mapped["SupplierDocProfile | None"] = relationship(  # noqa: F821
        back_populates="supplier", uselist=False)
```

W klasie `CustomsAgency` pod `note` dopisz (import `JSON` do listy importów z `sqlalchemy`):

```python
    # format pliku do agencji: standard (Excel pozycji) | symbols (Kartoteka symboli)
    export_format: Mapped[str] = mapped_column(String(20), default="standard", server_default=text("'standard'"))
    export_params: Mapped[dict] = mapped_column(JSON, default=dict)   # np. {"IDZestawu": 106}
```

W `backend/app/models/orders.py`, klasa `Material`, pod `levels_json` dopisz (import `Float` jeśli brak):

```python
    # jednostka uzupełniająca taryfy (np. „pary") i przelicznik z jednostki podstawowej
    suppl_unit: Mapped[str] = mapped_column(String(20), default="", server_default=text("''"))
    suppl_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
```

- [ ] **Step 4: Write migration**

Sprawdź głowę: `cd backend && python -m alembic heads` → wpisz ją jako `down_revision` (2026-09-24: `trgm001`).

```python
# backend/migrations/versions/profil001_profil_dostawcy.py
"""Profil dokumentów dostawcy (CI+PL), próbki, jednostka uzupełniająca materiału,
format eksportu agencji. Backfill: niepusty Supplier.column_map → profil draft z ci_map.

Revision ID: profil001
Revises: trgm001
"""
import sqlalchemy as sa
from alembic import op

revision = "profil001"
down_revision = "trgm001"
branch_labels = None
depends_on = None

ROLES = {"ref", "desc", "qty", "price", "net", "unit", "lot", "weight_net", "weight_gross", "cartons", "no"}


def ci_map_from_column_map(text: str) -> dict[str, list[str]]:
    """„ref=Item No.; qty=Q'ty" → {"ref": ["Item No."], "qty": ["Q'ty"]} (ta sama składnia co
    extractor.parse_column_map; nieznane role i puste aliasy pomijane)."""
    out: dict[str, list[str]] = {}
    for part in (text or "").split(";"):
        role, _, header = part.partition("=")
        role, header = role.strip().lower(), header.strip()
        if role in ROLES and header:
            out.setdefault(role, []).append(header)
    return out


def upgrade() -> None:
    op.create_table(
        "supplier_doc_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("supplier_id", sa.Integer, sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(3), nullable=False, server_default=""),
        sa.Column("doc_language", sa.String(10), nullable=False, server_default=""),
        sa.Column("keywords", sa.JSON, nullable=False),
        sa.Column("ci_map", sa.JSON, nullable=False),
        sa.Column("pl_map", sa.JSON, nullable=False),
        sa.Column("ref_kind", sa.String(10), nullable=False, server_default="ours"),
        sa.Column("split_marker", sa.String(60), nullable=False, server_default=""),
        sa.Column("tol_amount_pct", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("tol_qty_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "supplier_doc_samples",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("profile_id", sa.Integer,
                  sa.ForeignKey("supplier_doc_profiles.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("last_test", sa.JSON, nullable=False),
        sa.Column("last_test_at", sa.DateTime, nullable=True),
    )
    with op.batch_alter_table("materials") as b:
        b.add_column(sa.Column("suppl_unit", sa.String(20), nullable=False, server_default=""))
        b.add_column(sa.Column("suppl_factor", sa.Float, nullable=True))
    with op.batch_alter_table("customs_agencies") as b:
        b.add_column(sa.Column("export_format", sa.String(20), nullable=False, server_default="standard"))
        b.add_column(sa.Column("export_params", sa.JSON, nullable=True))

    conn = op.get_bind()
    profiles = sa.table("supplier_doc_profiles", sa.column("supplier_id"), sa.column("keywords"),
                        sa.column("ci_map"), sa.column("pl_map"), sa.column("status"))
    rows = conn.execute(sa.text("SELECT id, column_map FROM suppliers WHERE column_map <> ''")).all()
    batch = [{"supplier_id": sid, "keywords": [], "ci_map": ci_map_from_column_map(cm), "pl_map": {},
              "status": "draft"} for sid, cm in rows if ci_map_from_column_map(cm)]
    if batch:
        op.bulk_insert(profiles, batch)


def downgrade() -> None:
    with op.batch_alter_table("customs_agencies") as b:
        b.drop_column("export_params")
        b.drop_column("export_format")
    with op.batch_alter_table("materials") as b:
        b.drop_column("suppl_factor")
        b.drop_column("suppl_unit")
    op.drop_table("supplier_doc_samples")
    op.drop_table("supplier_doc_profiles")
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_supplier_profiles.py tests/test_migration_chain.py -q`
Expected: PASS (w tym strażnik jednej głowy alembica).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models backend/migrations/versions/profil001_profil_dostawcy.py backend/tests/test_supplier_profiles.py
git commit -m "feat(dostawcy): model profilu dokumentów (CI+PL) i próbek + pola materiału/agencji, backfill column_map"
```

---

### Task 2: API profilu dostawcy

**Files:**
- Create: `backend/app/routers/supplier_profiles.py`
- Create: `backend/app/schemas/supplier_profiles.py`
- Modify: `backend/app/main.py` (import routera + `app.include_router(supplier_profiles.router)`)
- Test: `backend/tests/test_supplier_profiles.py` (dopisz)

**Interfaces:**
- Consumes: modele z Task 1; `get_scoped(db, Model, id, user)` i `Editors`/`Viewer` z `app/deps.py`; `COLUMN_ROLES` z `app/invoices/extractor.py`.
- Produces: `GET /api/suppliers/{supplier_id}/doc-profile` → `SupplierDocProfileOut` (pusty profil `draft` z wartościami domyślnymi, gdy nie istnieje; `samples` = lista `{id, filename, created_at, last_test, last_test_at}`); `PUT /api/suppliers/{supplier_id}/doc-profile` (Editors) body `SupplierDocProfileIn` → `SupplierDocProfileOut` (upsert, audyt `record`).

- [ ] **Step 1: Write the failing test** (dopisz do `tests/test_supplier_profiles.py`)

```python
def test_profile_api_upsert_and_validation(client, admin_headers):
    company = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    sid = client.post("/api/suppliers", headers=admin_headers,
                      json={"name": "Northbridge", "company_id": company}).json()["id"]
    url = f"/api/suppliers/{sid}/doc-profile"
    empty = client.get(url, headers=admin_headers).json()
    assert (empty["status"], empty["ci_map"], empty["samples"]) == ("draft", {}, [])
    body = {"currency": "USD", "doc_language": "en", "keywords": ["NORTHBRIDGE", " Northbridge "],
            "ci_map": {"ref": ["Item No."], "qty": ["Qty", "Quantity"]}, "pl_map": {"weight_net": ["N.W."]},
            "ref_kind": "supplier", "split_marker": "PACKING LIST", "tol_amount_pct": 0.5,
            "tol_qty_pct": 0, "status": "active"}
    r = client.put(url, headers=admin_headers, json=body)
    assert r.status_code == 200, r.text
    got = client.get(url, headers=admin_headers).json()
    assert got["keywords"] == ["NORTHBRIDGE", "Northbridge"]          # trim + bez pustych
    assert got["ref_kind"] == "supplier" and got["pl_map"] == {"weight_net": ["N.W."]}
    bad = client.put(url, headers=admin_headers, json={**body, "ci_map": {"cena": ["Price"]}})
    assert bad.status_code == 422                               # nieznana rola kolumny
    assert client.put(url, headers=admin_headers, json={**body, "tol_qty_pct": -1}).status_code == 422
    assert client.get("/api/suppliers/999999/doc-profile", headers=admin_headers).status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_supplier_profiles.py::test_profile_api_upsert_and_validation -q`
Expected: FAIL — 404/405 (brak endpointu).

- [ ] **Step 3: Implement schemas**

```python
# backend/app/schemas/supplier_profiles.py
import datetime

from pydantic import BaseModel, Field, field_validator

from ..invoices.extractor import COLUMN_ROLES


def _check_map(v: dict[str, list[str]]) -> dict[str, list[str]]:
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
    supplier_id: int
    samples: list[SampleOut] = []
```

- [ ] **Step 4: Implement router**

```python
# backend/app/routers/supplier_profiles.py
"""Profil dokumentów dostawcy (CI + packing list) — odczyt i zapis (etap 1 spec
2026-09-24-profil-dostawcy). Scoping dostawcy jak słownik (get_scoped)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..audit import record
from ..database import get_db
from ..deps import Editors as editors
from ..deps import Viewer as viewer
from ..deps import get_scoped
from ..models import Supplier, SupplierDocProfile, User
from ..schemas.supplier_profiles import SupplierDocProfileIn, SupplierDocProfileOut

router = APIRouter(prefix="/api", tags=["profil dostawcy"])


@router.get("/suppliers/{supplier_id}/doc-profile", response_model=SupplierDocProfileOut)
def get_profile(supplier_id: int, db: Session = Depends(get_db), user: User = viewer):
    supplier = get_scoped(db, Supplier, supplier_id, user)
    if supplier.doc_profile:
        return supplier.doc_profile
    return SupplierDocProfileOut(supplier_id=supplier.id)


@router.put("/suppliers/{supplier_id}/doc-profile", response_model=SupplierDocProfileOut)
def put_profile(supplier_id: int, body: SupplierDocProfileIn, db: Session = Depends(get_db),
                user: User = editors):
    supplier = get_scoped(db, Supplier, supplier_id, user)
    profile = supplier.doc_profile or SupplierDocProfile(supplier_id=supplier.id)
    old_status = profile.status if profile.id else None
    for field, value in body.model_dump().items():
        setattr(profile, field, value)
    db.add(profile)
    record(db, entity_type="suppliers", entity_id=supplier.id, field="doc_profile",
           old_value=old_status, new_value=profile.status, user=user)
    db.commit()
    db.refresh(profile)
    return profile
```

W `backend/app/main.py`: dopisz `supplier_profiles,` do listy `from .routers import (...)` (alfabetycznie, po `supplier_maps,`) i `app.include_router(supplier_profiles.router)` po `app.include_router(supplier_maps.router)`.

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_supplier_profiles.py -q`
Expected: PASS (3 testy).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/supplier_profiles.py backend/app/schemas/supplier_profiles.py backend/app/main.py backend/tests/test_supplier_profiles.py
git commit -m "feat(dostawcy): API profilu dokumentów dostawcy (GET/PUT, walidacja ról kolumn)"
```

---

### Task 3: Pola materiału i agencji w API

**Files:**
- Modify: `backend/app/schemas/materials_customs.py` (`MaterialOut`, `MaterialIn`)
- Modify: `backend/app/schemas/dictionaries.py` (`CustomsAgencyOut`, `CustomsAgencyIn`)
- Test: `backend/tests/test_supplier_profiles.py` (dopisz)

**Interfaces:**
- Produces: `MaterialOut.suppl_unit: str`, `MaterialOut.suppl_factor: float | None`; `MaterialIn.suppl_unit/suppl_factor` (opcjonalne, PATCH); `CustomsAgencyOut/In.export_format: Literal["standard","symbols"]`, `export_params: dict`.

- [ ] **Step 1: Write the failing test**

```python
def test_agency_export_format_and_material_suppl_unit(client, admin_headers):
    r = client.post("/api/customs-agencies", headers=admin_headers,
                    json={"name": "Delta Brokers", "export_format": "symbols", "export_params": {"IDZestawu": 106}})
    assert r.status_code == 201, r.text
    assert (r.json()["export_format"], r.json()["export_params"]) == ("symbols", {"IDZestawu": 106})
    assert client.post("/api/customs-agencies", headers=admin_headers,
                       json={"name": "X", "export_format": "pdf"}).status_code == 422
    with SessionLocal() as db:
        db.add(Material(ref_code="GLOVE-1"))
        db.commit()
        mid = db.query(Material).filter_by(ref_code="GLOVE-1").one().id
    r = client.patch(f"/api/materials/{mid}", headers=admin_headers,
                     json={"suppl_unit": "pary", "suppl_factor": 0.5})
    assert r.status_code == 200, r.text
    assert (r.json()["suppl_unit"], r.json()["suppl_factor"]) == ("pary", 0.5)
```

Przed napisaniem: potwierdź ścieżkę PATCH materiału (`grep -n "@router.patch" backend/app/routers/materials.py`) i dopasuj URL w teście.

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_supplier_profiles.py::test_agency_export_format_and_material_suppl_unit -q`
Expected: FAIL (brak pól w odpowiedzi / 422 nie zwracany).

- [ ] **Step 3: Implement**

`backend/app/schemas/dictionaries.py` — `from typing import Literal` na górze; w `CustomsAgencyOut` dopisz:

```python
    export_format: str = "standard"
    export_params: dict | None = None
```

w `CustomsAgencyIn` dopisz:

```python
    export_format: Literal["standard", "symbols"] = "standard"
    export_params: dict = {}
```

`backend/app/schemas/materials_customs.py` — w `MaterialOut`:

```python
    suppl_unit: str = ""
    suppl_factor: float | None = None
```

w `MaterialIn`:

```python
    suppl_unit: str | None = Field(default=None, max_length=20)
    suppl_factor: float | None = Field(default=None, gt=0)
```

(Router agencji zapisuje `body.model_dump()` przez `record_changes`, router materiału zapisuje pola podane w PATCH — sprawdź, że `MaterialIn` jest aplikowany przez `model_dump(exclude_unset=True)`; jeśli router ma listę pól wprost, dopisz `suppl_unit`, `suppl_factor`.)

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_supplier_profiles.py tests/test_materials*.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite, length guard, commit, PR**

```bash
cd backend && python -m pytest -q -p no:cacheprovider      # oczekiwane: wszystkie zielone
cd .. && python scripts/check_file_lengths.py
git add backend/app/schemas backend/tests/test_supplier_profiles.py
git commit -m "feat(dostawcy): export_format agencji i jednostka uzupełniająca materiału w API"
git push -u origin claude/profil-dostawcy-1-model
gh pr create --fill
```

---

## Następne plany (osobne pliki, po scaleniu etapu 1)

- `2026-09-24-profil-dostawcy-2-ekstrakcja.md` — ekstrakcja wg `ci_map/pl_map`, podział CI/PL (`split_marker` + klasyfikator), rozpoznanie dostawcy po `keywords`, `ref_kind`.
- `…-3-kontrole.md` — jednostki (UomConversion/MARM, `suppl_unit/factor`), waga netto z PL, kontrole z `tol_amount_pct/tol_qty_pct`, widok przy dokumencie.
- `…-4-kreator.md` — karta dostawcy, kreator 4 kroki, próbki (`SupplierDocSample`) i test.
- `…-5-eksport.md` — „Kartoteka symboli" (44 kolumny) wg `export_format/export_params`, mail .eml.

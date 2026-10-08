# Analityka i Predykcja — Faza 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zastąpić ręczne `target_days × zużycie` w wywołaniach DLT prognozą dziennego popytu per produkt, opartą o baseline sezonowo-naiwny, za wymienialnym interfejsem `Predictor`.

**Architecture:** Nowy pakiet `backend/app/analytics/` (ingest historii wydań → tabela `material_issues` → `BaselinePredictor` → integracja z `pallets_analysis`). Front: strona `AnalitykaPage` (upload + wykres prognozy). Interfejs `Predictor` jest szwem, za którym Faza 2 wstawia model ML bez zmian w konsumentach.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`), Pydantic, pytest + TestClient, React + Vite (istniejące wzorce stron), openpyxl (już w zależnościach — używa go `pallets_export`).

## Global Constraints

- Python: importy względne wewnątrz `app.` (pakiet). Modele w `app/models.py`, routery w `app/routers/`.
- Modele: SQLAlchemy 2.0 `Mapped[...] = mapped_column(...)`, wzorzec jak `ProductPaz` (`app/models.py:795`).
- Nowe tabele powstają przez `Base.metadata.create_all` w `bootstrap()`; dla dev-SQLite nowe KOLUMNY istniejących tabel dokłada `ensure_new_columns()` — nowa tabela nie wymaga tam wpisu.
- Izolacja/role: router pod `Editors`/`AdminOnly` z `app/deps.py` (wzorzec jak `routers/pallets.py`). Prefix `/api/analytics`.
- Testy: pytest, fixture `client`/`admin_headers` z `tests/conftest.py`. Login admin `admin/admin123`.
- Waluta zmian: DRY, YAGNI, TDD, częste commity. Bez nowych zależności — `openpyxl` i `csv` (stdlib) wystarczą.

---

### Task 1: Model `MaterialIssue` (historia wydań)

**Files:**
- Modify: `backend/app/models.py` (dodaj klasę po `ProductPaz`, ~`:802`)
- Test: `backend/tests/test_material_issue_model.py`

**Interfaces:**
- Produces: `MaterialIssue(produkt: str, date: datetime.date, qty: float, firma: str, magazyn: str, kontrahent: str, source_file: str)`; tabela `material_issues`; unikat `(source_file, produkt, date, magazyn)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_material_issue_model.py
import datetime
from app.database import Base, engine, SessionLocal
from app.models import MaterialIssue

def test_material_issue_persists_and_dedups():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.query(MaterialIssue).delete()
        db.add(MaterialIssue(produkt="A", date=datetime.date(2026, 1, 2), qty=10,
                             firma="BOREALIS", magazyn="MAG1", kontrahent="", source_file="f1.csv"))
        db.commit()
        row = db.query(MaterialIssue).one()
        assert row.produkt == "A" and float(row.qty) == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_material_issue_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'MaterialIssue'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/models.py — po klasie ProductPaz
class MaterialIssue(Base):
    """Historia wydań materiałów (dzienna, per produkt) — podstawa prognozy popytu."""
    __tablename__ = "material_issues"
    __table_args__ = (UniqueConstraint("source_file", "produkt", "date", "magazyn",
                                       name="uq_material_issue"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    produkt: Mapped[str] = mapped_column(String(60), index=True)
    date: Mapped[datetime.date] = mapped_column(Date, index=True)
    qty: Mapped[float] = mapped_column(Numeric(14, 3))
    firma: Mapped[str] = mapped_column(String(60), default="")
    magazyn: Mapped[str] = mapped_column(String(60), default="")
    kontrahent: Mapped[str] = mapped_column(String(120), default="")
    source_file: Mapped[str] = mapped_column(String(200), default="")
```

Upewnij się, że `UniqueConstraint` i `Date` są w imporcie `sqlalchemy` na górze `models.py` (dodaj brakujące).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_material_issue_model.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_material_issue_model.py
git commit -m "feat(analityka): model MaterialIssue (historia wydań)"
```

---

### Task 2: Parser ingest (CSV/XLSX → wiersze + raport walidacji)

**Files:**
- Create: `backend/app/analytics/__init__.py` (pusty)
- Create: `backend/app/analytics/ingest.py`
- Test: `backend/tests/test_analytics_ingest.py`

**Interfaces:**
- Consumes: nic.
- Produces:
  - `parse_issues(data: bytes, filename: str) -> IngestReport`
  - `IngestReport(rows: list[dict], errors: list[str], unknown_products: list[str], duplicates: int)` — `rows` mają klucze `produkt, date(datetime.date), qty(float), firma, magazyn, kontrahent`.
  - Oczekiwane kolumny (po normalizacji nagłówka: lower + bez ogonków): `data, produkt, ilosc` (wymagane) oraz `firma, magazyn, kontrahent` (opcjonalne).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_analytics_ingest.py
import datetime
from app.analytics.ingest import parse_issues

CSV = b"data;produkt;ilosc;magazyn\n2026-01-02;A;10;MAG1\n2026-01-03;A;5;MAG1\n"

def test_parse_ok():
    rep = parse_issues(CSV, "f1.csv")
    assert rep.errors == []
    assert len(rep.rows) == 2
    assert rep.rows[0] == {"produkt": "A", "date": datetime.date(2026, 1, 2),
                           "qty": 10.0, "firma": "", "magazyn": "MAG1", "kontrahent": ""}

def test_parse_bad_header():
    rep = parse_issues(b"foo;bar\n1;2\n", "x.csv")
    assert any("brak kolumny" in e.lower() for e in rep.errors)
    assert rep.rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_analytics_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: app.analytics.ingest`

- [ ] **Step 3: Write minimal implementation**

```python
# app/analytics/ingest.py
from __future__ import annotations
import csv, datetime, io, unicodedata
from dataclasses import dataclass, field

REQUIRED = ("data", "produkt", "ilosc")

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return s.strip().lower()

@dataclass
class IngestReport:
    rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    unknown_products: list[str] = field(default_factory=list)
    duplicates: int = 0

def _read_table(data: bytes, filename: str) -> tuple[list[str], list[list[str]]]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        rows = [[("" if c is None else str(c)) for c in r]
                for r in ws.iter_rows(values_only=True)]
        wb.close()
    else:
        text = data.decode("utf-8-sig", errors="replace")
        delim = ";" if text[:2048].count(";") >= text[:2048].count(",") else ","
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return [], []
    return rows[0], rows[1:]

def parse_issues(data: bytes, filename: str) -> IngestReport:
    rep = IngestReport()
    header, body = _read_table(data, filename)
    cols = {_norm(h): i for i, h in enumerate(header)}
    missing = [c for c in REQUIRED if c not in cols]
    if missing:
        rep.errors.append(f"Brak kolumny: {', '.join(missing)}")
        return rep
    seen: set[tuple] = set()
    for n, raw in enumerate(body, start=2):
        def cell(name: str) -> str:
            i = cols.get(name)
            return raw[i].strip() if i is not None and i < len(raw) else ""
        if not any(raw):
            continue
        try:
            d = datetime.date.fromisoformat(cell("data")[:10])
            qty = float(cell("ilosc").replace(",", ".") or 0)
        except ValueError:
            rep.errors.append(f"Wiersz {n}: zła data/ilość")
            continue
        produkt = cell("produkt")
        if not produkt:
            rep.errors.append(f"Wiersz {n}: brak produktu")
            continue
        magazyn = cell("magazyn")
        key = (produkt, d, magazyn)
        if key in seen:
            rep.duplicates += 1
            continue
        seen.add(key)
        rep.rows.append({"produkt": produkt, "date": d, "qty": qty,
                         "firma": cell("firma"), "magazyn": magazyn,
                         "kontrahent": cell("kontrahent")})
    return rep
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_analytics_ingest.py -v`
Expected: PASS (oba testy)

- [ ] **Step 5: Commit**

```bash
git add backend/app/analytics/__init__.py backend/app/analytics/ingest.py backend/tests/test_analytics_ingest.py
git commit -m "feat(analityka): parser ingest CSV/XLSX + raport walidacji"
```

---

### Task 3: `Predictor` + `BaselinePredictor` (prognoza + przedział)

**Files:**
- Create: `backend/app/analytics/predictor.py`
- Test: `backend/tests/test_analytics_predictor.py`

**Interfaces:**
- Consumes: nic (dostaje gotową serię).
- Produces:
  - `@dataclass DayForecast(date: datetime.date, mean: float, lo: float, hi: float)`
  - `class Predictor(Protocol): def forecast(self, series: dict[datetime.date, float], horizon_days: int, start: datetime.date) -> list[DayForecast]`
  - `class BaselinePredictor` z polami `level_window=28, profile_window=84, z=1.0`.
  - `MIN_HISTORY_DAYS = 14` — poniżej tego `forecast` zwraca `[]` (sygnał „za mało historii").

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_analytics_predictor.py
import datetime
from app.analytics.predictor import BaselinePredictor, MIN_HISTORY_DAYS

def _weekly_series(start, days, weekday_qty):
    return {start + datetime.timedelta(days=i): weekday_qty[(start.weekday() + i) % 7]
            for i in range(days)}

def test_forecast_follows_weekday_profile():
    start = datetime.date(2025, 1, 6)  # poniedziałek
    qty = [10, 10, 10, 10, 10, 2, 0]   # pn..nd
    series = _weekly_series(start, 120, qty)
    pred = BaselinePredictor()
    fc = pred.forecast(series, horizon_days=7, start=datetime.date(2025, 5, 6))
    assert len(fc) == 7
    by_wd = {f.date.weekday(): f.mean for f in fc}
    assert by_wd[5] < by_wd[0]          # sobota niżej niż poniedziałek
    assert all(f.lo <= f.mean <= f.hi for f in fc)
    assert all(f.lo >= 0 for f in fc)

def test_too_little_history_returns_empty():
    start = datetime.date(2025, 1, 6)
    series = {start + datetime.timedelta(days=i): 5 for i in range(MIN_HISTORY_DAYS - 1)}
    assert BaselinePredictor().forecast(series, 7, datetime.date(2025, 2, 1)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_analytics_predictor.py -v`
Expected: FAIL — `ModuleNotFoundError: app.analytics.predictor`

- [ ] **Step 3: Write minimal implementation**

```python
# app/analytics/predictor.py
from __future__ import annotations
import datetime, statistics
from dataclasses import dataclass
from typing import Protocol

MIN_HISTORY_DAYS = 14

@dataclass
class DayForecast:
    date: datetime.date
    mean: float
    lo: float
    hi: float

class Predictor(Protocol):
    def forecast(self, series: dict[datetime.date, float],
                 horizon_days: int, start: datetime.date) -> list[DayForecast]: ...

def _dense(series: dict[datetime.date, float]) -> list[tuple[datetime.date, float]]:
    """Wypełnia brakujące dni zerami między min a max datą (wydanie = 0 w dniu bez ruchu)."""
    if not series:
        return []
    lo, hi = min(series), max(series)
    out, d = [], lo
    while d <= hi:
        out.append((d, float(series.get(d, 0.0))))
        d += datetime.timedelta(days=1)
    return out

class BaselinePredictor:
    def __init__(self, level_window: int = 28, profile_window: int = 84, z: float = 1.0):
        self.level_window, self.profile_window, self.z = level_window, profile_window, z

    def forecast(self, series, horizon_days, start):
        dense = _dense(series)
        if len(dense) < MIN_HISTORY_DAYS:
            return []
        vals = [v for _, v in dense]
        level = statistics.fmean(vals[-self.level_window:])
        window = dense[-self.profile_window:]
        overall = statistics.fmean([v for _, v in window]) or 1e-9
        by_wd: dict[int, list[float]] = {}
        for d, v in window:
            by_wd.setdefault(d.weekday(), []).append(v)
        factor = {wd: (statistics.fmean(vs) / overall) for wd, vs in by_wd.items()}
        # reszta historyczna (actual - fitted) → przedział
        resid = [v - level * factor.get(d.weekday(), 1.0) for d, v in window]
        sd = statistics.pstdev(resid) if len(resid) > 1 else 0.0
        out = []
        for i in range(horizon_days):
            day = start + datetime.timedelta(days=i)
            mean = max(0.0, level * factor.get(day.weekday(), 1.0))
            out.append(DayForecast(day, mean, max(0.0, mean - self.z * sd), mean + self.z * sd))
        return out

def demo() -> None:
    start = datetime.date(2025, 1, 6)
    series = {start + datetime.timedelta(days=i): (0 if (start.weekday()+i) % 7 >= 5 else 10)
              for i in range(120)}
    fc = BaselinePredictor().forecast(series, 7, datetime.date(2025, 5, 6))
    assert len(fc) == 7 and all(f.lo <= f.mean <= f.hi for f in fc)
    print("baseline demo OK")

if __name__ == "__main__":
    demo()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_analytics_predictor.py -v && python -m app.analytics.predictor`
Expected: PASS + wydruk `baseline demo OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/analytics/predictor.py backend/tests/test_analytics_predictor.py
git commit -m "feat(analityka): BaselinePredictor (sezonowo-naiwny + przedział)"
```

---

### Task 4: Router `/api/analytics` (upload z podglądem + prognoza)

**Files:**
- Create: `backend/app/routers/analytics.py`
- Modify: `backend/app/main.py` (import + `app.include_router(analytics.router)` przy pozostałych, ~`:250`)
- Modify: `backend/app/analytics/store.py` (Create) — zapis wierszy do `MaterialIssue`, odczyt serii
- Test: `backend/tests/test_analytics_api.py`

**Interfaces:**
- Consumes: `parse_issues` (Task 2), `BaselinePredictor` (Task 3), `MaterialIssue` (Task 1).
- Produces (store.py):
  - `save_rows(db, rows: list[dict], source_file: str) -> int` (liczba zapisanych, dedup po unikacie)
  - `load_series(db, produkt: str) -> dict[datetime.date, float]` (suma qty per dzień)
  - `list_products(db) -> list[str]`
- Produces (endpointy):
  - `POST /api/analytics/upload?commit=false` (multipart plik) → raport `{rows_count, errors, duplicates, unknown_products, saved}`. `commit=false` = tylko podgląd; `commit=true` = zapis.
  - `GET /api/analytics/forecast?produkt=..&horizon=14` → `{produkt, horizon, days:[{date, mean, lo, hi}]}`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_analytics_api.py
import io

CSV = ("data;produkt;ilosc;magazyn\n"
       + "".join(f"2025-{m:02d}-{d:02d};A;{10 if (d%7)<5 else 0};MAG1\n"
                for m in range(1, 6) for d in range(1, 28))).encode()

def _upload(client, headers, commit):
    return client.post(f"/api/analytics/upload?commit={commit}", headers=headers,
                       files={"file": ("h.csv", io.BytesIO(CSV), "text/csv")})

def test_preview_then_commit_then_forecast(client, admin_headers):
    prev = _upload(client, admin_headers, "false").json()
    assert prev["errors"] == [] and prev["rows_count"] > 100 and prev["saved"] == 0
    saved = _upload(client, admin_headers, "true").json()
    assert saved["saved"] > 100
    fc = client.get("/api/analytics/forecast?produkt=A&horizon=14", headers=admin_headers).json()
    assert len(fc["days"]) == 14
    assert all(d["lo"] <= d["mean"] <= d["hi"] for d in fc["days"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_analytics_api.py -v`
Expected: FAIL — 404 (router nie zarejestrowany)

- [ ] **Step 3: Write minimal implementation**

```python
# app/analytics/store.py
from __future__ import annotations
import datetime
from sqlalchemy import select, func
from .ingest import IngestReport
from ..models import MaterialIssue

def save_rows(db, rows: list[dict], source_file: str) -> int:
    existing = {(r.produkt, r.date, r.magazyn) for r in db.query(
        MaterialIssue).filter(MaterialIssue.source_file == source_file).all()}
    n = 0
    for r in rows:
        key = (r["produkt"], r["date"], r["magazyn"])
        if key in existing:
            continue
        db.add(MaterialIssue(source_file=source_file, **r))
        existing.add(key); n += 1
    db.commit()
    return n

def load_series(db, produkt: str) -> dict[datetime.date, float]:
    stmt = (select(MaterialIssue.date, func.sum(MaterialIssue.qty))
            .where(MaterialIssue.produkt == produkt).group_by(MaterialIssue.date))
    return {d: float(q or 0) for d, q in db.execute(stmt)}

def list_products(db) -> list[str]:
    return [p for (p,) in db.execute(
        select(MaterialIssue.produkt).distinct().order_by(MaterialIssue.produkt))]
```

```python
# app/routers/analytics.py
import datetime
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session
from ..analytics.ingest import parse_issues
from ..analytics.predictor import BaselinePredictor
from ..analytics.store import save_rows, load_series
from ..database import get_db
from ..deps import Editors as editors
from ..models import User, ProductPaz

router = APIRouter(prefix="/api/analytics", tags=["analityka"])

@router.post("/upload")
async def upload(commit: bool = Query(False), file: UploadFile = File(...),
                 user: User = editors, db: Session = Depends(get_db)):
    data = await file.read()
    rep = parse_issues(data, file.filename or "upload.csv")
    known = {p.produkt for p in db.query(ProductPaz).all()}
    unknown = sorted({r["produkt"] for r in rep.rows} - known) if known else []
    saved = 0
    if commit and not rep.errors:
        saved = save_rows(db, rep.rows, file.filename or "upload.csv")
    return {"rows_count": len(rep.rows), "errors": rep.errors,
            "duplicates": rep.duplicates, "unknown_products": unknown, "saved": saved}

@router.get("/forecast")
def forecast(produkt: str, horizon: int = Query(14, ge=1, le=90),
             user: User = editors, db: Session = Depends(get_db)):
    series = load_series(db, produkt)
    start = (max(series) + datetime.timedelta(days=1)) if series else datetime.date.today()
    days = BaselinePredictor().forecast(series, horizon, start)
    return {"produkt": produkt, "horizon": horizon,
            "days": [{"date": d.date.isoformat(), "mean": d.mean, "lo": d.lo, "hi": d.hi}
                     for d in days]}
```

W `app/main.py`: dodaj `analytics` do importu z `.routers` oraz `app.include_router(analytics.router)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_analytics_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/analytics.py backend/app/analytics/store.py backend/app/main.py backend/tests/test_analytics_api.py
git commit -m "feat(analityka): router upload(podgląd/commit) + forecast"
```

---

### Task 5: Integracja prognozy z wywołaniami DLT

**Files:**
- Modify: `backend/app/pallets_analysis.py` (`build_rows` — nowy opcjonalny arg `demand_forecast`)
- Modify: `backend/app/pallets_cache.py` (`get_analysis` — policz `demand_forecast` z historii przez `BaselinePredictor`, przekaż horyzont)
- Test: `backend/tests/test_pallets_forecast_integration.py`

**Interfaces:**
- Consumes: `load_series`, `list_products` (Task 4), `BaselinePredictor` (Task 3).
- Produces:
  - `build_rows(..., demand_forecast: dict[str, float] | None = None, horizon_days: int = 14)` — gdy `demand_forecast[p]` istnieje, zapotrzebowanie z prognozy (sztuki na horyzont), a `zuzycie` dzienne = `demand_forecast[p] / horizon_days`; brak wpisu → dotychczasowa reguła `zużycie × target_days` (kompatybilność wstecz).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_pallets_forecast_integration.py
from app.pallets_analysis import build_rows

def test_forecast_drives_need_when_present():
    stock = [{"produkt": "A", "ilosc": 100, "lok": "MAG"}]
    paz = {"A": 10.0}          # 10 szt/paleta
    rows, _ = build_rows(
        stock, [], [], [], paz, {}, key="produkt", location_field="lok",
        dlt_values={"DLT"}, open_statuses=set(), target_days=7, urgent_threshold=2,
        demand_forecast={"A": 140.0}, horizon_days=14)   # 140 szt = 14 palet na 14 dni
    r = next(x for x in rows if x["produkt"] == "A")
    # need = 14 palet forecast; stan_mag = 10 palet → sugestia dąży do 4 (cap floor(DLT)=0 → 0),
    # ale dni_zapasu liczone z prognozy (10 palet / (1 pal/dzień) = 10 dni)
    assert round(r["dni_zapasu"], 1) == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_pallets_forecast_integration.py -v`
Expected: FAIL — `build_rows() got an unexpected keyword argument 'demand_forecast'`

- [ ] **Step 3: Write minimal implementation**

W `pallets_analysis.build_rows` dodaj parametry i podmień źródło zapotrzebowania dla produktów z prognozą:

```python
def build_rows(stock, vbba, orders, usage, paz_map, called_map, *,
               key, location_field, dlt_values, open_statuses,
               target_days, urgent_threshold,
               orders_confirmed_field="potw", orders_unconfirmed_field="niestandardowe",
               demand_forecast=None, horizon_days=14):
    ...
    for p in sorted(produkty):
        paz = paz_map.get(p)
        ...
        if demand_forecast and p in demand_forecast:
            fc_pal = to_pallets(demand_forecast[p], paz)        # palety na horyzont
            zuzycie_pal = None if fc_pal is None else fc_pal / horizon_days
        else:
            zuzycie_pal = to_pallets(usage_daily.get(p, 0), paz)
        ...
        if paz is None:
            sugestia = None; disc.append({"produkt": p, "powod": "brak_paz"})
        else:
            base = (fc_pal if (demand_forecast and p in demand_forecast)
                    else (zuzycie_pal or 0) * target_days)
            need = base + dost_pal + zn_pal
            raw = math.ceil(need - (mag_pal or 0) - wywolane)
            sugestia = max(0, min(raw, math.floor(dlt_pal or 0)))
```

W `pallets_cache.get_analysis` policz prognozę i przekaż:

```python
from .analytics.predictor import BaselinePredictor
from .analytics.store import load_series, list_products

def _demand_forecast(db, horizon_days: int) -> dict[str, float]:
    pred = BaselinePredictor()
    import datetime
    out = {}
    for produkt in list_products(db):
        series = load_series(db, produkt)
        if not series:
            continue
        start = max(series) + datetime.timedelta(days=1)
        days = pred.forecast(series, horizon_days, start)
        if days:
            out[produkt] = sum(d.mean for d in days)     # sztuki na horyzont
    return out
```

Wywołaj `_demand_forecast(db, settings.pallet_forecast_horizon_days)` i przekaż jako `demand_forecast=...`, `horizon_days=...` do `build_rows`. Dodaj `pallet_forecast_horizon_days: int = 14` w `config.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_pallets_forecast_integration.py tests/test_pallets_analysis.py -v`
Expected: PASS (nowy + brak regresji w istniejących)

- [ ] **Step 5: Commit**

```bash
git add backend/app/pallets_analysis.py backend/app/pallets_cache.py backend/app/config.py backend/tests/test_pallets_forecast_integration.py
git commit -m "feat(analityka): prognoza napędza zapotrzebowanie w wywołaniach DLT"
```

---

### Task 6: Frontend — strona `AnalitykaPage` (upload + wykres prognozy)

**Files:**
- Create: `frontend/src/pages/AnalitykaPage.tsx`
- Modify: `frontend/src/App.tsx` (lazy import + `<Route path="/analityka">` + `<NavLink>` w `Sidebar` z `NavIcon n="dashboard"` lub nowym kluczem)
- Modify: `frontend/src/App.tsx` `NAV_ICONS` — dodaj klucz `analytics` (ścieżka SVG wykresu), użyj w NavLink
- Test: `frontend/src/analytika.dom.test.tsx`

**Interfaces:**
- Consumes: `api.get`/`api.post` (`src/api.ts`), endpointy z Task 4.
- Produces: trasa `/analityka` (rola admin/logistics), UI: (1) input pliku → `POST /api/analytics/upload?commit=false` → pokaż raport → „Zapisz" (`commit=true`); (2) wybór produktu + suwak horyzontu → `GET /forecast` → wykres (SVG własny, jak istniejące — bez nowych zależności) z pasmem `lo..hi`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/analitika.dom.test.tsx
import { render, screen } from '@testing-library/react'
import AnalitykaPage from './pages/AnalitykaPage'
import { describe, it, expect } from 'vitest'

describe('AnalitykaPage', () => {
  it('renderuje sekcję wgrywania', () => {
    render(<AnalitykaPage />)
    expect(screen.getByText(/wgraj/i)).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- analitika`
Expected: FAIL — brak pliku `AnalitykaPage`

- [ ] **Step 3: Write minimal implementation**

Utwórz `AnalitykaPage.tsx` wg wzorca innych stron (`pages/QuotesPage.tsx`): sekcja uploadu (input `type=file`, przycisk „Wgraj podgląd", render raportu `errors/rows_count/duplicates`, przycisk „Zapisz" gdy brak błędów), sekcja prognozy (select produktu z `GET /api/analytics/forecast`, suwak `horizon`, prosty SVG: linia `mean`, wypełnienie między `lo` i `hi`). Użyj istniejących klas CSS (`.page`, `.btn`, `.panel`). Etykieta zawiera słowo „Wgraj".
Podłącz trasę i NavLink w `App.tsx` (lazy, jak pozostałe ciężkie strony; rola `admin`/`logistics`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- analitika && npm run build`
Expected: PASS + build OK (nowy chunk `AnalitykaPage`)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AnalitykaPage.tsx frontend/src/App.tsx frontend/src/analitika.dom.test.tsx
git commit -m "feat(analityka): strona Analityka i Predykcja (upload + wykres prognozy)"
```

---

## Self-Review

**Spec coverage:**
- Ingest ręczny (CSV/XLSX, podgląd przed zapisem) → Task 2 + 4. ✓
- Magazyn historii (`material_issues`, wymiary, dedup) → Task 1 + store (Task 4). ✓
- `Predictor` interfejs + baseline z przedziałem → Task 3. ✓
- Integracja z wywołaniami (prognoza zamiast `target_days`) → Task 5. ✓
- UI moduł + suwak horyzontu + pasmo niepewności → Task 6. ✓
- Przypadki brzegowe: złe kolumny → raport bez zapisu (Task 2/4); za mało historii → `[]`/brak sugestii (Task 3, `MIN_HISTORY_DAYS`); brak PAZ → `brak_paz` bez zmian (Task 5). ✓
- Poza Fazą 1 (ML, watcher, retrening) — świadomie pominięte, brak zadań. ✓

**Placeholder scan:** brak TODO/TBD; każdy krok ma realny kod i komendę. ✓

**Type consistency:** `parse_issues→IngestReport.rows(dict)` używane w `save_rows`; `BaselinePredictor.forecast→list[DayForecast{date,mean,lo,hi}]` używane w routerze i `_demand_forecast`; `load_series→dict[date,float]` zgodne z `forecast(series=...)`. Nazwy kolumn (`produkt,date,qty,magazyn`) spójne między modelem, ingest, store. ✓

## Uwaga o istniejącym mappingu `niestandardowe`
Parking z brainstormu (Pytanie 1) — niezależny wątek, nie dotykany w tym planie. Do domknięcia przy pierwszym realnym pliku z SAP.

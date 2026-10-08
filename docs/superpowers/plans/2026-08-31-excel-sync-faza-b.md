# Faza B — dwukierunkowa synchronizacja Excel ↔ apka — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dołożyć kierunek apka→Excel i uzgadnianie three-way (baseline) z LWW, tak by kolejka była jednym zestawem danych w dwóch edytowalnych widokach — bez pętli echa.

**Architecture:** Nowa kolumna `Container.sync_baseline` (JSON) trzyma ostatni uzgodniony stan pól. `reconcile_queue` przechodzi na three-way (baseline vs Excel vs apka) z LWW przy konflikcie (czas pola z AuditLog vs czas pliku Excela). Zapis zwrotny wyprowadzony z baseline: `GET /pending` (pola gdzie A≠B ∩ WRITABLE_FIELDS) → agent pisze komórki openpyxl → `POST /applied` podnosi baseline. Bez osobnej kolejki.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, openpyxl, requests, pytest.

## Global Constraints

- Backend w `backend/app/`, testy `backend/tests/test_sync.py` (dopisujesz); agent w `agent/`. Testy z `backend/`, uruchamiane SAM (nie równolegle — inaczej fałszywe „database is locked").
- Bazuje na Fazie A (scalonej lokalnie): `build_container_fields`, `SYNCED_FIELDS`, `_audit_val`, `reconcile_queue`, endpoint `POST /api/import/sync`, token `sync_api_token`, agent `agent/sync_agent.py`.
- Serializacja pól do porównania i baseline: `ser(v)` = enum→`.value`, date/datetime→`.isoformat()`, None→None, else `str(v)`. Baseline w DB trzyma wartości `ser(...)`.
- `SYNCED_FIELDS` (z Fazy A) = pola porównywane. `WRITABLE_FIELDS` (pierwszy cut, tylko skalarne/daty/enum z bezpośrednią kolumną): `eta, notify_date, vessel, order_numbers, delivery_note, purchase_note, document_flow, incoming_delivery_no, rf_number, sent_required, sent_number, sent_status, customs_status`. Relacyjne (supplier/forwarder/warehouse/customs_agency) i wyliczane (`status`, `notes`) — NIE zapisywane do Excela (Excel→apka).
- LWW: apka wygrywa pole gdy `app_field_time > file_mtime`; inaczej Excel. `app_field_time` = najnowszy `AuditLog.created_at` dla `(entity_type="containers", entity_id, field)`, fallback `Container.updated_at`. `file_mtime` przysłany przez agenta.
- Alembic head (down_revision nowej migracji): `e5f6a7b8c9d0` (zweryfikuj `python -m alembic heads`).
- Echo: baseline podnoszony po uzgodnieniu (Excel-win/agree od razu; app-win dopiero po `/applied`).

---

### Task 1: Kolumna `sync_baseline` + migracja + helpery serializacji

**Files:**
- Modify: `backend/app/models.py` (klasa `Container`)
- Create: `backend/migrations/versions/<rev>_container_sync_baseline.py`
- Modify: `backend/app/routers/imports.py` (helper `ser`, `container_baseline`)
- Test: `backend/tests/test_sync.py`

**Interfaces:**
- Produces: `Container.sync_baseline: Mapped[dict | None]` (JSON, nullable); `ser(v) -> str | None`; `container_baseline(container) -> dict` (aktualny stan pól po `ser`).

- [ ] **Step 1: Test helpera serializacji**

Dopisz do `backend/tests/test_sync.py`:

```python
import datetime as _dt
from app.routers.imports import ser, container_baseline, SYNCED_FIELDS
from app.models import ContainerStatus, CustomsStatus


def test_ser_normalizes_types():
    assert ser(None) is None
    assert ser(ContainerStatus.W_PORCIE) == ContainerStatus.W_PORCIE.value
    assert ser(_dt.date(2026, 9, 1)) == "2026-09-01"
    assert ser(5) == "5"
    assert ser("x") == "x"


def test_container_baseline_covers_synced_fields(client):
    from app.database import SessionLocal
    from sqlalchemy import select
    from app.models import Container
    db = SessionLocal()
    try:
        c = db.scalar(select(Container)) or None
        if c is None:
            import pytest; pytest.skip("brak kontenera w bootstrapie")
        b = container_baseline(c)
        assert set(b.keys()) == set(SYNCED_FIELDS)
    finally:
        db.close()
```

- [ ] **Step 2: Uruchom — FAIL (brak `ser`/`container_baseline`)**

Run: `cd backend && python -m pytest tests/test_sync.py::test_ser_normalizes_types -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Dodaj kolumnę do modelu**

W `backend/app/models.py`, w klasie `Container` (obok innych kolumn, przed `created_at`):

```python
    # Faza B sync: ostatni uzgodniony stan pól (ser()) — three-way merge Excel<->apka.
    sync_baseline: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
```

Upewnij się, że `JSON` jest zaimportowany z `sqlalchemy` na górze `models.py` (dodaj do istniejącego importu, jeśli brak).

- [ ] **Step 4: Dodaj helpery w imports.py**

W `backend/app/routers/imports.py` (obok `_audit_val`):

```python
def ser(v) -> str | None:
    """Serializacja pola do porównania i baseline: enum->value, date->iso, else str."""
    if v is None:
        return None
    if hasattr(v, "value"):
        return v.value
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    return str(v)


def container_baseline(container) -> dict:
    """Aktualny stan pól SYNCED_FIELDS kontenera po ser() — kandydat na nowy baseline."""
    return {f: ser(getattr(container, f)) for f in SYNCED_FIELDS}
```

- [ ] **Step 5: Migracja alembic**

Zweryfikuj head: `cd backend && python -m alembic heads` (oczekiwane `e5f6a7b8c9d0`). Utwórz `backend/migrations/versions/a1b2c3d4e5f6_container_sync_baseline.py`:

```python
"""container sync_baseline

Revision ID: a1b2c3d4e5f6
Revises: e5f6a7b8c9d0
"""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("containers", sa.Column("sync_baseline", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("containers", "sync_baseline")
```

(Jeśli `alembic heads` zwróci inny head niż `e5f6a7b8c9d0`, użyj tego rzeczywistego jako `down_revision`.)

- [ ] **Step 6: Uruchom testy + migrację**

Run: `cd backend && python -m alembic upgrade head && python -m pytest tests/test_sync.py -v`
Expected: migracja OK; testy PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/routers/imports.py backend/migrations/versions/a1b2c3d4e5f6_container_sync_baseline.py backend/tests/test_sync.py
git commit -m "feat(sync-b): kolumna sync_baseline + helpery ser/container_baseline + migracja"
```

---

### Task 2: three-way reconcile + LWW

Zamienia dotychczasowy `_process_row` (Faza A: Excel nadpisuje) na three-way na `sync_baseline`. Bootstrap gdy baseline None. Konflikt → LWW.

**Files:**
- Modify: `backend/app/routers/imports.py`
- Modify: `backend/app/routers/imports.py` endpoint `sync_queue` (przyjmij `file_mtime`)
- Test: `backend/tests/test_sync.py`

**Interfaces:**
- Consumes: `ser`, `container_baseline`, `build_container_fields`, `SYNCED_FIELDS`.
- Produces: `app_field_time(db, container_id, field) -> datetime` (czas ostatniej zmiany pola w apce); `reconcile_queue(db, company, parsed, actor, file_mtime=None)` — zachowuje sygnaturę + nowy kwarg; three-way.

- [ ] **Step 1: Testy three-way (4 przypadki + bootstrap + konflikt + echo)**

Dopisz do `backend/tests/test_sync.py` (używaj `client`, poprawnych numerów ISO6346, `SessionLocal`):

```python
import datetime as dt2
from sqlalchemy import select as _sel
from app.database import SessionLocal
from app.routers.imports import reconcile_queue, container_baseline, ser, SYNCED_FIELDS
from app.models import Container, AuditLog


def _rawB(no, vessel="MAERSK", eta_day=1):
    return {"supplier": "", "vessel": vessel, "eta": dt2.datetime(2026, 9, eta_day),
            "transport": "kolej", "container_no": no, "order_numbers": "", "delivery_note": "",
            "purchase_note": "", "warehouse": "", "incoming_delivery_no": "", "rf_number": "",
            "forwarder": "", "document_flow": "", "customs_agency": "", "customs": "",
            "notify_date": None, "sent_required": "", "sent_number": "", "sent_status": ""}


def test_bootstrap_baseline_none_excel_wins(client):
    db = SessionLocal()
    try:
        company = db.scalar(_sel(Container.company_id))  # dowolna spółka z kontenera? użyj BOREALIS
        from app.models import Company
        company = db.scalar(_sel(Company).where(Company.code == "BOREALIS"))
        no = "MSKU7026492"
        reconcile_queue(db, company, [_rawB(no, "AAA")], None); db.flush()
        c = db.scalar(_sel(Container).where(Container.container_no == no,
                                            Container.company_id == company.id))
        assert c.sync_baseline is not None            # baseline zainicjowany
        assert c.sync_baseline["vessel"] == "AAA"     # B = E po bootstrapie
    finally:
        db.rollback(); db.close()


def test_app_change_goes_to_pending_not_excel(client):
    db = SessionLocal()
    try:
        from app.models import Company
        company = db.scalar(_sel(Company).where(Company.code == "BOREALIS"))
        no = "MSKU7026492"
        reconcile_queue(db, company, [_rawB(no, "AAA")], None); db.flush()
        c = db.scalar(_sel(Container).where(Container.container_no == no,
                                            Container.company_id == company.id))
        # zmiana po stronie apki (A != B), Excel bez zmian (E == B)
        c.vessel = "APP-EDIT"; db.flush()
        res = reconcile_queue(db, company, [_rawB(no, "AAA")], None); db.flush()
        # apka wygrywa: pole zostaje APP-EDIT, baseline NIE podniesiony (czeka na /applied)
        assert c.vessel == "APP-EDIT"
        assert c.sync_baseline["vessel"] == "AAA"     # B nietknięty -> trafi do pending
    finally:
        db.rollback(); db.close()


def test_excel_change_adopted_and_baseline_advances(client):
    db = SessionLocal()
    try:
        from app.models import Company
        company = db.scalar(_sel(Company).where(Company.code == "BOREALIS"))
        no = "MSKU7026492"
        reconcile_queue(db, company, [_rawB(no, "AAA")], None); db.flush()
        c = db.scalar(_sel(Container).where(Container.container_no == no,
                                            Container.company_id == company.id))
        reconcile_queue(db, company, [_rawB(no, "BBB")], None); db.flush()  # Excel zmienił
        assert c.vessel == "BBB"                      # A <- E
        assert c.sync_baseline["vessel"] == "BBB"     # B <- E
    finally:
        db.rollback(); db.close()
```

- [ ] **Step 2: Uruchom — FAIL (stary reconcile nie ma baseline)**

Run: `cd backend && python -m pytest tests/test_sync.py::test_bootstrap_baseline_none_excel_wins -v`
Expected: FAIL (brak `sync_baseline` w logice / KeyError).

- [ ] **Step 3: Zaimplementuj three-way**

W `backend/app/routers/imports.py` dodaj helper czasu i przepisz `_process_row`:

```python
def app_field_time(db: Session, container_id: int, field: str) -> datetime.datetime:
    """Czas ostatniej zmiany pola w apce (z AuditLog); fallback minimalny gdy brak."""
    t = db.scalar(select(func.max(AuditLog.created_at)).where(
        AuditLog.entity_type == "containers", AuditLog.entity_id == container_id,
        AuditLog.field == field))
    return t or datetime.datetime.min


def _process_row(db: Session, company, raw: dict, existing: dict, actor,
                 file_mtime: datetime.datetime | None = None) -> dict | None:
    number = iso6346.normalize(_text(raw["container_no"]))
    ok, _reason = iso6346.validate(number)
    if not ok:
        logger.warning("sync: pominięto niepoprawny numer kontenera %s", number)
        return None
    fields = build_container_fields(db, company, raw)
    container = existing.get(number)
    if container is None:                                   # nowy kontener
        container = Container(company_id=company.id, container_no=number, **fields)
        year = (fields["notify_date"] or datetime.date.today()).year
        container.transport_id = next_transport_id(db, company, year)
        db.add(container); db.flush(); existing[number] = container
        container.sync_baseline = container_baseline(container)   # B = stan początkowy
        record(db, entity_type="containers", entity_id=container.id, field="status",
               old_value=None, new_value=container.status.value, user=actor,
               note="sync z Excela (nowy)")
        return {"container": container, "changes": [("__new__", None, None)]}

    baseline = container.sync_baseline
    # BOOTSTRAP: brak baseline -> Excel wygrywa (jak Faza A), potem B <- stan
    if baseline is None:
        changes = []
        for f in SYNCED_FIELDS:
            if ser(getattr(container, f)) != ser(fields[f]):
                setattr(container, f, fields[f]); changes.append((f, None, ser(fields[f])))
        container.sync_baseline = container_baseline(container)
        if changes and all(f == "status" for f, _, _ in changes):
            return None
        for f, _o, nv in changes:
            record(db, entity_type="containers", entity_id=container.id, field=f,
                   old_value=None, new_value=nv, user=actor, note="sync z Excela")
        return {"container": container, "changes": changes} if changes else None

    # THREE-WAY per pole
    new_baseline = dict(baseline)
    excel_changes = []            # pola gdzie Excel wygrał i ustawiamy A<-E (audyt/notify)
    for f in SYNCED_FIELDS:
        e = ser(fields[f]); a = ser(getattr(container, f)); b = baseline.get(f)
        if e == b and a == b:
            continue                                        # nic
        if e != b and a == b:                               # tylko Excel
            setattr(container, f, fields[f]); new_baseline[f] = e
            excel_changes.append((f, a, e)); continue
        if a != b and e == b:                               # tylko apka -> pending
            continue                                        # B[f] zostaje stare -> /pending
        if e == a:                                          # oba tak samo
            new_baseline[f] = e; continue
        # KONFLIKT: e!=b, a!=b, e!=a -> LWW
        app_wins = file_mtime is not None and \
            app_field_time(db, container.id, f) > file_mtime
        if app_wins:
            continue                                        # apka wygrywa -> pending (B stare)
        setattr(container, f, fields[f]); new_baseline[f] = e
        excel_changes.append((f, a, e))
    container.sync_baseline = new_baseline
    if not excel_changes:
        return None
    if all(f == "status" for f, _, _ in excel_changes):     # tylko czasowy status -> cicho
        return None
    if any(f == "customs_agency_id" for f, _, _ in excel_changes):
        container.customs_assigned_at = fields["customs_assigned_at"]
    for f, ov, nv in excel_changes:
        record(db, entity_type="containers", entity_id=container.id, field=f,
               old_value=ov, new_value=nv, user=actor, note="sync z Excela")
    return {"container": container, "changes": excel_changes}
```

Zaktualizuj `reconcile_queue`, by przyjął i przekazał `file_mtime`:

```python
def reconcile_queue(db: Session, company, parsed: list[dict], actor,
                    file_mtime: datetime.datetime | None = None) -> list[dict]:
    existing = {c.container_no: c for c in db.scalars(
        select(Container).where(Container.company_id == company.id))}
    results: list[dict] = []
    for raw in parsed:
        try:
            with db.begin_nested():
                row_result = _process_row(db, company, raw, existing, actor, file_mtime)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sync: pominięto %s: %s", _text(raw.get("container_no")), exc)
            continue
        if row_result:
            results.append(row_result)
    return results
```

Upewnij się, że `func` jest zaimportowany z sqlalchemy w imports.py (już jest — `from sqlalchemy import func, select`).

- [ ] **Step 4: Endpoint przyjmuje `file_mtime`**

W `sync_queue` dodaj parametr i przekaż:

```python
async def sync_queue(
    file: UploadFile,
    company_code: str = Query(...),
    file_mtime: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_sync_token),
):
    ...
    mtime = None
    if file_mtime:
        try:
            mtime = datetime.datetime.fromisoformat(file_mtime)
        except ValueError:
            mtime = None
    results = reconcile_queue(db, company, parsed, actor, file_mtime=mtime)
    ...
```

- [ ] **Step 5: Uruchom testy**

Run: `cd backend && python -m pytest tests/test_sync.py -v`
Expected: PASS (nowe + istniejące). Uwaga: istniejące testy Fazy A mogą wymagać dobicia baseline — jeśli pękną przez bootstrap, dostosuj asercje (bootstrap zachowuje „Excel wygrywa", więc powinny przejść). Jeśli któryś test Fazy A zakładał brak `sync_baseline`, zaktualizuj go.

- [ ] **Step 6: Pełny suite SAM**

Run: `cd backend && python -m pytest -q`
Expected: zielony.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/imports.py backend/tests/test_sync.py
git commit -m "feat(sync-b): three-way reconcile na baseline + LWW konfliktu + file_mtime"
```

---

### Task 3: endpointy `/pending` i `/applied` + `WRITABLE_FIELDS` + wartości do Excela

**Files:**
- Modify: `backend/app/routers/imports.py`
- Test: `backend/tests/test_sync.py`

**Interfaces:**
- Consumes: `ser`, `container.sync_baseline`, `WRITABLE_FIELDS`.
- Produces: `WRITABLE_FIELDS: tuple`; `to_excel_value(container, field) -> str`; `GET /api/import/sync/pending`; `POST /api/import/sync/applied`.

- [ ] **Step 1: Testy pending/applied + echo**

Dopisz do `backend/tests/test_sync.py`:

```python
def test_pending_lists_app_changes_then_applied_advances_baseline(client, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "sync_api_token", "test-token", raising=False)
    hdr = {"Authorization": "Bearer test-token"}
    import io as _io
    from openpyxl import Workbook

    def xlsx(rows):
        wb = Workbook(); ws = wb.active
        ws.append(["DOSTAWCA", "STATEK", "ETA", "KOLEJ", "NR KONTENERA",
                   "STATUS ODPRAWY", "DATA ROZŁADUNKU"])
        for r in rows:
            ws.append(r)
        b = _io.BytesIO(); wb.save(b); return b.getvalue()

    no = "MSKU7026492"
    client.post("/api/import/sync?company_code=BOREALIS", headers=hdr,
                files={"file": ("q.xlsx", xlsx([["", "AAA", dt2.datetime(2026, 9, 1), "kolej", no, "", ""]]))})
    # zmiana po stronie apki
    from app.database import SessionLocal
    from sqlalchemy import select as sel3
    from app.models import Container
    db = SessionLocal()
    try:
        c = db.scalar(sel3(Container).where(Container.container_no == no)); c.vessel = "APP"; db.commit()
    finally:
        db.close()
    pend = client.get("/api/import/sync/pending?company_code=BOREALIS", headers=hdr).json()
    assert no in pend and pend[no].get("vessel") == "APP"     # pending pokazuje zmianę apki
    # potwierdzenie zapisu -> baseline podniesiony
    client.post("/api/import/sync/applied?company_code=BOREALIS", headers=hdr,
                json={no: ["vessel"]})
    pend2 = client.get("/api/import/sync/pending?company_code=BOREALIS", headers=hdr).json()
    assert no not in pend2 or "vessel" not in pend2.get(no, {})  # już nie pending (echo cięte)


def test_pending_excludes_status_and_notes(client, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "sync_api_token", "test-token", raising=False)
    from app.routers.imports import WRITABLE_FIELDS
    assert "status" not in WRITABLE_FIELDS and "notes" not in WRITABLE_FIELDS
```

- [ ] **Step 2: Uruchom — FAIL (brak endpointów)**

Run: `cd backend && python -m pytest tests/test_sync.py::test_pending_excludes_status_and_notes -v`
Expected: FAIL — ImportError `WRITABLE_FIELDS`.

- [ ] **Step 3: Implementacja**

W `backend/app/routers/imports.py`. UWAGA: `WRITABLE_FIELDS` jest już zdefiniowane w Task 2 (przeniesione tam do merge) — NIE definiuj go ponownie, użyj istniejącego. Dodaj tylko `to_excel_value` i endpointy:

```python
def to_excel_value(container, field: str) -> str:
    """Wartość pola gotowa do wpisania w komórkę Excela."""
    v = getattr(container, field)
    if v is None:
        return ""
    if field == "sent_required":
        return "TAK" if v else "NIE"
    if field == "customs_status":
        return "odprawiony" if v == CustomsStatus.ODPRAWIONY else (
            "zlecona" if v == CustomsStatus.ZLECONA else "")
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat() if not isinstance(v, datetime.datetime) else v.date().isoformat()
    return str(v)


@router.get("/sync/pending")
def sync_pending(company_code: str = Query(...), db: Session = Depends(get_db),
                 _auth: None = Depends(require_sync_token)):
    """Pola gdzie A≠B ∩ WRITABLE_FIELDS — zmiany apki jeszcze niezapisane w Excelu."""
    company = db.scalar(select(Company).where(Company.code == company_code.upper()))
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nieznana spółka.")
    out: dict[str, dict] = {}
    rows = db.scalars(select(Container).where(Container.company_id == company.id,
                                              Container.sync_baseline.isnot(None)))
    for c in rows:
        b = c.sync_baseline or {}
        diff = {f: to_excel_value(c, f) for f in WRITABLE_FIELDS
                if ser(getattr(c, f)) != b.get(f)}
        if diff:
            out[c.container_no] = diff
    return out


@router.post("/sync/applied")
def sync_applied(payload: dict[str, list[str]], company_code: str = Query(...),
                 db: Session = Depends(get_db), _auth: None = Depends(require_sync_token)):
    """Potwierdza zapis w Excelu: podnosi baseline (B[field] <- ser(A[field]))."""
    company = db.scalar(select(Company).where(Company.code == company_code.upper()))
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nieznana spółka.")
    updated = 0
    for container_no, fields in payload.items():
        c = db.scalar(select(Container).where(Container.company_id == company.id,
                                              Container.container_no == container_no))
        if not c or c.sync_baseline is None:
            continue
        nb = dict(c.sync_baseline)
        for f in fields:
            if f in SYNCED_FIELDS:
                nb[f] = ser(getattr(c, f))
        c.sync_baseline = nb
        updated += 1
    db.commit()
    return {"updated": updated}
```

- [ ] **Step 4: Uruchom testy**

Run: `cd backend && python -m pytest tests/test_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Pełny suite SAM + commit**

Run: `cd backend && python -m pytest -q` → zielony.

```bash
git add backend/app/routers/imports.py backend/tests/test_sync.py
git commit -m "feat(sync-b): endpointy /sync/pending i /sync/applied + WRITABLE_FIELDS"
```

---

### Task 4: agent — zapis zwrotny do Excela + `file_mtime`

**Files:**
- Modify: `agent/sync_agent.py`
- Modify: `agent/README.md`
- Test: `agent/test_sync_agent.py`

**Interfaces:**
- Consumes: endpointy `/sync/pending`, `/sync/applied`; `POST /sync` z `file_mtime`.
- Produces: `write_back(path, pending) -> list[str]` per kontener (zwraca numery zapisane); `HEADER_FOR_FIELD: dict`; rozszerzone `push_snapshot` o `file_mtime`; `run()` robi push→pending→write→applied.

- [ ] **Step 1: Test zapisu komórki + mapowania nagłówka**

Dopisz do `agent/test_sync_agent.py`:

```python
from openpyxl import Workbook, load_workbook
from sync_agent import write_back, HEADER_FOR_FIELD


def _make_xlsx(tmp_path, rows):
    p = tmp_path / "q.xlsx"
    wb = Workbook(); ws = wb.active
    ws.append(["DOSTAWCA", "STATEK", "ETA", "KOLEJ", "NR KONTENERA", "STATUS ODPRAWY"])
    for r in rows:
        ws.append(r)
    wb.save(str(p)); return str(p)


def test_write_back_sets_cell_by_container_and_header(tmp_path):
    path = _make_xlsx(tmp_path, [["ACME", "OLD", "2026-09-01", "kolej", "MSKU7026492", ""]])
    written = write_back(path, {"MSKU7026492": {"vessel": "NEW"}})
    assert written == ["MSKU7026492"]
    ws = load_workbook(path).active
    # STATEK jest w kolumnie 2; wiersz danych to 2
    assert ws.cell(row=2, column=2).value == "NEW"


def test_header_for_field_maps_vessel_to_statek():
    assert HEADER_FOR_FIELD["vessel"] == "STATEK"
```

- [ ] **Step 2: Uruchom — FAIL**

Run: `cd agent && python -m pytest test_sync_agent.py::test_header_for_field_maps_vessel_to_statek -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implementacja w `agent/sync_agent.py`**

Dodaj mapowanie i zapis (openpyxl już dostępne w środowisku apki; agent go potrzebuje — dopisz do `agent/README.md` `pip install openpyxl`):

```python
from openpyxl import load_workbook

# pole apki -> fragment nagłówka Excela (zgodnie z HEADER_MAP w backendzie, pierwszy cut)
HEADER_FOR_FIELD = {
    "eta": "ETA", "notify_date": "DATA ROZ", "vessel": "STATEK",
    "order_numbers": "NUMER ZAM", "delivery_note": "DOSTAWA",
    "purchase_note": "MAGAZYN - ZAKUPY", "document_flow": "PRZEP",
    "incoming_delivery_no": "NUMER DOSTAWY", "rf_number": "NUMER RF",
    "sent_required": "SENT WYMAGANY", "sent_number": "NUMER SENT",
    "sent_status": "STATUS SENT", "customs_status": "STATUS ODPRAWY",
}


def _find_header_columns(ws):
    """Zwraca (wiersz_nagłówka, {fragment_nagłówka_upper: kolumna}) dla arkusza."""
    for r in range(1, min(ws.max_row, 20) + 1):
        cells = {(ws.cell(row=r, column=cc).value or ""): cc for cc in range(1, ws.max_column + 1)}
        upper = {str(k).upper(): v for k, v in cells.items() if k}
        if any("NR KONTENERA" in k for k in upper):
            return r, upper
    return None, {}


def _col_for(upper_headers: dict, fragment: str):
    for htext, col in upper_headers.items():
        if fragment.upper() in htext:
            return col
    return None


def write_back(path: str, pending: dict) -> list[str]:
    """Zapisuje wskazane pola do lokalnego .xlsx (wiersz po numerze kontenera,
    kolumna po nagłówku). Zwraca listę zapisanych numerów. Podnosi wyjątek przy blokadzie."""
    if not pending:
        return []
    wb = load_workbook(path)
    ws = wb.active
    hrow, headers = _find_header_columns(ws)
    if hrow is None:
        return []
    no_col = _col_for(headers, "NR KONTENERA")
    row_for_no = {}
    for r in range(hrow + 1, ws.max_row + 1):
        val = ws.cell(row=r, column=no_col).value
        if val:
            row_for_no[str(val).strip()] = r
    written = []
    for container_no, fields in pending.items():
        r = row_for_no.get(container_no)
        if r is None:
            continue
        touched = False
        for field, value in fields.items():
            frag = HEADER_FOR_FIELD.get(field)
            col = _col_for(headers, frag) if frag else None
            if col:
                ws.cell(row=r, column=col, value=value); touched = True
        if touched:
            written.append(container_no)
    if written:
        wb.save(path)     # PermissionError gdy plik otwarty w Excelu -> obsługa w run()
    return written
```

Rozszerz `push_snapshot` o `file_mtime` (query param):

```python
def push_snapshot(session, base_url: str, token: str, company_code: str, path: str) -> dict:
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
    with open(path, "rb") as fh:
        resp = session.post(
            f"{base_url.rstrip('/')}/api/import/sync",
            params={"company_code": company_code, "file_mtime": mtime},
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (os.path.basename(path), fh)}, timeout=60)
    resp.raise_for_status()
    return resp.json()
```

(Dodaj `import datetime` na górze pliku, jeśli brak.)

Rozszerz `run()` o cykl zapisu zwrotnego po udanym push (z obsługą blokady pliku):

```python
def _sync_back(session, base_url, token, company_code, path):
    hdr = {"Authorization": f"Bearer {token}"}
    pend = session.get(f"{base_url.rstrip('/')}/api/import/sync/pending",
                       params={"company_code": company_code}, headers=hdr, timeout=30)
    pend.raise_for_status()
    pending = pend.json()
    if not pending:
        return
    try:
        written = write_back(path, pending)
    except PermissionError:
        log.warning("Plik zablokowany (Excel otwarty?) — zapis zwrotny odłożony")
        return
    if written:
        applied = {no: list(pending[no].keys()) for no in written}
        session.post(f"{base_url.rstrip('/')}/api/import/sync/applied",
                     params={"company_code": company_code}, headers=hdr, json=applied, timeout=30)
        log.info("Zapis zwrotny: %s kontenerów", len(written))
```

W pętli `run()`, po udanym `push_snapshot(...)` i `last_mtime = new_mtime`, dołóż:

```python
                try:
                    _sync_back(session, base_url, token, company_code, path)
                except Exception as exc:  # noqa: BLE001 — zapis zwrotny nie wywala pętli
                    log.warning("Zapis zwrotny nieudany (ponowię): %s", exc)
```

Uwaga: po `write_back` plik ma nowy mtime — żeby nie wywołać własnego echa, po `_sync_back` ustaw `last_mtime = os.path.getmtime(path)` (wartości, które właśnie zapisaliśmy, są już baseline'em po `/applied`, więc kolejny snapshot i tak da 0 różnic; aktualizacja `last_mtime` unika zbędnego pełnego POST-a). Dodaj tę aktualizację w bloku sukcesu.

- [ ] **Step 4: Uruchom testy agenta**

Run: `cd agent && python -m pytest test_sync_agent.py -v`
Expected: PASS (istniejące + nowe).

- [ ] **Step 5: README — dopisz openpyxl + kierunek zwrotny**

W `agent/README.md` dodaj do „Wymagania": `pip install requests openpyxl`, i akapit, że agent zapisuje zmiany z apki z powrotem do `.xlsx` (blokada pliku = odłożenie do następnego cyklu).

- [ ] **Step 6: Commit**

```bash
git add agent/sync_agent.py agent/test_sync_agent.py agent/README.md
git commit -m "feat(agent-b): zapis zwrotny do Excela (pending->write->applied) + file_mtime"
```

---

## Self-Review

- **Spec coverage:** baseline+migracja (B1 ✓); three-way 4 przypadki + bootstrap + LWW + file_mtime (B2 ✓); `/pending`+`/applied`+WRITABLE_FIELDS+status/notes wykluczone (B3 ✓); agent zapis zwrotny + mapowanie nagłówków + blokada pliku + file_mtime (B4 ✓); echo-loop (test w B3 ✓).
- **Placeholdery:** brak — pełny kod w każdym kroku.
- **Spójność typów:** `ser` używane w baseline/porównaniu/applied spójnie; `reconcile_queue(..., file_mtime=None)` wstecznie zgodne z wołaniami Fazy A (endpoint przekazuje); `WRITABLE_FIELDS ⊆ SYNCED_FIELDS`; `HEADER_FOR_FIELD` fragmenty zgodne z `HEADER_MAP` backendu.
- **Świadome uproszczenia (ponytail):** pierwszy cut WRITABLE_FIELDS bez pól relacyjnych (round-trip nazwa↔id później); LWW plikowe (nie per komórka); blokada pliku = odłożenie, nie wymuszony zapis.
- **Ryzyko do potwierdzenia u właściciela:** czy operatorzy edytują w apce pola relacyjne (dostawca/spedytor/magazyn/agencja) — jeśli tak, trzeba dołożyć je do WRITABLE_FIELDS z mapowaniem id→nazwa w kolejnej iteracji.

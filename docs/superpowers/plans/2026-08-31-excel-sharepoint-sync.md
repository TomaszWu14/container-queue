# Excel(SharePoint)→apka sync — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** n8n wysyła cały arkusz Excela z SharePointa na endpoint apki; apka natywnie liczy różnice per kontener, aktualizuje dane, pisze historię (AuditLog) i powiadamia (Notification).

**Architecture:** Endpoint `POST /api/import/sync` przyjmuje `.xlsx` + `company_code` + token serwisowy. `reconcile_queue()` parsuje (reuse `_parse_rows`), buduje pola przez wspólny `build_container_fields()` (wyciągnięty z istniejącego importu), porównuje z DB per numer kontenera, nadpisuje kolumny Excela, `record()` per zmienione pole, `notify()` per zmieniony kontener. Idempotentne: ten sam arkusz = 0 różnic.

**Tech Stack:** FastAPI, SQLAlchemy, openpyxl (już w projekcie), pytest.

## Global Constraints

- Wszystkie zmiany w `backend/app/`; testy w `backend/tests/`. Uruchamianie testów z katalogu `backend/`.
- Kolumny Excela = pola z `HEADER_MAP` (`imports.py`). Excel nadpisuje je bezwarunkowo, łącznie ze statusem (`_derive_status`). Pola spoza tej listy — nietknięte.
- Separacja spółek: dopasowanie kontenera po `container_no` znormalizowanym (`iso6346.normalize`) w obrębie `company_id`.
- Kurier = lokalny skrypt Python (Task 4) na maszynie 24h: wysyła plik 1:1, żadnej logiki różnic po jego stronie. BEZ n8n/Graph/Entra (ograniczenie IT — brak rejestracji app w Entra).
- Plik-master (na maszynie 24h, konto użytkownika): `C:\Users\<uzytkownik>\OneDrive - <firma>\<biblioteka> - Dokumenty\<folder>\Kolejka.xlsx`
- Kasowanie (kontener zniknął z arkusza) — POZA zakresem: tylko log, bez usuwania.

## File Structure

- Modify: `backend/app/routers/imports.py` — wyciągnięcie `build_container_fields`, nowe `reconcile_queue` + `_process_row` + `_audit_val`, dependency `require_sync_token`, endpoint `POST /sync`. Import `Company`.
- Modify: `backend/app/config.py` — `sync_api_token`, `sync_actor_login`.
- Create: `backend/tests/test_sync.py` — testy jednostkowe + integracyjny.

---

### Task 1: Wyciągnięcie `build_container_fields` (refactor bez zmiany zachowania)

Istniejący `import_containers` buduje `Container(...)` inline (imports.py:305–330). Wyciągamy budowę pól do funkcji, której użyje i insert (istniejący), i update (Task 2).

**Files:**
- Modify: `backend/app/routers/imports.py`
- Test: `backend/tests/test_sync.py`

**Interfaces:**
- Produces: `build_container_fields(db: Session, company, raw: dict) -> dict` — zwraca kwargs kolumn modelu `Container` (bez `company_id`, `container_no`, `transport_id`). Klucze: `vessel, eta, notify_date, transport_type, transport_details, supplier_id, forwarder_id, warehouse_id, order_numbers, delivery_note, purchase_note, document_flow, incoming_delivery_no, rf_number, customs_status, customs_agency, customs_agency_id, customs_assigned_at, sent_required, sent_number, sent_status, status, notes`.

- [ ] **Step 1: Napisz test jednostkowy buildera**

Utwórz `backend/tests/test_sync.py`:

```python
import datetime
from app.database import SessionLocal
from app.routers.imports import build_container_fields
from app.models import Company, ContainerStatus, CustomsStatus


def _company(db):
    return db.scalar(__import__("sqlalchemy").select(Company).where(Company.code == "BOREALIS"))


def test_build_container_fields_maps_excel_row():
    db = SessionLocal()
    try:
        raw = {
            "supplier": "ACME", "vessel": "MAERSK", "eta": datetime.datetime(2026, 9, 1),
            "transport": "kolej", "container_no": "MSKU7026499", "order_numbers": "4500",
            "delivery_note": "", "purchase_note": "", "warehouse": "ACME",
            "incoming_delivery_no": "", "rf_number": "", "forwarder": "SPEDALFA",
            "document_flow": "", "customs_agency": "", "customs": "odprawiony",
            "notify_date": datetime.datetime(2026, 9, 2), "sent_required": "TAK",
            "sent_number": "", "sent_status": "",
        }
        fields = build_container_fields(db, _company(db), raw)
        assert fields["vessel"] == "MAERSK"
        assert fields["eta"] == datetime.date(2026, 9, 1)
        assert fields["customs_status"] == CustomsStatus.ODPRAWIONY
        assert fields["status"] == ContainerStatus.AWIZOWANY  # notify_date + odprawiony
        assert "company_id" not in fields and "transport_id" not in fields
    finally:
        db.rollback()
        db.close()
```

- [ ] **Step 2: Uruchom test — ma FAIL (brak funkcji)**

Run: `cd backend && python -m pytest tests/test_sync.py::test_build_container_fields_maps_excel_row -v`
Expected: FAIL — `ImportError: cannot import name 'build_container_fields'`

- [ ] **Step 3: Wyciągnij funkcję**

W `backend/app/routers/imports.py` dodaj funkcję (nad `import_containers`):

```python
def build_container_fields(db: Session, company, raw: dict) -> dict:
    """Buduje kwargs kolumn Container z surowego wiersza Excela (bez identity:
    company_id/container_no/transport_id). Wspólne dla importu (insert) i sync (update)."""
    transport_type, transport_details = _classify_transport(_text(raw["transport"]))
    warehouse_name, warehouse_extra = _map_warehouse(_text(raw["warehouse"]))
    warehouse = _get_or_create(db, Warehouse, {"country": "PL"},
                               company_id=company.id, name=warehouse_name) if warehouse_name else None
    supplier_name = _text(raw["supplier"])
    supplier = _get_or_create(db, Supplier, {}, company_id=company.id,
                              name=supplier_name) if supplier_name else None
    forwarder_raw = _text(raw["forwarder"])
    forwarder_name = _parse_forwarder_name(forwarder_raw)
    forwarder = _get_or_create(db, Forwarder, {}, name=forwarder_name) if forwarder_name else None
    forwarder_extra = forwarder_raw if forwarder_raw != forwarder_name else ""
    customs_raw = _text(raw["customs"]).lower()
    customs = CustomsStatus.ODPRAWIONY if "odprawiony" in customs_raw \
        else (CustomsStatus.ZLECONA if customs_raw else CustomsStatus.BRAK)
    agency_name = _cap(_text(raw["customs_agency"]), 160)
    agency = _match_customs_agency(db, agency_name)
    sent_raw = _text(raw["sent_required"]).upper()
    notify_date = _date(raw["notify_date"])
    eta = _date(raw["eta"])
    notes = "\n".join(x for x in (warehouse_extra, forwarder_extra) if x)
    return {
        "vessel": _cap(_text(raw["vessel"]), 160),
        "eta": eta, "notify_date": notify_date,
        "transport_type": transport_type,
        "transport_details": _cap(transport_details, 200),
        "supplier_id": supplier.id if supplier else None,
        "forwarder_id": forwarder.id if forwarder else None,
        "warehouse_id": warehouse.id if warehouse else None,
        "order_numbers": _text(raw["order_numbers"]),
        "delivery_note": _text(raw["delivery_note"]),
        "purchase_note": _text(raw["purchase_note"]),
        "document_flow": _text(raw["document_flow"]),
        "incoming_delivery_no": _cap(_text(raw["incoming_delivery_no"]), 80),
        "rf_number": _cap(_text(raw["rf_number"]), 80),
        "customs_status": customs,
        "customs_agency": agency_name,
        "customs_agency_id": agency.id if agency else None,
        "customs_assigned_at": utcnow() if agency else None,
        "sent_required": True if sent_raw == "TAK" else (False if sent_raw == "NIE" else None),
        "sent_number": _text(raw["sent_number"]),
        "sent_status": _cap(_text(raw["sent_status"]), 120),
        "status": _derive_status(notify_date, customs, eta),
        "notes": notes,
    }
```

Następnie w `import_containers` zastąp inline-budowę `Container(...)` (imports.py:283–330) użyciem buildera. Blok wewnątrz `with db.begin_nested():` ma teraz wyglądać:

```python
            with db.begin_nested():
                fields = build_container_fields(db, company, raw)
                container = Container(company_id=company.id,
                                      container_no=entry["container_no"], **fields)
                year = (fields["notify_date"] or datetime.date.today()).year
                container.transport_id = next_transport_id(db, company, year)
                db.add(container)
                db.flush()
                record(db, entity_type="containers", entity_id=container.id, field="status",
                       old_value=None, new_value=container.status.value, user=user,
                       note=f"import z Excela ({file.filename})")
```

- [ ] **Step 4: Uruchom testy — buildery i istniejący import zielone**

Run: `cd backend && python -m pytest tests/test_sync.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/imports.py backend/tests/test_sync.py
git commit -m "refactor(import): wyciągnij build_container_fields (wspólne dla import+sync)"
```

---

### Task 2: `reconcile_queue` — diff + update + audyt

**Files:**
- Modify: `backend/app/routers/imports.py`
- Test: `backend/tests/test_sync.py`

**Interfaces:**
- Consumes: `build_container_fields` (Task 1).
- Produces:
  - `reconcile_queue(db: Session, company, parsed: list[dict], actor) -> list[dict]` — zwraca listę `{"container": Container, "changes": list[tuple[str, object, object]]}`. Dla nowego kontenera `changes == [("__new__", None, None)]`.
  - `SYNCED_FIELDS: tuple[str, ...]` — pola porównywane/nadpisywane (bez `customs_assigned_at`).

- [ ] **Step 1: Napisz test reconcile (insert → update → idempotencja)**

Dopisz do `backend/tests/test_sync.py`:

```python
from sqlalchemy import select
from app.routers.imports import reconcile_queue
from app.models import Container


def _raw(no, eta_day, customs="", notify_day=None):
    return {
        "supplier": "ACME", "vessel": "MAERSK",
        "eta": datetime.datetime(2026, 9, eta_day),
        "transport": "kolej", "container_no": no, "order_numbers": "",
        "delivery_note": "", "purchase_note": "", "warehouse": "",
        "incoming_delivery_no": "", "rf_number": "", "forwarder": "",
        "document_flow": "", "customs_agency": "", "customs": customs,
        "notify_date": datetime.datetime(2026, 9, notify_day) if notify_day else None,
        "sent_required": "", "sent_number": "", "sent_status": "",
    }


def test_reconcile_insert_update_idempotent():
    db = SessionLocal()
    try:
        company = _company(db)
        no = "MSKU7026499"
        # 1. insert
        r1 = reconcile_queue(db, company, [_raw(no, 1)], None)
        db.flush()
        assert r1[0]["changes"][0][0] == "__new__"
        cont = db.scalar(select(Container).where(Container.company_id == company.id,
                                                 Container.container_no == no))
        assert cont.eta == datetime.date(2026, 9, 1)
        # 2. update — zmiana ETA
        r2 = reconcile_queue(db, company, [_raw(no, 5)], None)
        db.flush()
        changed = {f for f, _, _ in r2[0]["changes"]}
        assert "eta" in changed
        assert cont.eta == datetime.date(2026, 9, 5)
        # 3. idempotencja — ten sam arkusz, 0 zmian
        r3 = reconcile_queue(db, company, [_raw(no, 5)], None)
        assert r3 == []
    finally:
        db.rollback()
        db.close()
```

- [ ] **Step 2: Uruchom — FAIL (brak reconcile_queue)**

Run: `cd backend && python -m pytest tests/test_sync.py::test_reconcile_insert_update_idempotent -v`
Expected: FAIL — `ImportError: cannot import name 'reconcile_queue'`

- [ ] **Step 3: Zaimplementuj reconcile**

W `backend/app/routers/imports.py` dodaj:

```python
# pola nadpisywane z Excela na istniejących kontenerach. customs_assigned_at
# celowo wykluczone: to świeży timestamp z każdego build → floodowałby audyt.
SYNCED_FIELDS = (
    "vessel", "eta", "notify_date", "transport_type", "transport_details",
    "supplier_id", "forwarder_id", "warehouse_id", "order_numbers", "delivery_note",
    "purchase_note", "document_flow", "incoming_delivery_no", "rf_number",
    "customs_status", "customs_agency", "customs_agency_id", "sent_required",
    "sent_number", "sent_status", "status", "notes",
)


def _audit_val(v):
    """Serializacja wartości do AuditLog (enum→value, reszta→str, None→None)."""
    if v is None:
        return None
    return v.value if hasattr(v, "value") else str(v)


def _process_row(db: Session, company, raw: dict, existing: dict, actor) -> dict | None:
    number = iso6346.normalize(_text(raw["container_no"]))
    ok, _reason = iso6346.validate(number)
    if not ok:
        return None
    fields = build_container_fields(db, company, raw)
    container = existing.get(number)
    if container is None:
        container = Container(company_id=company.id, container_no=number, **fields)
        year = (fields["notify_date"] or datetime.date.today()).year
        container.transport_id = next_transport_id(db, company, year)
        db.add(container)
        db.flush()
        existing[number] = container
        record(db, entity_type="containers", entity_id=container.id, field="status",
               old_value=None, new_value=container.status.value, user=actor,
               note="sync z Excela (nowy)")
        return {"container": container, "changes": [("__new__", None, None)]}
    changes = []
    for f in SYNCED_FIELDS:
        new_val, old_val = fields[f], getattr(container, f)
        if old_val != new_val:
            setattr(container, f, new_val)
            changes.append((f, old_val, new_val))
    if not changes:
        return None
    if any(f == "customs_agency_id" for f, _, _ in changes):
        container.customs_assigned_at = fields["customs_assigned_at"]
    for f, old_val, new_val in changes:
        record(db, entity_type="containers", entity_id=container.id, field=f,
               old_value=_audit_val(old_val), new_value=_audit_val(new_val),
               user=actor, note="sync z Excela")
    return {"container": container, "changes": changes}


def reconcile_queue(db: Session, company, parsed: list[dict], actor) -> list[dict]:
    """Uzgadnia snapshot arkusza z DB per numer kontenera. Insert nowych, update
    zmienionych (Excel nadpisuje SYNCED_FIELDS), audyt per pole. Zwraca listę zmian.
    Każdy wiersz w savepoincie — jeden wadliwy nie wywala całego syncu."""
    existing = {c.container_no: c for c in db.scalars(
        select(Container).where(Container.company_id == company.id))}
    results: list[dict] = []
    for raw in parsed:
        try:
            with db.begin_nested():
                row_result = _process_row(db, company, raw, existing, actor)
        except Exception as exc:  # noqa: BLE001 — wadliwy wiersz nie przerywa syncu
            logger.warning("sync: pominięto %s: %s", _text(raw.get("container_no")), exc)
            continue
        if row_result:
            results.append(row_result)
    return results
```

- [ ] **Step 4: Uruchom test — PASS**

Run: `cd backend && python -m pytest tests/test_sync.py -v`
Expected: PASS (3 testy)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/imports.py backend/tests/test_sync.py
git commit -m "feat(sync): reconcile_queue — diff+update+audyt per pole (Excel nadpisuje)"
```

---

### Task 3: Endpoint `POST /api/import/sync` + token serwisowy + powiadomienia

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/routers/imports.py`
- Test: `backend/tests/test_sync.py`

**Interfaces:**
- Consumes: `reconcile_queue` (Task 2), `_parse_rows`, `read_upload_capped`, `company_watchers`/`notify` (z `..notifications`).
- Produces: endpoint `POST /api/import/sync?company_code=…` (multipart `file`, nagłówek `Authorization: Bearer <sync_api_token>`) → JSON `{"containers": int, "changed": int, "notified": int}`.

- [ ] **Step 1: Napisz test integracyjny (endpoint + audyt + powiadomienie + izolacja pola apki)**

Dopisz do `backend/tests/test_sync.py`:

```python
import io
from openpyxl import Workbook
from app.config import settings as app_settings
from app.models import AuditLog, Notification


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["DOSTAWCA", "STATEK", "ETA", "KOLEJ/KOŁA", "NR KONTENERA",
               "STATUS ODPRAWY", "DATA ROZŁADUNKU"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_sync_endpoint_updates_notifies_and_audits(client, monkeypatch):
    monkeypatch.setattr(app_settings, "sync_api_token", "test-token", raising=False)
    hdr = {"Authorization": "Bearer test-token"}
    no = "MSKU7026499"
    # 1. pierwszy snapshot — insert
    f1 = _xlsx([["ACME", "MAERSK", datetime.datetime(2026, 9, 1), "kolej", no, "", ""]])
    r1 = client.post("/api/import/sync?company_code=BOREALIS", headers=hdr,
                     files={"file": ("q.xlsx", f1)})
    assert r1.status_code == 200, r1.text
    assert r1.json()["changed"] == 1
    # 2. drugi snapshot — zmiana ETA → update + audyt + powiadomienie
    f2 = _xlsx([["ACME", "MAERSK", datetime.datetime(2026, 9, 9), "kolej", no, "", ""]])
    r2 = client.post("/api/import/sync?company_code=BOREALIS", headers=hdr,
                     files={"file": ("q.xlsx", f2)})
    assert r2.json()["changed"] == 1 and r2.json()["notified"] >= 1
    # 3. idempotencja — ten sam plik, 0 zmian
    r3 = client.post("/api/import/sync?company_code=BOREALIS", headers=hdr,
                     files={"file": ("q.xlsx", f2)})
    assert r3.json()["changed"] == 0
    # audyt zawiera wpis o zmianie eta
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        assert db.query(AuditLog).filter(AuditLog.field == "eta",
                                         AuditLog.note == "sync z Excela").count() >= 1
        assert db.query(Notification).filter(Notification.kind == "excel-sync").count() >= 1
    finally:
        db.close()


def test_sync_rejects_bad_token(client):
    r = client.post("/api/import/sync?company_code=BOREALIS",
                    headers={"Authorization": "Bearer wrong"},
                    files={"file": ("q.xlsx", b"x")})
    assert r.status_code == 401
```

- [ ] **Step 2: Uruchom — FAIL (brak endpointu/tokena)**

Run: `cd backend && python -m pytest tests/test_sync.py::test_sync_rejects_bad_token -v`
Expected: FAIL — 404 (endpoint nie istnieje) zamiast 401

- [ ] **Step 3a: Dodaj config**

W `backend/app/config.py` (obok innych pól Settings):

```python
    sync_api_token: str = ""            # token dla n8n; pusty = sync wyłączony (401)
    sync_actor_login: str = "excel-sync"  # opcjonalne konto serwisowe do atrybucji audytu
```

- [ ] **Step 3b: Dodaj dependency + endpoint**

W `backend/app/routers/imports.py`:

1. Rozszerz import modeli o `Company`:

```python
from ..models import (
    Company, Container, ContainerStatus, CustomsAgency, CustomsStatus, Forwarder,
    Supplier, TransportType, User, Warehouse, utcnow,
)
```

2. Dodaj import `Header` do fastapi (dopisz do istniejącej linii importu fastapi):

```python
from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile, status
```

3. Dodaj dependency i endpoint (na końcu pliku):

```python
def require_sync_token(authorization: str = Header(default="")) -> None:
    """Uwierzytelnia n8n statycznym tokenem serwisowym (nie sesja usera)."""
    token = app_config.sync_api_token
    if not token or authorization != f"Bearer {token}":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Brak lub błędny token sync.")


@router.post("/sync")
async def sync_queue(
    file: UploadFile,
    company_code: str = Query(...),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_sync_token),
):
    """Snapshot arkusza z SharePointa (przez n8n) → uzgodnienie kolejki.
    Excel nadpisuje swoje kolumny; per zmieniony kontener: audyt + powiadomienie."""
    from ..notifications import company_watchers, notify

    company = db.scalar(select(Company).where(Company.code == company_code.upper()))
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nieznana spółka.")
    actor = db.scalar(select(User).where(User.login == app_config.sync_actor_login))
    parsed = _parse_rows(
        await read_upload_capped(file, app_config.max_upload_mb, "Plik sync"), company)
    results = reconcile_queue(db, company, parsed, actor)

    watchers = company_watchers(db, company.id)
    notified = 0
    for r in results:
        c = r["container"]
        if r["changes"] and r["changes"][0][0] == "__new__":
            title, body = f"Nowy kontener z Excela: {c.container_no}", ""
        else:
            fields = ", ".join(f for f, _, _ in r["changes"])
            title, body = f"Zmiana w kontenerze {c.container_no}", f"Zmienione pola: {fields}"
        if notify(db, watchers, kind="excel-sync", title=title, body=body, container_id=c.id):
            notified += 1
    db.commit()
    return {"containers": len(parsed), "changed": len(results), "notified": notified}
```

- [ ] **Step 4: Uruchom cały plik testów — PASS**

Run: `cd backend && python -m pytest tests/test_sync.py -v`
Expected: PASS (wszystkie: builder, reconcile, endpoint, zły token)

- [ ] **Step 5: Regresja — pełny suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS (żaden istniejący test nie pęka po refaktorze importu)

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/routers/imports.py backend/tests/test_sync.py
git commit -m "feat(sync): endpoint /api/import/sync + token serwisowy dla n8n + powiadomienia"
```

---

### Task 4: Lokalny agent-watcher (kurier Excel→apka, Faza A)

Skrypt Python na maszynie 24h. Pilnuje pliku-mastera; przy zmianie POST-uje go na endpoint z Task 3. To osobny deliverable — NIE część apki serwerowej; leży w repo w `agent/`.

**Files:**
- Create: `agent/sync_agent.py`
- Create: `agent/README.md` (uruchomienie + Task Scheduler)
- Test: `agent/test_sync_agent.py`

**Interfaces:**
- Consumes: endpoint `POST /api/import/sync` (Task 3).
- Produces: `detect_change(path, last_mtime) -> float | None` (zwraca nowy mtime gdy plik się zmienił i ustabilizował, inaczej None); `push_snapshot(session, base_url, token, company_code, path) -> dict` (POST pliku, zwraca JSON odpowiedzi).

- [ ] **Step 1: Napisz test detekcji zmiany + wysyłki (mock HTTP)**

Utwórz `agent/test_sync_agent.py`:

```python
import io
from sync_agent import detect_change, push_snapshot


def test_detect_change_reports_new_mtime(tmp_path):
    f = tmp_path / "q.xlsx"
    f.write_bytes(b"a")
    m1 = detect_change(str(f), None)
    assert m1 is not None                      # pierwszy raz = zmiana
    assert detect_change(str(f), m1) is None    # bez zmiany = None
    f.write_bytes(b"bb")
    assert detect_change(str(f), m1) is not None  # po zmianie = nowy mtime


class _Resp:
    status_code = 200
    def json(self): return {"containers": 1, "changed": 1, "notified": 0}
    def raise_for_status(self): pass


class _Session:
    def __init__(self): self.calls = []
    def post(self, url, **kw): self.calls.append((url, kw)); return _Resp()


def test_push_snapshot_posts_file_with_token(tmp_path):
    f = tmp_path / "q.xlsx"
    f.write_bytes(b"xlsxdata")
    s = _Session()
    out = push_snapshot(s, "http://app", "tok", "BOREALIS", str(f))
    url, kw = s.calls[0]
    assert url == "http://app/api/import/sync"
    assert kw["params"] == {"company_code": "BOREALIS"}
    assert kw["headers"]["Authorization"] == "Bearer tok"
    assert "file" in kw["files"]
    assert out["changed"] == 1
```

- [ ] **Step 2: Uruchom — FAIL (brak modułu)**

Run: `cd agent && python -m pytest test_sync_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sync_agent'`

- [ ] **Step 3: Zaimplementuj agenta**

Utwórz `agent/sync_agent.py`:

```python
"""Lokalny agent: pilnuje pliku kolejki (OneDrive-synced) i POST-uje snapshot do apki.
Faza A (jednokierunkowo Excel->apka). Uruchamiany na maszynie 24h (Task Scheduler)."""
import os
import sys
import time
import logging

import requests

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sync_agent")


def detect_change(path: str, last_mtime: float | None) -> float | None:
    """Zwraca nowy mtime, jeśli plik istnieje i zmienił się względem last_mtime
    (i nie jest w trakcie zapisu — sprawdzamy stabilność rozmiaru). Inaczej None."""
    try:
        m = os.path.getmtime(path)
    except OSError:
        return None
    if last_mtime is not None and m == last_mtime:
        return None
    # stabilizacja: plik może być w trakcie synchronizacji/zapisu
    size1 = os.path.getsize(path)
    time.sleep(2)
    if os.path.getsize(path) != size1:
        return None  # jeszcze się zmienia — złapiemy w następnym cyklu
    return m


def push_snapshot(session, base_url: str, token: str, company_code: str, path: str) -> dict:
    with open(path, "rb") as fh:
        resp = session.post(
            f"{base_url.rstrip('/')}/api/import/sync",
            params={"company_code": company_code},
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (os.path.basename(path), fh)},
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()


def run(path: str, base_url: str, token: str, company_code: str, interval: int = 30) -> None:
    session = requests.Session()
    last_mtime: float | None = None
    log.info("Agent start: pilnuję %s co %ss", path, interval)
    while True:
        new_mtime = detect_change(path, last_mtime)
        if new_mtime is not None:
            try:
                out = push_snapshot(session, base_url, token, company_code, path)
                last_mtime = new_mtime
                log.info("Wysłano snapshot: %s", out)
            except Exception as exc:  # noqa: BLE001 — nie przerywaj pętli na błędzie sieci
                log.warning("Błąd wysyłki (ponowię): %s", exc)
        time.sleep(interval)


if __name__ == "__main__":
    run(
        path=os.environ["SYNC_FILE"],
        base_url=os.environ["SYNC_URL"],
        token=os.environ["SYNC_TOKEN"],
        company_code=os.environ.get("SYNC_COMPANY", "ACME"),
        interval=int(os.environ.get("SYNC_INTERVAL", "30")),
    )
```

- [ ] **Step 4: Uruchom testy — PASS**

Run: `cd agent && python -m pytest test_sync_agent.py -v`
Expected: PASS (2 testy)

- [ ] **Step 5: README z uruchomieniem**

Utwórz `agent/README.md`:

```markdown
# Lokalny agent sync kolejki (Faza A: Excel -> apka)

Pilnuje pliku kolejki zsynchronizowanego przez OneDrive i wysyła snapshot do apki
przy każdej zmianie. Uruchamiany na maszynie 24h.

## Wymagania
- Python 3.11+, `pip install requests`

## Konfiguracja (zmienne środowiskowe)
- `SYNC_FILE`  — ścieżka do `.xlsx` (np. `C:\Users\<uzytkownik>\OneDrive - <firma>\<biblioteka> - Dokumenty\<folder>\Kolejka.xlsx`)
- `SYNC_URL`   — adres apki (np. `https://timporye.example.com`)
- `SYNC_TOKEN` — ten sam co `SYNC_API_TOKEN` w apce
- `SYNC_COMPANY` — kod spółki (domyślnie `ACME`)
- `SYNC_INTERVAL` — sekundy między sprawdzeniami (domyślnie 30)

## Uruchomienie ręczne
    set SYNC_FILE=...
    set SYNC_URL=...
    set SYNC_TOKEN=...
    python sync_agent.py

## Autostart (Windows Task Scheduler)
Utwórz zadanie „przy logowaniu / przy starcie", akcja: `python C:\path\sync_agent.py`,
z ustawionymi zmiennymi środowiskowymi konta serwisowego. Zaznacz „Uruchom niezależnie
od tego, czy użytkownik jest zalogowany".
```

- [ ] **Step 6: Commit**

```bash
git add agent/sync_agent.py agent/test_sync_agent.py agent/README.md
git commit -m "feat(agent): lokalny watcher Excel->apka (Faza A kurier, bez n8n)"
```

## Wdrożenie (warstwa operacyjna, po kodzie)

1. Env apki (Coolify): `SYNC_API_TOKEN=<losowy sekret>`. Opcjonalnie konto `excel-sync` (rola logistics) do atrybucji historii; bez niego audyt ma `user=None`.
2. Maszyna 24h: skopiuj `agent/`, ustaw zmienne, dodaj do Task Scheduler (patrz `agent/README.md`).

## Self-Review

- **Spec coverage:** n8n=kurier (endpoint przyjmuje cały plik ✓), apka liczy różnice (`reconcile_queue` ✓), Excel nadpisuje kolumny łącznie ze statusem (`SYNCED_FIELDS` zawiera `status` ✓), pola tylko-w-apce nietknięte (strukturalnie: diff pętli wyłącznie po `SYNCED_FIELDS`, więc kolumny spoza listy nie są dotykane — gwarancja z konstrukcji, nie z osobnego assertu), audyt per pole (✓), powiadomienia per kontener (✓), idempotencja (test ✓), kasowanie poza zakresem (nie implementowane ✓), token serwisowy + konto `excel-sync` (✓).
- **Placeholdery:** brak — każdy krok ma pełny kod/komendę.
- **Spójność typów:** `build_container_fields` klucze == `SYNCED_FIELDS` ∪ `{customs_assigned_at}`; `reconcile_queue` zwraca `{"container","changes"}` używane spójnie w endpoincie; `_audit_val` serializuje enum/date do AuditLog.
- **Uwaga (świadome uproszczenie):** `customs_assigned_at` poza diffem, by nie floodować audytu; aktualizowany tylko gdy zmieni się agencja.

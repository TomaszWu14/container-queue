# Plaster 4: CRD + eskalacja (backend) — Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Aktualizacja CRD zamówienia z automatycznym liczeniem odchylenia od `crd_target` i eskalacją (auto-blokada) przy przekroczeniu progu; odblokowanie, gdy nowy target schodzi poniżej progu.

**Architecture:** Czysta funkcja odchylenia + stała progu w `app/consolidation.py`; endpoint PATCH w `app/routers/consolidation.py` używający `record_changes` (audyt) i zmieniający `cart_status` wg progu. Reużywa istniejącego filtra `GET /api/purchase-orders?cart_status=zablokowane` do listy zablokowanych.

**Tech Stack:** FastAPI, SQLAlchemy, pytest.

## Global Constraints
- ZAŁOŻENIA (do korekty biznesu): odchylenie = `(crd − crd_target).days`; próg `CRD_ESCALATION_DAYS = 10` (stała, konfigurowalna później przez Admina); `≥ próg` → `zablokowane`; nowy target dający odchylenie `< próg` na zablokowanym → `w_koszyku`. Blokada per-zamówienie (spójne z plastrem 1: zablokowane wypada z fill/crd).
- Kanał alertu (mail/sygnał) POZA zakresem tego plastra (kolejny plaster) — tu tylko blokada + audyt.
- Rola: aktualizacja CRD = `admin + logistics + purchasing`.
- Izolacja spółki (reużyj `_scoped_po` z plastra 2).
- Audyt każdej zmiany przez `record_changes` + `db.commit()`.

---

### Task 1: Funkcja odchylenia + stała progu

**Files:**
- Modify: `backend/app/consolidation.py`
- Test: `backend/tests/test_crd.py`

**Interfaces:**
- Produces: `CRD_ESCALATION_DAYS: int = 10`; `crd_deviation_days(po) -> int | None` (None gdy brak którejś daty).

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_crd.py
import datetime
from app.consolidation import crd_deviation_days, CRD_ESCALATION_DAYS
from app.models import PurchaseOrder


def test_deviation_none_without_dates(client):
    assert crd_deviation_days(PurchaseOrder(order_no="X")) is None


def test_deviation_positive_days(client):
    po = PurchaseOrder(order_no="Y", crd=datetime.date(2026, 9, 25),
                       crd_target=datetime.date(2026, 9, 10))
    assert crd_deviation_days(po) == 15
    assert CRD_ESCALATION_DAYS == 10
```

- [ ] **Step 2: Run — FAIL** (`cd backend && python -m pytest tests/test_crd.py -v`)

- [ ] **Step 3: Implement w consolidation.py**

```python
CRD_ESCALATION_DAYS = 10   # prog eskalacji (dni); konfigurowalny przez Admina w przyszlosci


def crd_deviation_days(po) -> int | None:
    """Odchylenie aktualnego CRD od zakladanego (crd_target), w dniach. None gdy
    brak ktorejkolwiek daty. Dodatnie = poslizg (CRD pozniej niz zakladano)."""
    if po.crd is None or po.crd_target is None:
        return None
    return (po.crd - po.crd_target).days
```

- [ ] **Step 4: Run — PASS**; **Step 5: Commit** `feat(front): odchylenie CRD + prog eskalacji`

---

### Task 2: Endpoint aktualizacji CRD z eskalacją

**Files:**
- Modify: `backend/app/routers/consolidation.py`
- Test: `backend/tests/test_crd.py` (dopisać)

**Interfaces:**
- Consumes: `crd_deviation_days`, `CRD_ESCALATION_DAYS` (`app.consolidation`); `_scoped_po`, `record_changes`, `CartStatus` (istniejące).
- Produces: `PATCH /api/purchase-orders/{po_id}/crd` body `{crd: date|null, crd_target: date|null}` → `{id, crd, crd_target, deviation_days, cart_status}`.

- [ ] **Step 1: Failing tests**

```python
# dopisz do backend/tests/test_crd.py
from app.database import SessionLocal
from app.models import Company, CartStatus


def _po(db, **kw):
    co = db.query(Company).first()
    po = PurchaseOrder(company_id=co.id, order_no=kw.pop("order_no", "CRD-1"),
                       cart_status=CartStatus.w_koszyku.value, **kw)
    db.add(po); db.commit()
    return po.id


def test_crd_update_within_threshold_no_block(client, admin_headers):
    with SessionLocal() as db:
        pid = _po(db, order_no="CRD-OK")
    r = client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                     json={"crd": "2026-09-15", "crd_target": "2026-09-10"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deviation_days"] == 5 and body["cart_status"] == "w_koszyku"


def test_crd_update_over_threshold_auto_blocks(client, admin_headers):
    with SessionLocal() as db:
        pid = _po(db, order_no="CRD-BLK")
    r = client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                     json={"crd": "2026-09-25", "crd_target": "2026-09-10"})
    assert r.status_code == 200
    assert r.json()["deviation_days"] == 15 and r.json()["cart_status"] == "zablokowane"


def test_new_target_unblocks_when_below_threshold(client, admin_headers):
    with SessionLocal() as db:
        pid = _po(db, order_no="CRD-UNB")
    client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                 json={"crd": "2026-09-25", "crd_target": "2026-09-10"})  # zablokowane
    r = client.patch(f"/api/purchase-orders/{pid}/crd", headers=admin_headers,
                     json={"crd": "2026-09-25", "crd_target": "2026-09-20"})  # odchylenie 5
    assert r.json()["cart_status"] == "w_koszyku"
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement endpoint**

Dodaj na górze (jeśli brak): `import datetime`, `from pydantic import BaseModel`, oraz do importów z `..consolidation`: `crd_deviation_days, CRD_ESCALATION_DAYS`.

```python
class CrdIn(BaseModel):
    crd: datetime.date | None = None
    crd_target: datetime.date | None = None


@router.patch("/purchase-orders/{po_id}/crd")
def update_crd(po_id: int, body: CrdIn, db: Session = Depends(get_db),
               user: User = _releasers) -> dict:
    po = _scoped_po(db, po_id, user)
    changes = {"crd": body.crd, "crd_target": body.crd_target}
    dev = None
    if body.crd is not None and body.crd_target is not None:
        dev = (body.crd - body.crd_target).days
        if dev >= CRD_ESCALATION_DAYS:
            changes["cart_status"] = CartStatus.zablokowane.value
        elif po.cart_status == CartStatus.zablokowane.value:
            # nowy target sprowadzil odchylenie ponizej progu -> odblokuj
            changes["cart_status"] = CartStatus.w_koszyku.value
    record_changes(db, po, changes, user,
                   note=f"aktualizacja CRD (odchylenie {dev if dev is not None else '—'} dni)")
    db.commit(); db.refresh(po)
    return {"id": po.id, "crd": po.crd, "crd_target": po.crd_target,
            "deviation_days": crd_deviation_days(po), "cart_status": po.cart_status}
```

Uwaga: `_releasers` (admin+logistics+purchasing) jest już zdefiniowane w consolidation.py z plastra 2 — reużyj.

- [ ] **Step 4: Run — PASS** (3 testy)

- [ ] **Step 5: Regresja**

Run: `cd backend && python -m pytest tests/test_crd.py tests/test_koszyk_mutacje.py tests/test_consolidation.py -q`
Expected: PASS

- [ ] **Step 6: Commit** `feat(front): endpoint aktualizacji CRD z auto-eskalacja`

---

## Poza zakresem (kolejne plastry)
Alert/powiadomienie do zespołu kupców przy eskalacji (mail/sygnał); konfiguracja progu przez Admina; UI edycji CRD w koszyku; auto-konsolidacja; SAP.

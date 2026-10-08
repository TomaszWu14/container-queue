# Model danych front↔back (plaster 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Położyć fundament front-half procesu — pola CRD/koszyk na zamówieniu, stan konsolidacji na kontenerze i wyliczenia (fill_cbm/CRD), reużywając istniejącej relacji `PurchaseOrder.container_id` (many:1).

**Architecture:** Addytywna zmiana modelu (nowe kolumny + 2 enumy), czysty serwis wyliczeń `consolidation.py`, oraz router tylko-do-odczytu. Bez tabeli m:n (relacja już istnieje przez `container_id`), bez pola CBM (już jest).

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (Mapped), Alembic, pytest.

## Global Constraints

- Migracja **wyłącznie addytywna** (nowe kolumny nullable/`server_default`); nie rusza istniejących wierszy ani obiegu kolejki.
- Jedna głowa alembica — `down_revision` łańcuchowo po obecnej głowie `care001` (strażnik `test_migration_chain`).
- Enumy trzymane jako `String` z `server_default` (wzorzec repo: `customs_status`/`ContainerStatus`).
- Nowe encje/endpointy przechodzą przez izolację spółki (`company_filter_ids`) — partner zewnętrzny nie widzi cudzych zamówień.
- Reguły biznesowe (potwierdzone 2026-09-22): CRD kontenera = max CRD zamówień; zablokowane zamówienie wypada z wyliczeń; capacity=70 CBM.
- Testy: fixture `client` + autouse `create_all` (świeże metadane per test).

---

### Task 1: Enumy + kolumny modelu + migracja

**Files:**
- Modify: `backend/app/models.py` (dodać 2 enumy + kolumny na `PurchaseOrder` i `Container`)
- Create: `backend/migrations/versions/frontmodel001_front_half_fields.py`
- Test: `backend/tests/test_consolidation.py`

**Interfaces:**
- Produces: `CartStatus`, `ConsolidationStatus` (enumy str); `PurchaseOrder.crd`, `.crd_target`, `.cart_status`; `Container.consolidation_status`, `.capacity_cbm`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_consolidation.py
from app.database import SessionLocal
from app.models import Company, Container, PurchaseOrder, CartStatus, ConsolidationStatus


def test_new_fields_have_defaults(client):
    with SessionLocal() as db:
        co = Company(name="FM Co", code="FMCO")
        db.add(co); db.flush()
        po = PurchaseOrder(company_id=co.id, order_no="PO-1")
        cont = Container(container_no="FMCU0000001", company_id=co.id)
        db.add_all([po, cont]); db.commit()
        db.refresh(po); db.refresh(cont)
        assert po.cart_status == CartStatus.w_koszyku.value
        assert po.crd is None and po.crd_target is None
        assert cont.consolidation_status == ConsolidationStatus.otwarty.value
        assert float(cont.capacity_cbm) == 70.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_consolidation.py::test_new_fields_have_defaults -v`
Expected: FAIL — `ImportError: cannot import name 'CartStatus'`

- [ ] **Step 3: Add enums to models.py**

Wstaw obok innych enumów (po `class ContainerStatus`):

```python
class CartStatus(str, enum.Enum):
    w_koszyku = "w_koszyku"
    zwolnione = "zwolnione"
    przypisane = "przypisane"
    zablokowane = "zablokowane"


class ConsolidationStatus(str, enum.Enum):
    otwarty = "otwarty"
    wypelniony = "wypelniony"
    zamkniety = "zamkniety"
```

- [ ] **Step 4: Add columns to PurchaseOrder**

W `class PurchaseOrder`, po `cbm`:

```python
    crd: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    crd_target: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    cart_status: Mapped[str] = mapped_column(
        String(20), default=CartStatus.w_koszyku.value,
        server_default=CartStatus.w_koszyku.value)
```

- [ ] **Step 5: Add columns to Container**

W `class Container`, po istniejących kolumnach statusu:

```python
    consolidation_status: Mapped[str] = mapped_column(
        String(20), default=ConsolidationStatus.otwarty.value,
        server_default=ConsolidationStatus.otwarty.value)
    capacity_cbm: Mapped[float] = mapped_column(
        Numeric(10, 3), default=70, server_default="70")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_consolidation.py::test_new_fields_have_defaults -v`
Expected: PASS (create_all buduje kolumny z metadanych)

- [ ] **Step 7: Create Alembic migration (dla produkcji)**

```python
# backend/migrations/versions/frontmodel001_front_half_fields.py
"""Front-half: pola CRD/koszyk na zamowieniu + stan konsolidacji na kontenerze.

Revision ID: frontmodel001
Revises: care001
Create Date: 2026-09-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'frontmodel001'
down_revision: Union[str, Sequence[str], None] = 'care001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_orders', sa.Column('crd', sa.Date(), nullable=True))
    op.add_column('purchase_orders', sa.Column('crd_target', sa.Date(), nullable=True))
    op.add_column('purchase_orders', sa.Column(
        'cart_status', sa.String(length=20), nullable=False, server_default='w_koszyku'))
    op.add_column('containers', sa.Column(
        'consolidation_status', sa.String(length=20), nullable=False, server_default='otwarty'))
    op.add_column('containers', sa.Column(
        'capacity_cbm', sa.Numeric(10, 3), nullable=False, server_default='70'))


def downgrade() -> None:
    op.drop_column('containers', 'capacity_cbm')
    op.drop_column('containers', 'consolidation_status')
    op.drop_column('purchase_orders', 'cart_status')
    op.drop_column('purchase_orders', 'crd_target')
    op.drop_column('purchase_orders', 'crd')
```

- [ ] **Step 8: Verify single alembic head**

Run: `cd backend && python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; s=ScriptDirectory.from_config(Config('alembic.ini')); print(s.get_heads())"`
Expected: `['frontmodel001']` (dokładnie jedna głowa)

- [ ] **Step 9: Commit**

```bash
git add backend/app/models.py backend/migrations/versions/frontmodel001_front_half_fields.py backend/tests/test_consolidation.py
git commit -m "feat(front): pola CRD/koszyk + stan konsolidacji (model + migracja)"
```

---

### Task 2: Serwis wyliczeń konsolidacji

**Files:**
- Create: `backend/app/consolidation.py`
- Test: `backend/tests/test_consolidation.py` (dopisać)

**Interfaces:**
- Consumes: `PurchaseOrder.container_id`, `.cbm`, `.crd`, `.cart_status`; `Container.consolidation_status`.
- Produces: `container_fill_cbm(db, container_id) -> float`, `container_crd(db, container_id) -> datetime.date | None`, `can_add_order(container) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# dopisz do backend/tests/test_consolidation.py
import datetime
from app.consolidation import container_fill_cbm, container_crd, can_add_order


def _seed_consolidation(db):
    co = Company(name="CN Co", code="CNCO"); db.add(co); db.flush()
    cont = Container(container_no="CNCU0000001", company_id=co.id)
    db.add(cont); db.flush()
    d = datetime.date
    db.add_all([
        PurchaseOrder(company_id=co.id, order_no="A", container_id=cont.id,
                      cbm=10, crd=d(2026, 9, 10), cart_status=CartStatus.przypisane.value),
        PurchaseOrder(company_id=co.id, order_no="B", container_id=cont.id,
                      cbm=20, crd=d(2026, 9, 15), cart_status=CartStatus.przypisane.value),
        # zablokowane — NIE liczy się do fill ani CRD
        PurchaseOrder(company_id=co.id, order_no="C", container_id=cont.id,
                      cbm=999, crd=d(2027, 1, 1), cart_status=CartStatus.zablokowane.value),
    ])
    db.commit()
    return cont


def test_fill_cbm_ignores_blocked(client):
    with SessionLocal() as db:
        cont = _seed_consolidation(db)
        assert container_fill_cbm(db, cont.id) == 30.0        # 10+20, bez 999


def test_crd_is_latest_of_unblocked(client):
    with SessionLocal() as db:
        cont = _seed_consolidation(db)
        assert container_crd(db, cont.id) == datetime.date(2026, 9, 15)  # max(10,15), bez 2027


def test_can_add_order_false_when_closed(client):
    with SessionLocal() as db:
        co = Company(name="ZC", code="ZCCO"); db.add(co); db.flush()
        closed = Container(container_no="ZCCU0000001", company_id=co.id,
                           consolidation_status=ConsolidationStatus.zamkniety.value)
        db.add(closed); db.commit()
        assert can_add_order(closed) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_consolidation.py -k "fill_cbm or crd_is_latest or can_add_order" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.consolidation'`

- [ ] **Step 3: Implement consolidation.py**

```python
# backend/app/consolidation.py
"""Wyliczenia konsolidacji kontenera z przypisanych zamowien (reguly potwierdzone
2026-09-22): fill_cbm = suma CBM niezablokowanych; CRD = max CRD niezablokowanych;
kontener zamkniety nie przyjmuje nowych zamowien."""
import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import CartStatus, ConsolidationStatus, Container, PurchaseOrder


def _unblocked(container_id: int):
    return (PurchaseOrder.container_id == container_id,
            PurchaseOrder.cart_status != CartStatus.zablokowane.value)


def container_fill_cbm(db: Session, container_id: int) -> float:
    total = db.scalar(select(func.coalesce(func.sum(PurchaseOrder.cbm), 0))
                      .where(*_unblocked(container_id)))
    return float(total or 0)


def container_crd(db: Session, container_id: int) -> datetime.date | None:
    return db.scalar(select(func.max(PurchaseOrder.crd)).where(*_unblocked(container_id)))


def can_add_order(container: Container) -> bool:
    return container.consolidation_status != ConsolidationStatus.zamkniety.value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_consolidation.py -k "fill_cbm or crd_is_latest or can_add_order" -v`
Expected: PASS (3 testy)

- [ ] **Step 5: Commit**

```bash
git add backend/app/consolidation.py backend/tests/test_consolidation.py
git commit -m "feat(front): serwis wyliczen konsolidacji (fill_cbm, crd, can_add_order)"
```

---

### Task 3: Endpointy tylko-do-odczytu (koszyk + zamówienia kontenera)

**Files:**
- Create: `backend/app/routers/consolidation.py`
- Modify: `backend/app/main.py` (rejestracja routera)
- Test: `backend/tests/test_consolidation.py` (dopisać)

**Interfaces:**
- Consumes: `company_filter_ids(user)` z `app.deps`; `container_fill_cbm`, `container_crd` z `app.consolidation`; fixtury testowe `client`, `admin_headers` (jak w istniejących testach).
- Produces: `GET /api/purchase-orders?cart_status=<s>` → lista `{id, order_no, supplier, cbm, crd, cart_status, container_id}`; `GET /api/containers/{id}/orders` → `{orders:[...], fill_cbm, crd, capacity_cbm, consolidation_status}`.

- [ ] **Step 1: Write the failing test**

```python
# dopisz do backend/tests/test_consolidation.py — wykorzystaj istniejacy wzorzec logowania admina
def test_container_orders_endpoint(client, admin_headers):
    with SessionLocal() as db:
        co = db.scalar(select(Company).limit(1)) or Company(name="EP", code="EPCO")
        if not co.id:
            db.add(co); db.flush()
        cont = Container(container_no="EPCU0000001", company_id=co.id)
        db.add(cont); db.flush()
        db.add(PurchaseOrder(company_id=co.id, order_no="EP-A", container_id=cont.id,
                             cbm=12, cart_status=CartStatus.przypisane.value))
        db.commit()
        cid = cont.id
    r = client.get(f"/api/containers/{cid}/orders", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fill_cbm"] == 12.0
    assert float(body["capacity_cbm"]) == 70.0
    assert body["consolidation_status"] == "otwarty"
    assert len(body["orders"]) == 1 and body["orders"][0]["order_no"] == "EP-A"
```

Uwaga: `admin_headers` to istniejąca fixtura (patrz `tests/test_customs.py`). Jeśli test potrzebuje spójnej `Company` z kontem admina — użyj tego samego wzorca seedowania co `test_customs.py::_setup` (logowanie `admin_headers` operuje na spółce z konta).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_consolidation.py::test_container_orders_endpoint -v`
Expected: FAIL — 404 (endpoint nie istnieje)

- [ ] **Step 3: Implement router**

```python
# backend/app/routers/consolidation.py
"""Front-half (tylko odczyt): koszyk zamowien + zamowienia przypisane do kontenera
wraz z wyliczeniami konsolidacji. Mutacje (dodaj/usun/zwolnij) w kolejnym plastrze."""
import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..consolidation import container_crd, container_fill_cbm
from ..database import get_db
from ..deps import company_filter_ids
from ..models import Container, PurchaseOrder, User
from ..security import get_current_user

router = APIRouter(prefix="/api", tags=["consolidation"])


def _po_dict(po: PurchaseOrder) -> dict:
    return {"id": po.id, "order_no": po.order_no, "supplier": po.supplier,
            "cbm": float(po.cbm) if po.cbm is not None else None,
            "crd": po.crd, "cart_status": po.cart_status, "container_id": po.container_id}


@router.get("/purchase-orders")
def list_purchase_orders(cart_status: str | None = None,
                         db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)) -> list[dict]:
    q = select(PurchaseOrder)
    ids = company_filter_ids(user)
    if ids is not None:
        q = q.where(PurchaseOrder.company_id.in_(ids))
    if cart_status:
        q = q.where(PurchaseOrder.cart_status == cart_status)
    return [_po_dict(p) for p in db.scalars(q.order_by(PurchaseOrder.order_no)).all()]


@router.get("/containers/{container_id}/orders")
def container_orders(container_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> dict:
    cont = db.get(Container, container_id)
    ids = company_filter_ids(user)
    if cont is None or (ids is not None and cont.company_id not in ids):
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kontener nie istnieje.")
    orders = db.scalars(select(PurchaseOrder)
                        .where(PurchaseOrder.container_id == container_id)
                        .order_by(PurchaseOrder.order_no)).all()
    return {"orders": [_po_dict(p) for p in orders],
            "fill_cbm": container_fill_cbm(db, container_id),
            "crd": container_crd(db, container_id),
            "capacity_cbm": float(cont.capacity_cbm),
            "consolidation_status": cont.consolidation_status}
```

- [ ] **Step 4: Register router in main.py**

W `backend/app/main.py` dopisz import przy innych routerach (`from .routers import (...)`) oraz linię rejestracji obok pozostałych:

```python
app.include_router(consolidation.router)
```

(pamiętaj dodać `consolidation` do listy importów `from .routers import (...)`)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_consolidation.py::test_container_orders_endpoint -v`
Expected: PASS

- [ ] **Step 6: Run full new test file + a scope smoke**

Run: `cd backend && python -m pytest tests/test_consolidation.py tests/test_deps.py -q`
Expected: PASS (nowe + izolacja bez regresji)

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/consolidation.py backend/app/main.py backend/tests/test_consolidation.py
git commit -m "feat(front): endpointy odczytu koszyka i zamowien kontenera"
```

---

## Poza zakresem tego planu (kolejne plastry)
UI koszyka + przenoszenie zamówień; silnik auto-propozycji konsolidacji (≤70 CBM); CRD odchylenie/próg 10 dni/blokada→Kupiec/alerty; zapis do SAP z drift-detection.

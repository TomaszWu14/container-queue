# Obserwowanie PR 1 (kto / kiedy / dlaczego) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gwiazdka „Obserwuj" zapisuje kto/kiedy/dlaczego (kontener i statek), a karta kontenera i karta statku pokazują „Śledzone przez…".

**Architecture:** `WatchedContainer` dostaje `reason`/`created_at`, nowa tabela `WatchedVessel`. Nowy router `routers/watchers.py` (lista obserwujących + toggle statku) z jednym helperem filtrującym widoczność wg roli. Front: `WatchReasonDialog` (wybór powodu) + `WatchersPanel` (lista + przycisk) użyte w kolejce, karcie kontenera i karcie statku.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic (backend/), React 19 + Vite + vitest/testing-library (frontend/).

Spec: `docs/superpowers/specs/2026-09-24-obserwowanie-kto-dlaczego-design.md`.

## Global Constraints

- Max 500 linii na plik (`scripts/check_file_lengths.py`); plików z BASELINE nie wydłużać.
- Migracja od jedynej głowy alembica: **`dostalias001`** (sprawdź `cd backend && python -m alembic heads` przed startem — jeśli inna, użyj jej).
- Nowe teksty UI tylko w `frontend/src/i18n/features/obserwowanie.ts` (`defineFeature`), nie w `*.modules.ts`.
- Role wewnętrzne (widzą wszystkich obserwujących): `admin, logistics, purchasing`. Pozostałe (`warehouse, forwarder, customs`) widzą tylko własny wpis.
- Powód opcjonalny, max 200 znaków, przycinany (`strip`).
- Kontrakt `POST /api/containers/{id}/watch` → `{"watching": bool}` bez zmian; body opcjonalne.
- Izolacja: kontener przez `get_container_checked`, statek przez `get_vessel_visible` (poza zakresem → 404). Nie powielać reguł zakresu.
- Przed PR: `cd frontend && npm run build` (tsc -b) + pełne `npx vitest run` + backend pytest.
- Testy backendu uruchamiaj z `backend/`: `python -m pytest -q tests/<plik>`.

---

### Task 1: Model, migracja i powód przy gwiazdce kontenera

**Files:**
- Modify: `backend/app/models/tracking.py` (klasa `WatchedContainer`, nowa `WatchedVessel` pod nią)
- Create: `backend/migrations/versions/watch001_watch_reason.py`
- Modify: `backend/app/schemas/containers.py` (nowy `WatchIn` obok `SpecialIn`)
- Modify: `backend/app/routers/containers_changes.py:138-152` (`toggle_watch`)
- Test: `backend/tests/test_watch.py`

**Interfaces:**
- Produces: `WatchedContainer.reason: str`, `WatchedContainer.created_at: datetime | None`; `WatchedVessel(id, user_id, vessel_id, reason, created_at)`; `schemas.WatchIn(reason: str = "")`.

- [ ] **Step 1: Failing test** — dopisz do `backend/tests/test_watch.py`:

```python
def test_watch_saves_reason_and_date(client, db_session):
    from sqlalchemy import select
    from app.models import WatchedContainer
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    c = client.post("/api/containers", headers=headers, json={
        "container_no": "MSKU1234565", "company_id": company_id}).json()

    r = client.post(f"/api/containers/{c['id']}/watch", headers=headers,
                    json={"reason": "  Pilne dla klienta  "})
    assert r.json() == {"watching": True}
    row = db_session.scalar(select(WatchedContainer).where(
        WatchedContainer.container_id == c["id"]))
    assert row.reason == "Pilne dla klienta"
    assert row.created_at is not None


def test_watch_reason_too_long_rejected(client):
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    c = client.post("/api/containers", headers=headers, json={
        "container_no": "MSKU7654321", "company_id": company_id}).json()
    r = client.post(f"/api/containers/{c['id']}/watch", headers=headers,
                    json={"reason": "x" * 201})
    assert r.status_code == 422
```

(Jeśli `MSKU…` nie przechodzi walidacji cyfry kontrolnej, użyj numerów z innych testów, np. `TGBU6784203` / `MSDU0806613`.)

- [ ] **Step 2: Run** `cd backend && python -m pytest -q tests/test_watch.py` → FAIL (brak kolumny `reason`).

- [ ] **Step 3: Model** — w `backend/app/models/tracking.py` zamień `WatchedContainer` i dodaj `WatchedVessel`:

```python
class WatchedContainer(Base):
    """Gwiazdka „moje kontenery" — subskrypcja usera na kontener (+ kiedy i dlaczego)."""
    __tablename__ = "watched_containers"
    __table_args__ = (UniqueConstraint("user_id", "container_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"))
    reason: Mapped[str] = mapped_column(String(200), default="", server_default="")
    # NULL = obserwacja sprzed 2026-09-24 (brak daty)
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True, default=utcnow)


class WatchedVessel(Base):
    """Gwiazdka na statku (karta statku) — kto, kiedy, dlaczego."""
    __tablename__ = "watched_vessels"
    __table_args__ = (UniqueConstraint("user_id", "vessel_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    vessel_id: Mapped[int] = mapped_column(ForeignKey("tracked_vessels.id"), index=True)
    reason: Mapped[str] = mapped_column(String(200), default="", server_default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
```

`WatchedVessel` musi być eksportowany z `app.models` — `models/__init__.py` robi `from .tracking import *`; jeśli `tracking.py` ma `__all__`, dopisz tam `"WatchedVessel"`.

- [ ] **Step 4: Migracja** — `backend/migrations/versions/watch001_watch_reason.py`:

```python
"""Obserwowanie: powód + data przy gwiazdce kontenera, gwiazdka na statku (watched_vessels).

Revision ID: watch001
Revises: dostalias001
"""
import sqlalchemy as sa
from alembic import op

revision = "watch001"
down_revision = "dostalias001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("watched_containers") as batch:
        batch.add_column(sa.Column("reason", sa.String(200), nullable=False,
                                   server_default=sa.text("''")))
        batch.add_column(sa.Column("created_at", sa.DateTime, nullable=True))
    op.create_table(
        "watched_vessels",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("vessel_id", sa.Integer, sa.ForeignKey("tracked_vessels.id"), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("user_id", "vessel_id"),
    )
    op.create_index("ix_watched_vessels_user_id", "watched_vessels", ["user_id"])
    op.create_index("ix_watched_vessels_vessel_id", "watched_vessels", ["vessel_id"])


def downgrade() -> None:
    op.drop_table("watched_vessels")
    with op.batch_alter_table("watched_containers") as batch:
        batch.drop_column("created_at")
        batch.drop_column("reason")
```

- [ ] **Step 5: Schemat** — w `backend/app/schemas/containers.py` pod `SpecialIn` (sprawdź, czy `Field` jest zaimportowany z pydantic; jeśli nie — dodaj do importu):

```python
class WatchIn(BaseModel):
    """Gwiazdka „Obserwuj": opcjonalny powód (szybki powód albo własny tekst)."""
    reason: str = Field("", max_length=200)
```

Wyeksportuj `WatchIn` z `app.schemas` tak jak `SpecialIn` (sprawdź `schemas/__init__.py`).

- [ ] **Step 6: Toggle** — w `backend/app/routers/containers_changes.py` import `from ..schemas import SpecialIn, WatchIn` i zamień `toggle_watch`:

```python
@router.post("/containers/{container_id}/watch")
def toggle_watch(container_id: int, body: WatchIn | None = None,
                 db: Session = Depends(get_db), user: User = viewer):
    """Toggle gwiazdki — idempotentny (drugi POST zdejmuje obserwację).
    Body opcjonalne: przy dodaniu zapisuje powód; przy zdjęciu ignorowane."""
    from ..models import WatchedContainer
    get_container_checked(db, container_id, user)
    existing = db.scalar(select(WatchedContainer).where(
        WatchedContainer.user_id == user.id,
        WatchedContainer.container_id == container_id))
    if existing:
        db.delete(existing)
        watching = False
    else:
        db.add(WatchedContainer(user_id=user.id, container_id=container_id,
                                reason=(body.reason.strip() if body else ""),
                                created_at=utcnow()))
        watching = True
    db.commit()
    return {"watching": watching}
```

- [ ] **Step 7: Run** `python -m pytest -q tests/test_watch.py tests/test_watch_only_and_digest.py tests/test_migration_chain.py` → PASS; `python -m alembic heads` → tylko `watch001 (head)`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/tracking.py backend/migrations/versions/watch001_watch_reason.py backend/app/schemas backend/app/routers/containers_changes.py backend/tests/test_watch.py
git commit -m "feat(obserwowanie): powód i data gwiazdki kontenera, tabela watched_vessels"
```

---

### Task 2: API „Śledzone przez…" (kontener + statek) z filtrem ról

**Files:**
- Create: `backend/app/routers/watchers.py`
- Modify: `backend/app/main.py` (import w `from .routers import (...)` alfabetycznie + `app.include_router(watchers.router)` obok pozostałych)
- Test: `backend/tests/test_watchers.py`

**Interfaces:**
- Consumes: `WatchedContainer`, `WatchedVessel`, `WatchIn` (Task 1); `get_container_checked(db, id, user)` z `routers/containers_common.py`; `get_vessel_visible(db, id, user)` z `routers/tracking.py`.
- Produces (HTTP):
  - `GET /api/containers/{id}/watchers` → `{"watching": bool, "watchers": [{"user_id": int, "name": str, "reason": str, "created_at": str | null}]}`
  - `GET /api/tracking/vessels/{id}/watchers` → ten sam kształt
  - `POST /api/tracking/vessels/{id}/watch` body `{"reason"?: str}` → `{"watching": bool}`

- [ ] **Step 1: Failing tests** — `backend/tests/test_watchers.py`:

```python
"""„Śledzone przez…": lista obserwujących kontener/statek, filtr ról, izolacja statku."""
from app.database import SessionLocal
from app.models import Role, TrackedVessel, User
from app.security import hash_password
from tests.conftest import login


def _company_id(client, headers, code="ACME"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _user(login_name, role, company_id, full_name=""):
    with SessionLocal() as db:
        db.add(User(login=login_name, hashed_password=hash_password("pass12345"),
                    role=role, company_id=company_id, view_all_companies=False,
                    full_name=full_name, email=""))
        db.commit()


def _container(client, headers, no, company_id, vessel=""):
    r = client.post("/api/containers", headers=headers, json={
        "container_no": no, "company_id": company_id, "vessel": vessel})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_container_watchers_list_for_internal(client):
    admin = login(client)
    acme = _company_id(client, admin)
    cid = _container(client, admin, "TGBU6784203", acme)
    _user("logi1", Role.logistics, acme, full_name="Jan Kowalski")
    logi = login(client, "logi1", "pass12345")

    client.post(f"/api/containers/{cid}/watch", headers=admin, json={"reason": "Reklamacja"})
    client.post(f"/api/containers/{cid}/watch", headers=logi, json={})

    data = client.get(f"/api/containers/{cid}/watchers", headers=logi).json()
    assert data["watching"] is True
    assert [w["reason"] for w in data["watchers"]] == ["Reklamacja", ""]
    assert data["watchers"][1]["name"] == "Jan Kowalski"
    assert data["watchers"][0]["created_at"]


def test_external_role_sees_only_self(client):
    admin = login(client)
    acme = _company_id(client, admin)
    cid = _container(client, admin, "MSDU0806613", acme)
    _user("magazyn1", Role.warehouse, acme)
    wh = login(client, "magazyn1", "pass12345")
    client.post(f"/api/containers/{cid}/watch", headers=admin, json={"reason": "Pilne"})

    data = client.get(f"/api/containers/{cid}/watchers", headers=wh)
    if data.status_code == 404:      # magazyn bez dostępu do kontenera — też OK (izolacja)
        return
    assert data.json() == {"watching": False, "watchers": []}


def test_vessel_watch_toggle_and_scope(client, db_session):
    admin = login(client)
    acme = _company_id(client, admin)
    borealis = _company_id(client, admin, "BOREALIS")
    _container(client, admin, "TGBU6784203", borealis, vessel="MV OBSERWOWANA")
    vessel = TrackedVessel(name="MV OBSERWOWANA")
    db_session.add(vessel)
    db_session.commit()

    r = client.post(f"/api/tracking/vessels/{vessel.id}/watch", headers=admin,
                    json={"reason": "Ryzyko opóźnienia"})
    assert r.json() == {"watching": True}
    data = client.get(f"/api/tracking/vessels/{vessel.id}/watchers", headers=admin).json()
    assert data["watching"] is True
    assert data["watchers"][0]["reason"] == "Ryzyko opóźnienia"

    # user ACME nie ma ładunku na tym statku → 404 (get_vessel_visible)
    _user("logi2", Role.logistics, acme)
    logi = login(client, "logi2", "pass12345")
    assert client.get(f"/api/tracking/vessels/{vessel.id}/watchers",
                      headers=logi).status_code == 404
    assert client.post(f"/api/tracking/vessels/{vessel.id}/watch", headers=logi,
                       json={}).status_code == 404

    # drugi POST zdejmuje obserwację
    assert client.post(f"/api/tracking/vessels/{vessel.id}/watch", headers=admin,
                       json={}).json() == {"watching": False}
```

- [ ] **Step 2: Run** `python -m pytest -q tests/test_watchers.py` → FAIL (404 na `/watchers`).

- [ ] **Step 3: Router** — `backend/app/routers/watchers.py`:

```python
"""„Śledzone przez…": kto, kiedy i dlaczego obserwuje kontener / statek.

Widoczność jednym miejscem (`_watchers_out`): role wewnętrzne widzą wszystkich
obserwujących, pozostałe tylko własny wpis — nazwiska i powody pracowników nie
wychodzą do spedytora/agencji/magazynu. Zakres zasobu: get_container_checked /
get_vessel_visible (nie powielamy reguł izolacji)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import Viewer as viewer
from ..models import Role, User, WatchedContainer, WatchedVessel, utcnow
from ..schemas import WatchIn
from .containers_common import get_container_checked
from .tracking import get_vessel_visible

router = APIRouter(prefix="/api", tags=["obserwowanie"])

INTERNAL_ROLES = (Role.admin, Role.logistics, Role.purchasing)


def _watchers_out(db: Session, model, target_col, target_id: int, user: User) -> dict:
    rows = db.execute(
        select(model, User).join(User, User.id == model.user_id)
        .where(target_col == target_id)
        .order_by(model.created_at.asc().nulls_first(), model.id)).all()
    if user.role not in INTERNAL_ROLES:
        rows = [(w, u) for w, u in rows if u.id == user.id]
    return {
        "watching": any(u.id == user.id for _, u in rows),
        "watchers": [{"user_id": u.id, "name": u.full_name or u.login, "reason": w.reason,
                      "created_at": w.created_at.isoformat() if w.created_at else None}
                     for w, u in rows],
    }


@router.get("/containers/{container_id}/watchers")
def container_watchers(container_id: int, db: Session = Depends(get_db),
                       user: User = viewer):
    get_container_checked(db, container_id, user)
    return _watchers_out(db, WatchedContainer, WatchedContainer.container_id,
                         container_id, user)


@router.get("/tracking/vessels/{vessel_id}/watchers")
def vessel_watchers(vessel_id: int, db: Session = Depends(get_db), user: User = viewer):
    get_vessel_visible(db, vessel_id, user)
    return _watchers_out(db, WatchedVessel, WatchedVessel.vessel_id, vessel_id, user)


@router.post("/tracking/vessels/{vessel_id}/watch")
def toggle_vessel_watch(vessel_id: int, body: WatchIn | None = None,
                        db: Session = Depends(get_db), user: User = viewer):
    """Toggle gwiazdki statku — jak kontener: drugi POST zdejmuje obserwację."""
    get_vessel_visible(db, vessel_id, user)
    existing = db.scalar(select(WatchedVessel).where(
        WatchedVessel.user_id == user.id, WatchedVessel.vessel_id == vessel_id))
    if existing:
        db.delete(existing)
        watching = False
    else:
        db.add(WatchedVessel(user_id=user.id, vessel_id=vessel_id,
                             reason=(body.reason.strip() if body else ""),
                             created_at=utcnow()))
        watching = True
    db.commit()
    return {"watching": watching}
```

(Jeśli `Role`/`utcnow` nie są eksportowane z `app.models`, importuj jak w `containers_changes.py`: `from ..models import Container, User, utcnow` — `Role` z `..models`, co potwierdza `test_vessel_card.py`.)

- [ ] **Step 4: Rejestracja** — w `backend/app/main.py` dopisz `watchers,` w bloku `from .routers import (...)` (alfabetycznie) i `app.include_router(watchers.router)` po ostatnim `include_router` routerów API (przed ewentualnym montowaniem statycznego frontu / catch-all SPA — sprawdź, żeby nie znalazł się za trasą `/{path:path}`).

- [ ] **Step 5: Run** `python -m pytest -q tests/test_watchers.py tests/test_watch.py tests/test_vessel_card.py` → PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/watchers.py backend/app/main.py backend/tests/test_watchers.py
git commit -m "feat(obserwowanie): API „Śledzone przez…” dla kontenera i statku + gwiazdka statku"
```

---

### Task 3: Komponenty frontu — okienko powodu i panel „Śledzone przez…"

**Files:**
- Create: `frontend/src/i18n/features/obserwowanie.ts`
- Create: `frontend/src/pages/watch/WatchReasonDialog.tsx`
- Create: `frontend/src/pages/watch/WatchersPanel.tsx`
- Test: `frontend/src/pages/watch/watch.dom.test.tsx`

**Interfaces:**
- Consumes: `Modal` z `frontend/src/components.tsx` (`{title, onClose, children, width?, busy?}`); `api.get/post` z `frontend/src/api.ts`; `useT` z `frontend/src/i18n`; `formatDateTime` z `frontend/src/dates`.
- Produces:
  - `export default function WatchReasonDialog({ onConfirm, onClose }: { onConfirm: (reason: string) => void; onClose: () => void })`
  - `export default function WatchersPanel({ baseUrl, framed? }: { baseUrl: string; framed?: boolean })` — `baseUrl` np. `/api/containers/5` albo `/api/tracking/vessels/3`; panel sam woła `${baseUrl}/watchers` i `${baseUrl}/watch`.
  - `export interface WatchersResponse { watching: boolean; watchers: { user_id: number; name: string; reason: string; created_at: string | null }[] }`

- [ ] **Step 1: Teksty** — `frontend/src/i18n/features/obserwowanie.ts`:

```ts
// Obserwowanie (gwiazdka): powód przy dodaniu + „Śledzone przez…" (kontener, statek)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    watchReasonTitle: 'Dlaczego obserwujesz?',
    watchReasonUrgent: 'Pilne dla klienta',
    watchReasonDelay: 'Ryzyko opóźnienia',
    watchReasonSpecial: 'Towar specjalny',
    watchReasonComplaint: 'Reklamacja',
    watchReasonOther: 'Własny powód (opcjonalnie)',
    watchConfirm: 'Obserwuj',
    watchSkipReason: 'Pomiń powód',
    watchedBy: 'Śledzone przez',
    watchedByNobody: 'Nikt jeszcze nie obserwuje.',
  },
  en: {
    watchReasonTitle: 'Why are you watching?',
    watchReasonUrgent: 'Urgent for customer',
    watchReasonDelay: 'Delay risk',
    watchReasonSpecial: 'Special goods',
    watchReasonComplaint: 'Complaint',
    watchReasonOther: 'Own reason (optional)',
    watchConfirm: 'Watch',
    watchSkipReason: 'Skip reason',
    watchedBy: 'Watched by',
    watchedByNobody: 'Nobody is watching yet.',
  },
  pt: {
    watchReasonTitle: 'Porque está a observar?',
    watchReasonUrgent: 'Urgente para o cliente',
    watchReasonDelay: 'Risco de atraso',
    watchReasonSpecial: 'Mercadoria especial',
    watchReasonComplaint: 'Reclamação',
    watchReasonOther: 'Motivo próprio (opcional)',
    watchConfirm: 'Observar',
    watchSkipReason: 'Ignorar motivo',
    watchedBy: 'Observado por',
    watchedByNobody: 'Ainda ninguém está a observar.',
  },
})
```

Istniejące klucze `watchAdd`, `watchRemove`, `watchToggle` (plik `i18n/features/obserwowane.ts`) — reużyj, nie duplikuj.

- [ ] **Step 2: Failing test** — `frontend/src/pages/watch/watch.dom.test.tsx`:

```tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(() => Promise.resolve({ watching: true })),
}))
vi.mock('../../api', () => ({ api: { get: apiGet, post: apiPost } }))
vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../../dates', () => ({ formatDateTime: (s: string) => `D:${s}` }))

import WatchReasonDialog from './WatchReasonDialog'
import WatchersPanel from './WatchersPanel'

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('WatchReasonDialog', () => {
  it('szybki powód wypełnia pole i „Obserwuj" oddaje tekst', () => {
    const onConfirm = vi.fn()
    render(<WatchReasonDialog onConfirm={onConfirm} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'watchReasonDelay' }))
    fireEvent.click(screen.getByRole('button', { name: 'watchConfirm' }))
    expect(onConfirm).toHaveBeenCalledWith('watchReasonDelay')
  })

  it('„Pomiń powód" oddaje pusty powód', () => {
    const onConfirm = vi.fn()
    render(<WatchReasonDialog onConfirm={onConfirm} onClose={() => {}} />)
    fireEvent.change(screen.getByLabelText('watchReasonOther'), { target: { value: 'coś' } })
    fireEvent.click(screen.getByRole('button', { name: 'watchSkipReason' }))
    expect(onConfirm).toHaveBeenCalledWith('')
  })
})

describe('WatchersPanel', () => {
  it('pokazuje obserwujących z powodem i datą; dodanie idzie przez okienko powodu', async () => {
    apiGet.mockResolvedValueOnce({ watching: false, watchers: [
      { user_id: 1, name: 'Jan Kowalski', reason: 'Reklamacja', created_at: '2026-09-24T10:00:00' },
      { user_id: 2, name: 'Ala Nowak', reason: '', created_at: null },
    ] }).mockResolvedValue({ watching: true, watchers: [] })
    render(<WatchersPanel baseUrl="/api/containers/5" />)
    expect(await screen.findByText('Jan Kowalski')).toBeTruthy()
    expect(screen.getByText('Reklamacja')).toBeTruthy()
    expect(screen.getByText('D:2026-09-24T10:00:00')).toBeTruthy()
    expect(screen.getByText('JK')).toBeTruthy()          // inicjały

    fireEvent.click(screen.getByRole('button', { name: /watchAdd/ }))
    fireEvent.click(screen.getByRole('button', { name: 'watchReasonUrgent' }))
    fireEvent.click(screen.getByRole('button', { name: 'watchConfirm' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/containers/5/watch', { reason: 'watchReasonUrgent' }))
  })

  it('zdjęcie obserwacji bez okienka', async () => {
    apiGet.mockResolvedValue({ watching: true, watchers: [] })
    render(<WatchersPanel baseUrl="/api/tracking/vessels/3" />)
    fireEvent.click(await screen.findByRole('button', { name: /watchRemove/ }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/tracking/vessels/3/watch', {}))
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
```

Uwaga: `Modal` używa `useEscClose` — jeśli test wywali się na importach `components.tsx` (np. `useDicts`/`feedback`), dodaj `vi.mock('../../feedback', () => ({ useToast: () => ({ showToast: vi.fn() }) }))`.

- [ ] **Step 3: Run** `cd frontend && npx vitest run src/pages/watch` → FAIL (brak modułów).

- [ ] **Step 4: `WatchReasonDialog.tsx`**

```tsx
import { useState } from 'react'
import { Modal } from '../../components'
import { useT } from '../../i18n'

// klucze szybkich powodów — zapisujemy PRZETŁUMACZONY tekst (powód czyta człowiek)
const QUICK = ['watchReasonUrgent', 'watchReasonDelay', 'watchReasonSpecial', 'watchReasonComplaint']

/** Okienko przy dodaniu obserwacji: szybki powód albo własny tekst; można pominąć. */
export default function WatchReasonDialog({ onConfirm, onClose }: {
  onConfirm: (reason: string) => void
  onClose: () => void
}) {
  const t = useT()
  const [reason, setReason] = useState('')
  return (
    <Modal title={t('watchReasonTitle')} onClose={onClose} width={420}>
      <div className="watch-quick">
        {QUICK.map(k => (
          <button key={k} type="button"
                  className={`btn btn-sm${reason === t(k) ? ' active' : ''}`}
                  onClick={() => setReason(t(k))}>{t(k)}</button>
        ))}
      </div>
      <label className="field">
        <span>{t('watchReasonOther')}</span>
        <input aria-label={t('watchReasonOther')} value={reason} maxLength={200}
               onChange={e => setReason(e.target.value)} />
      </label>
      <div className="modal-actions">
        <button type="button" className="btn" onClick={() => onConfirm('')}>{t('watchSkipReason')}</button>
        <button type="button" className="btn primary" onClick={() => onConfirm(reason.trim())}>{t('watchConfirm')}</button>
      </div>
    </Modal>
  )
}
```

Klasy `btn`, `btn-sm`, `primary`, `field`, `modal-actions` — sprawdź w `frontend/src/styles/*.css`, czy istnieją pod tymi nazwami (`grep -rn "\.modal-actions\|\.btn-sm" frontend/src/styles`); użyj istniejących odpowiedników zamiast tworzyć nowe. Dodaj tylko `.watch-quick { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px }` do pliku CSS z komponentami formularzy (najkrótszego pasującego, pilnując limitu 500 linii).

- [ ] **Step 5: `WatchersPanel.tsx`**

```tsx
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api'
import { formatDateTime } from '../../dates'
import { useT } from '../../i18n'
import WatchReasonDialog from './WatchReasonDialog'

export interface WatchersResponse {
  watching: boolean
  watchers: { user_id: number; name: string; reason: string; created_at: string | null }[]
}

export const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]!.toUpperCase()).join('') || '?'

/** „Śledzone przez…" + gwiazdka dla kontenera/statku. baseUrl: /api/containers/5 | /api/tracking/vessels/3 */
export default function WatchersPanel({ baseUrl, framed = true }: { baseUrl: string; framed?: boolean }) {
  const t = useT()
  const [data, setData] = useState<WatchersResponse | null>(null)
  const [asking, setAsking] = useState(false)
  const load = useCallback(() => {
    api.get<WatchersResponse>(`${baseUrl}/watchers`).then(setData).catch(() => setData(null))
  }, [baseUrl])
  useEffect(load, [load])

  const toggle = (body: { reason?: string }) =>
    api.post<{ watching: boolean }>(`${baseUrl}/watch`, body).then(load).catch(() => {})

  if (!data) return null
  return (
    <div className={framed ? 'panel watchers-panel' : 'watchers-panel'}>
      <div className="watchers-head">
        <h3>{t('watchedBy')}</h3>
        <button type="button" className={`watch-star${data.watching ? ' on' : ''}`}
                onClick={() => data.watching ? toggle({}) : setAsking(true)}>
          {data.watching ? `★ ${t('watchRemove')}` : `☆ ${t('watchAdd')}`}
        </button>
      </div>
      {data.watchers.length === 0
        ? <p className="muted">{t('watchedByNobody')}</p>
        : (
          <ul className="watchers-list">
            {data.watchers.map(w => (
              <li key={w.user_id}>
                <span className="avatar-initials" aria-hidden>{initials(w.name)}</span>
                <span className="watcher-name">{w.name}</span>
                <span className="muted">{w.created_at ? formatDateTime(w.created_at) : '—'}</span>
                {w.reason && <span className="watcher-reason">{w.reason}</span>}
              </li>
            ))}
          </ul>
        )}
      {asking && (
        <WatchReasonDialog onClose={() => setAsking(false)}
                           onConfirm={reason => { setAsking(false); toggle({ reason }) }} />
      )}
    </div>
  )
}
```

Uwaga do testu: przy pustym powodzie body to `{ reason: '' }`; test „zdjęcie obserwacji" oczekuje `{}` — zgodne, bo zdjęcie woła `toggle({})`.
CSS: `.watchers-head {display:flex;justify-content:space-between;align-items:center}`, `.watchers-list {list-style:none;margin:0;padding:0;display:grid;gap:6px}`, `.watchers-list li {display:flex;gap:8px;align-items:center;flex-wrap:wrap}`, `.avatar-initials {width:24px;height:24px;border-radius:50%;display:inline-grid;place-items:center;font-size:11px;font-weight:600;background:var(--accent-soft, #e3e8ef)}`, `.watcher-reason {font-size:12px;opacity:.85}` — użyj istniejących tokenów `var(--…)` z `frontend/src/styles`, nie kolorów na sztywno, jeśli pasujący token istnieje.

- [ ] **Step 6: Run** `npx vitest run src/pages/watch src/i18n.features.test.ts` → PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/i18n/features/obserwowanie.ts frontend/src/pages/watch frontend/src/styles
git commit -m "feat(obserwowanie): okienko powodu i panel „Śledzone przez…”"
```

---

### Task 4: Podpięcie w kolejce, karcie kontenera i karcie statku

**Files:**
- Modify: `frontend/src/pages/queue/useViewPrefs.ts:109-121` (toggleWatch → pytanie o powód)
- Modify: `frontend/src/pages/queue/TileMenus.tsx` (render okienka)
- Modify: `frontend/src/pages/QueuePage.tsx:462-463` (jedna dodatkowa właściwość w tej samej linii — plik nie może urosnąć ponad baseline/500)
- Modify: `frontend/src/pages/ContainerPage.tsx` (aside `card-side`)
- Modify: `frontend/src/pages/tracking/VesselCard.tsx` (sekcja pod siatką parametrów)
- Modify: `frontend/src/pages/tracking/VesselCard.dom.test.tsx` (mock `api.get` rozróżnia URL)
- Modify: `frontend/src/pages/queue/TileMenus.dom.test.tsx` (nowa właściwość w Harness)

**Interfaces:**
- Consumes: `WatchReasonDialog`, `WatchersPanel` (Task 3).
- Produces: `useViewPrefs()` zwraca dodatkowo `watchPrompt: number | null`, `confirmWatch: (reason: string) => void`, `cancelWatch: () => void`; `toggleWatch(id)` przy DODANIU ustawia `watchPrompt = id` zamiast od razu POST-ować.

- [ ] **Step 1: Failing test** — w `TileMenus.dom.test.tsx` dopisz przypadek (dostosuj Harness: nowe propsy `watchPrompt`, `confirmWatch`, `cancelWatch`):

```tsx
it('okienko powodu gdy watchPrompt ustawiony — Obserwuj przekazuje powód', () => {
  const confirmWatch = vi.fn()
  render(<Harness watched={new Set()} toggleWatch={() => {}} replace={() => {}}
                  watchPrompt={3} confirmWatch={confirmWatch} cancelWatch={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: 'watchReasonComplaint' }))
  fireEvent.click(screen.getByRole('button', { name: 'watchConfirm' }))
  expect(confirmWatch).toHaveBeenCalledWith('watchReasonComplaint')
})
```

(W Harness przekaż nowe propsy do `<TileMenus …>`; domyślnie `watchPrompt={null}`. Jeśli test mockuje `useT` inaczej niż `key => key`, dopasuj oczekiwaną nazwę przycisku.)

- [ ] **Step 2: Run** `npx vitest run src/pages/queue/TileMenus.dom.test.tsx` → FAIL.

- [ ] **Step 3: `useViewPrefs.ts`** — zastąp blok `toggleWatch`:

```ts
  // dodanie gwiazdki pyta o powód (WatchReasonDialog w TileMenus); zdjęcie — od razu
  const [watchPrompt, setWatchPrompt] = useState<number | null>(null)
  const postWatch = (id: number, body: { reason?: string }) => {
    api.post<{ watching: boolean }>(`/api/containers/${id}/watch`, body)
      .then(r => setWatched(prev => {
        const next = new Set(prev)
        if (r.watching) next.add(id); else next.delete(id)
        return next
      })).catch(() => {})
  }
  const toggleWatch = (id: number) => {
    if (watched.has(id)) postWatch(id, {}); else setWatchPrompt(id)
  }
  const confirmWatch = (reason: string) => {
    if (watchPrompt !== null) postWatch(watchPrompt, { reason })
    setWatchPrompt(null)
  }
  const cancelWatch = () => setWatchPrompt(null)
```

i dopisz `watchPrompt, confirmWatch, cancelWatch` do zwracanego obiektu (w linii z `watched, toggleWatch,`).

- [ ] **Step 4: `TileMenus.tsx`** — rozszerz propsy i wyrenderuj okienko na końcu zwracanego fragmentu:

```tsx
// w sygnaturze: ..., watched, toggleWatch, watchPrompt, confirmWatch, cancelWatch }: {
//   ...
  watchPrompt: number | null
  confirmWatch: (reason: string) => void
  cancelWatch: () => void
// na końcu JSX (przed zamknięciem fragmentu):
      {watchPrompt !== null && <WatchReasonDialog onConfirm={confirmWatch} onClose={cancelWatch} />}
```

oraz `import WatchReasonDialog from '../watch/WatchReasonDialog'`.

- [ ] **Step 5: `QueuePage.tsx`** — zmień TYLKO linię 463 (bez dodawania linii):

```tsx
                 watched={prefs.watched} toggleWatch={prefs.toggleWatch} watchPrompt={prefs.watchPrompt} confirmWatch={prefs.confirmWatch} cancelWatch={prefs.cancelWatch} />
```

- [ ] **Step 6: `ContainerPage.tsx`** — w `<aside className="card-side">` przed `<MessagesPanel …>`:

```tsx
          <WatchersPanel baseUrl={`/api/containers/${container.id}`} />
```

+ `import WatchersPanel from './watch/WatchersPanel'`. (ContainerPage ma 439 linii — zostaje < 500.)

- [ ] **Step 7: `VesselCard.tsx`** — pod zamknięciem `<div className="vc-grid">…</div>` (siatka parametrów) wstaw:

```tsx
      <WatchersPanel baseUrl={`/api/tracking/vessels/${vessel.id}`} framed={false} />
```

+ `import WatchersPanel from '../watch/WatchersPanel'`.

- [ ] **Step 8: `VesselCard.dom.test.tsx`** — mock `apiGet` zwraca `cargo` dla każdego URL; zmień na rozróżnienie:

```tsx
  apiGet: vi.fn((url: string) => Promise.resolve(
    url.endsWith('/watchers') ? { watching: false, watchers: [] } : cargo)),
```

i sprawdź asercje liczące wywołania `apiGet` (np. `toHaveBeenCalledTimes(1)`) — jeśli liczą wszystkie GET-y, zawęź je do URL-a `/cargo` (`expect(apiGet).toHaveBeenCalledWith(expect.stringContaining('/cargo'))`).

- [ ] **Step 9: Run** `npx vitest run` (całość) → PASS; `npm run build` → bez błędów; `cd .. && python scripts/check_file_lengths.py` → rc 0.

- [ ] **Step 10: Commit**

```bash
git add frontend/src
git commit -m "feat(obserwowanie): powód przy gwiazdce w kolejce, „Śledzone przez…” w karcie kontenera i statku"
```

---

### Task 5: Weryfikacja całości i PR

- [ ] **Step 1:** `cd backend && python -m pytest -q` (pełny zestaw, jeden pytest na worktree) → wszystkie PASS; pokaż podsumowanie.
- [ ] **Step 2:** `cd frontend && npx vitest run && npm run build` → PASS.
- [ ] **Step 3:** `python scripts/check_file_lengths.py` → rc 0; `cd backend && python -m alembic heads` → jedna głowa `watch001`.
- [ ] **Step 4:** Push gałęzi `claude/obserwowanie-kto-dlaczego` i `gh pr create` (tytuł: „feat(obserwowanie): kto, kiedy i dlaczego obserwuje kontener/statek”; opis: zakres PR 1 ze specu, lista testów, uwaga o migracji `watch001`, stopka z Generated with Claude Code).

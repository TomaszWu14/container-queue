# Zlecenia spedycyjne — Plaster 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać osobny widok „kolejka do zlecenia" (kontenery wymagające wystawienia zlecenia spedycyjnego), karmiący istniejący pipeline `TransportJob` — bez nowej encji.

**Architecture:** Reużycie `TransportJob`/`QuoteRequestModal`. Nowe: kolumna `Container.needs_forwarding`, endpoint listy `GET /containers/to-forward`, endpoint flagi `PATCH /containers/{id}/needs-forwarding`, strona `ForwardingRequestsPage` na route `/zlecenia-spedycyjne`.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), React/TS + Vite + Vitest (frontend). Testy: pytest (backend), @testing-library/react (frontend).

## Global Constraints

- Scoping danych: TYLKO przez `deps.py` (`scope_containers`, `check_container_access`) — nie powielać reguł w routerze.
- Role: tworzenie/flaga = `editors` (admin/logistics). Front route pod `Guarded ok={role admin||logistics}`.
- Daty w UI: `formatDate` (dd.mm.rrrr). Ciche błędy zabronione — `setError`/`LoadError`/toast.
- Migracja: `down_revision = 'c9d0e1f2a3b4'` (aktualny head). Produkcja: `alembic upgrade head`.
- Testy frontendu: `npx vitest run` w `frontend/`. Backend: `pytest` w `backend/` (venv `.venv`).

---

### Task 1: Backend — kolumna `Container.needs_forwarding` + migracja

**Files:**
- Modify: `backend/app/models.py` (klasa `Container`, ~336)
- Create: `backend/migrations/versions/a1b2c3d4e5f6_needs_forwarding.py`
- Test: `backend/tests/test_forwarding_queue.py`

**Interfaces:**
- Produces: `Container.needs_forwarding: bool` (default False)

- [ ] **Step 1: Dodaj kolumnę do modelu**

W `backend/app/models.py`, w klasie `Container` (obok innych `Mapped` pól, np. po `forwarder_id`):

```python
    needs_forwarding: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
```

Na górze pliku upewnij się, że jest import `Boolean` (jest) i dodaj alias dla domyślnej:
```python
from sqlalchemy import false as sa_false
```
(jeśli `false` już importowany pod inną nazwą — użyj istniejącej.)

- [ ] **Step 2: Utwórz migrację**

`backend/migrations/versions/a1b2c3d4e5f6_needs_forwarding.py`:

```python
"""container needs_forwarding flag

Revision ID: a1b2c3d4e5f6
Revises: c9d0e1f2a3b4
Create Date: 2026-09-06 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('containers', sa.Column(
        'needs_forwarding', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('containers', 'needs_forwarding')
```

- [ ] **Step 3: Napisz test bazowy (default False)**

`backend/tests/test_forwarding_queue.py` — nagłówek + pierwszy test. Wzoruj `_setup` na `test_driver_link.py` (tworzenie kontenera przez API).

```python
"""Kolejka 'do zlecenia' + flaga needs_forwarding."""
from app.database import SessionLocal
from app.models import Container

VALID_NO = "MSDU0806613"


def _make_container(client, admin_headers, no=VALID_NO, forwarder_id=None):
    companies = client.get("/api/companies", headers=admin_headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    body = {"container_no": no, "company_id": borealis}
    if forwarder_id:
        body["forwarder_id"] = forwarder_id
    return client.post("/api/containers", headers=admin_headers, json=body).json()


def test_needs_forwarding_defaults_false(client, admin_headers):
    c = _make_container(client, admin_headers)
    with SessionLocal() as db:
        row = db.get(Container, c["id"])
        assert row.needs_forwarding is False
```

- [ ] **Step 4: Uruchom migrację testowej bazy i test**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_forwarding_queue.py -q`
Expected: PASS (conftest tworzy schemat z modeli; kolumna obecna).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/migrations/versions/a1b2c3d4e5f6_needs_forwarding.py backend/tests/test_forwarding_queue.py
git commit -m "feat(forwarding): kolumna Container.needs_forwarding + migracja"
```

---

### Task 2: Backend — `GET /containers/to-forward`

**Files:**
- Modify: `backend/app/routers/containers.py`
- Test: `backend/tests/test_forwarding_queue.py`

**Interfaces:**
- Consumes: `Container.needs_forwarding`, `TransportJob`, `TransportJobContainer`, `TransportJobStatus`, `scope_containers`, `to_out`, `editors`
- Produces: `GET /api/containers/to-forward` → `list[ContainerOut]`

- [ ] **Step 1: Test reguły kolejki**

Dopisz do `test_forwarding_queue.py`:

```python
def _to_forward_nos(client, headers):
    r = client.get("/api/containers/to-forward", headers=headers)
    assert r.status_code == 200, r.text
    return {c["container_no"] for c in r.json()}


def test_to_forward_rule(client, admin_headers):
    # bez spedytora → w kolejce
    a = _make_container(client, admin_headers, no="MSDU0806613")
    assert "MSDU0806613" in _to_forward_nos(client, admin_headers)

    # z przypisanym spedytorem → znika (chyba że flaga)
    fwds = client.get("/api/forwarders", headers=admin_headers).json()
    fid = fwds[0]["id"]
    client.patch(f"/api/containers/{a['id']}", headers=admin_headers,
                 json={"forwarder_id": fid})
    assert "MSDU0806613" not in _to_forward_nos(client, admin_headers)

    # flaga needs_forwarding zwraca go mimo spedytora
    client.patch(f"/api/containers/{a['id']}/needs-forwarding", headers=admin_headers,
                 json={"value": True})
    assert "MSDU0806613" in _to_forward_nos(client, admin_headers)

    # w aktywnym TransportJob (SZKIC) → znika
    client.post("/api/transport-jobs", headers=admin_headers,
                json={"container_ids": [a["id"]], "forwarder_ids": [fid]})
    assert "MSDU0806613" not in _to_forward_nos(client, admin_headers)
```

- [ ] **Step 2: Uruchom — ma FAIL (404 na to-forward)**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_forwarding_queue.py::test_to_forward_rule -q`
Expected: FAIL (endpoint nie istnieje / 405/404).

- [ ] **Step 3: Dodaj endpoint**

W `backend/app/routers/containers.py`. Import (dołóż do istniejących importów z `..models`):
```python
from ..models import TransportJob, TransportJobContainer, TransportJobStatus
```
i `or_` z sqlalchemy (jeśli brak): `from sqlalchemy import or_`.

Endpoint (obok innych `@router.get("/containers...")`):
```python
_ACTIVE_JOB = (TransportJobStatus.SZKIC, TransportJobStatus.WYSLANE)


@router.get("/containers/to-forward", response_model=list[ContainerOut])
def containers_to_forward(db: Session = Depends(get_db), user: User = editors):
    # kontenery uwięzione w aktywnym zleceniu (SZKIC/WYSLANE) — wykluczamy
    busy = (select(TransportJobContainer.container_id)
            .join(TransportJob, TransportJob.id == TransportJobContainer.job_id)
            .where(TransportJob.status.in_(_ACTIVE_JOB)))
    query = (select(Container).options(*_LOAD)
             .where(Container.status.not_in(Container.FINISHED),
                    Container.id.not_in(busy),
                    or_(Container.needs_forwarding.is_(True),
                        Container.forwarder_id.is_(None)))
             .order_by(Container.notify_date.asc().nulls_last(), Container.id))
    query = scope_containers(query, user)
    return [to_out(c, user) for c in db.scalars(query).all()]
```

**Uwaga kolejności tras:** umieść PRZED ewentualną trasą `/containers/{container_id}`, żeby „to-forward" nie zostało złapane jako `container_id`.

- [ ] **Step 4: Uruchom — PASS**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_forwarding_queue.py -q`
Expected: PASS (wymaga też Task 3 dla PATCH — jeśli PATCH jeszcze nie ma, ten krok rób po Task 3 albo tymczasowo zakomentuj asercje flagi).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/containers.py backend/tests/test_forwarding_queue.py
git commit -m "feat(forwarding): GET /containers/to-forward — kolejka do zlecenia"
```

---

### Task 3: Backend — `PATCH /containers/{id}/needs-forwarding`

**Files:**
- Modify: `backend/app/routers/containers.py`, `backend/app/schemas.py`
- Test: `backend/tests/test_forwarding_queue.py`

**Interfaces:**
- Produces: `PATCH /api/containers/{id}/needs-forwarding` body `{value: bool}` → `ContainerOut`

- [ ] **Step 1: Test przełączania flagi + scoping**

```python
def test_needs_forwarding_toggle(client, admin_headers):
    c = _make_container(client, admin_headers, no="TCLU1234567")
    r = client.patch(f"/api/containers/{c['id']}/needs-forwarding",
                     headers=admin_headers, json={"value": True})
    assert r.status_code == 200 and r.json()["needs_forwarding"] is True
    r = client.patch(f"/api/containers/{c['id']}/needs-forwarding",
                     headers=admin_headers, json={"value": False})
    assert r.json()["needs_forwarding"] is False
```

- [ ] **Step 2: Uruchom — FAIL**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_forwarding_queue.py::test_needs_forwarding_toggle -q`
Expected: FAIL (404/405).

- [ ] **Step 3: Schema + endpoint**

`backend/app/schemas.py` (obok innych `BaseModel`):
```python
class NeedsForwardingIn(BaseModel):
    value: bool
```
Import w `containers.py` (dołóż do listy z `..schemas`): `NeedsForwardingIn`.

Endpoint w `containers.py`:
```python
@router.patch("/containers/{container_id}/needs-forwarding", response_model=ContainerOut)
def set_needs_forwarding(container_id: int, body: NeedsForwardingIn,
                         db: Session = Depends(get_db), user: User = editors):
    container = db.get(Container, container_id)
    if not container:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kontener nie istnieje.")
    check_container_access(user, container)
    container.needs_forwarding = body.value
    db.commit()
    db.refresh(container)
    return to_out(container, user)
```

Upewnij się, że `ContainerOut` ma pole `needs_forwarding` — jeśli `ContainerOut` ma `model_config = ConfigDict(from_attributes=True)` bez jawnej listy pól, dodaj `needs_forwarding: bool = False` do `ContainerOut` w `schemas.py`.

- [ ] **Step 4: Uruchom cały plik — PASS**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_forwarding_queue.py -q`
Expected: PASS (wszystkie testy Task 1-3).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/containers.py backend/app/schemas.py backend/tests/test_forwarding_queue.py
git commit -m "feat(forwarding): PATCH needs-forwarding + needs_forwarding w ContainerOut"
```

---

### Task 4: Frontend — typ, i18n, route/link, szkielet strony

**Files:**
- Modify: `frontend/src/types.ts`, `frontend/src/i18n.ts`, `frontend/src/App.tsx`
- Create: `frontend/src/pages/ForwardingRequestsPage.tsx`

**Interfaces:**
- Produces: route `/zlecenia-spedycyjne`, komponent `ForwardingRequestsPage` (default export)

- [ ] **Step 1: Typ + i18n**

`types.ts` — w interfejsie `Container` dodaj: `needs_forwarding: boolean`.

`i18n.ts` — w każdym słowniku (pl/en/pt) dodaj klucze (wartości PL przykładowo):
```
fwqTitle: 'Zlecenia spedycyjne', fwqToForward: 'Do zlecenia',
fwqCreate: 'Utwórz zlecenie z zaznaczonych', fwqFlagOn: 'Oznacz „do zlecenia"',
fwqFlagOff: 'Zdejmij „do zlecenia"', fwqEmpty: 'Brak kontenerów do zlecenia',
```

- [ ] **Step 2: Szkielet strony (loader + pusta lista)**

`frontend/src/pages/ForwardingRequestsPage.tsx`:
```tsx
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { formatDate } from '../dates'
import { LoadError, Skeleton } from '../feedback'
import type { Container } from '../types'

export default function ForwardingRequestsPage() {
  const t = useT()
  const navigate = useNavigate()
  const [rows, setRows] = useState<Container[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  const load = useCallback(() => {
    setLoading(true); setLoadError('')
    api.get<Container[]>('/api/containers/to-forward')
      .then(setRows)
      .catch(err => setLoadError(errorMessage(err)))
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => load(), [load])

  if (loading && rows.length === 0) return <main className="page"><Skeleton rows={6} /></main>
  if (loadError && rows.length === 0)
    return <main className="page"><LoadError message={loadError} onRetry={load} /></main>

  return (
    <main className="page">
      <h2 style={{ marginTop: 0, fontSize: '1.2rem' }}>{t('fwqTitle')}</h2>
      {rows.length === 0 && <p style={{ color: 'var(--muted)' }}>{t('fwqEmpty')}</p>}
      {/* tabela + akcje w Task 5-6 */}
    </main>
  )
}
```

- [ ] **Step 3: Route + link w menu Logistyka**

`App.tsx`: import `import ForwardingRequestsPage from './pages/ForwardingRequestsPage'`.
W tablicy `sections`, sekcja `Logistyka.links`, dodaj po `spedycja`:
```tsx
      { to: '/zlecenia-spedycyjne', icon: 'forwarding', label: t('fwqTitle'), show: some('admin', 'logistics') },
```
W `<Routes>` (blok uwierzytelniony) dodaj:
```tsx
              <Route path="/zlecenia-spedycyjne" element={
                <Guarded ok={user.role === 'admin' || user.role === 'logistics'}>
                  <ForwardingRequestsPage /></Guarded>} />
```

- [ ] **Step 4: Typecheck + build myśli**

Run: `cd frontend && npx tsc --noEmit`
Expected: brak błędów.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/i18n.ts frontend/src/App.tsx frontend/src/pages/ForwardingRequestsPage.tsx
git commit -m "feat(forwarding): route /zlecenia-spedycyjne + szkielet strony"
```

---

### Task 5: Frontend — tabela kolejki + toggle flagi

**Files:**
- Modify: `frontend/src/pages/ForwardingRequestsPage.tsx`
- Test: `frontend/src/forwarding-queue.dom.test.tsx`

**Interfaces:**
- Consumes: `GET /containers/to-forward`, `PATCH /containers/{id}/needs-forwarding`

- [ ] **Step 1: Test DOM — render + toggle**

`frontend/src/forwarding-queue.dom.test.tsx`:
```tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('./i18n', () => ({ useT: () => (k: string) => k }))
const { apiGet, apiPatch } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPatch: vi.fn() }))
vi.mock('./api', () => ({ api: { get: apiGet, patch: apiPatch }, errorMessage: (e: unknown) => String(e) }))
vi.mock('./dates', () => ({ formatDate: (s: string) => s }))

import ForwardingRequestsPage from './pages/ForwardingRequestsPage'
afterEach(() => { cleanup(); apiGet.mockReset(); apiPatch.mockReset() })

const rows = [{ id: 1, container_no: 'MSDU1', warehouse_name: 'DLT', eta: '2026-07-08',
  notify_date: null, port_name: 'MUMBAI', needs_forwarding: false }]

it('renderuje kolejkę i przełącza flagę', async () => {
  apiGet.mockResolvedValue(rows)
  apiPatch.mockResolvedValue({ ...rows[0], needs_forwarding: true })
  render(<MemoryRouter><ForwardingRequestsPage /></MemoryRouter>)
  await waitFor(() => expect(screen.getByText('MSDU1')).toBeTruthy())
  fireEvent.click(screen.getByTitle('fwqFlagOn'))
  await waitFor(() => expect(apiPatch).toHaveBeenCalledWith(
    '/api/containers/1/needs-forwarding', { value: true }))
})
```

- [ ] **Step 2: Uruchom — FAIL**

Run: `cd frontend && npx vitest run src/forwarding-queue.dom.test.tsx`
Expected: FAIL (brak tabeli/przycisku).

- [ ] **Step 3: Dodaj tabelę + toggle w komponencie**

Zamień komentarz `{/* tabela ... */}` na:
```tsx
      {rows.length > 0 && (
        <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="grid">
            <thead>
              <tr>
                <th>{t('containerNo')}</th><th>{t('port')}</th><th>{t('warehouse')}</th>
                <th>{t('eta')}</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(c => (
                <tr key={c.id}>
                  <td className="mono">
                    <a className="order-link" onClick={() => navigate(`/kontenery/${c.id}`)}>
                      {c.container_no}
                    </a>
                  </td>
                  <td>{c.port_name}</td>
                  <td>{c.warehouse_name}</td>
                  <td>{formatDate(c.eta)}</td>
                  <td>
                    <button className="btn small secondary"
                            title={c.needs_forwarding ? t('fwqFlagOff') : t('fwqFlagOn')}
                            onClick={() => toggleFlag(c)}>
                      {c.needs_forwarding ? '★' : '☆'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
```
Dodaj handler (nad `return`):
```tsx
  const [error, setError] = useState('')
  const toggleFlag = async (c: Container) => {
    try {
      await api.patch(`/api/containers/${c.id}/needs-forwarding`, { value: !c.needs_forwarding })
      load()
    } catch (err) { setError(errorMessage(err)) }
  }
```
i pod `<h2>`: `{error && <p className="error">{error}</p>}`.

- [ ] **Step 4: Uruchom — PASS**

Run: `cd frontend && npx vitest run src/forwarding-queue.dom.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ForwardingRequestsPage.tsx frontend/src/forwarding-queue.dom.test.tsx
git commit -m "feat(forwarding): tabela kolejki do zlecenia + toggle flagi"
```

---

### Task 6: Frontend — multi-select + reużycie `QuoteRequestModal`

**Files:**
- Modify: `frontend/src/pages/ForwardingRequestsPage.tsx`, `frontend/src/forwarding-queue.dom.test.tsx`

**Interfaces:**
- Consumes: `QuoteRequestModal({ containers, forwarders, onDone, onClose })`, `GET /api/forwarders`

- [ ] **Step 1: Test — zaznacz + „Utwórz zlecenie" otwiera modal**

Dopisz do testu (mock forwarders + modal). Zamockuj `QuoteRequestModal`, by nie renderować pełnego:
```tsx
vi.mock('./pages/QuoteRequestModal', () => ({ default: () => <div>MODAL</div> }))
```
Test:
```tsx
it('zaznaczenie + Utwórz zlecenie otwiera modal', async () => {
  apiGet.mockImplementation((path: string) =>
    Promise.resolve(path.includes('forwarders') ? [{ id: 9, name: 'SPEDALFA' }] : rows))
  render(<MemoryRouter><ForwardingRequestsPage /></MemoryRouter>)
  await waitFor(() => expect(screen.getByText('MSDU1')).toBeTruthy())
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByText('fwqCreate'))
  expect(screen.getByText('MODAL')).toBeTruthy()
})
```

- [ ] **Step 2: Uruchom — FAIL**

Run: `cd frontend && npx vitest run src/forwarding-queue.dom.test.tsx`
Expected: FAIL (brak checkboxa/przycisku/modala).

- [ ] **Step 3: Dodaj multi-select + modal**

W komponencie:
```tsx
import QuoteRequestModal from './QuoteRequestModal'
import type { Named } from '../types'
```
Stan:
```tsx
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [forwarders, setForwarders] = useState<Named[]>([])
  const [showCreate, setShowCreate] = useState(false)
  useEffect(() => { api.get<Named[]>('/api/forwarders').then(setForwarders).catch(() => {}) }, [])
  const toggleSel = (id: number) => setSelected(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n
  })
```
W nagłówku (obok `<h2>`), pasek akcji:
```tsx
      {selected.size > 0 && (
        <button className="btn" onClick={() => setShowCreate(true)}>
          {t('fwqCreate')} ({selected.size})
        </button>
      )}
```
Kolumna checkboxa w `<thead>` (pierwsza): `<th></th>`, w wierszu (pierwsza `<td>`):
```tsx
                  <td><input type="checkbox" checked={selected.has(c.id)}
                             onChange={() => toggleSel(c.id)} /></td>
```
Modal na końcu `<main>`:
```tsx
      {showCreate && (
        <QuoteRequestModal
          containers={rows.filter(c => selected.has(c.id))}
          forwarders={forwarders}
          onDone={() => { setShowCreate(false); setSelected(new Set()); load() }}
          onClose={() => setShowCreate(false)}
        />
      )}
```

- [ ] **Step 4: Uruchom cały plik + pełny suite**

Run: `cd frontend && npx vitest run src/forwarding-queue.dom.test.tsx && npx vitest run && npx tsc --noEmit`
Expected: PASS + tsc czysto.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ForwardingRequestsPage.tsx frontend/src/forwarding-queue.dom.test.tsx
git commit -m "feat(forwarding): multi-select -> reuzycie QuoteRequestModal (utworz zlecenie)"
```

---

## Self-Review

- **Spec coverage:** kolumna+migracja (T1), reguła kolejki `to-forward` (T2), flaga PATCH (T3), route/panel (T4), tabela+toggle (T5), multi-select+reużycie modala (T6). Poza plastrem świadomie: RFQ/oferty/wystawienie (istnieje), e-mail-ścieżka, PDF. ✔
- **Placeholdery:** brak — każdy krok ma kod/komendę.
- **Typy spójne:** `needs_forwarding: boolean` (types.ts) ↔ `ContainerOut.needs_forwarding` (schemas) ↔ model. `QuoteRequestModal` props zgodne z definicją (`containers, forwarders, onDone, onClose`).
- **Ryzyko:** kolejność tras `/containers/to-forward` przed `/containers/{id}` (zaznaczone w T2). `ContainerOut` musi eksponować `needs_forwarding` (T3 step 3). `port_name`/`warehouse_name`/`eta` — pola już są w `ContainerOut` (używane w kolejce); jeśli `port_name` brak, użyj `port?.name` wg realnego schematu (sprawdzić przy T5).

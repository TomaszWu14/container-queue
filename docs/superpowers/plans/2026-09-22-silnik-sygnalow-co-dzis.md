# Silnik sygnałów + lista „Co dziś" (v1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zamienić trzy osobne listy dashboardu w jedną posortowaną listę działań „Co dziś", zasilaną wspólnym silnikiem sygnałów.

**Architecture:** Pure moduł `backend/app/signals.py` liczy sygnały z listy kontenerów (bez DB); istniejący `/api/stats/dashboard` dokleja pole `action_feed`; `DashboardPage.tsx` renderuje jedną listę z `action_feed` zamiast filtrować `delayed_list`.

**Tech Stack:** FastAPI + SQLAlchemy (backend), pytest; React + TypeScript + Vite (frontend), vitest.

## Global Constraints

- Backend testy uruchamiać z `cd backend && python -m pytest` (SQLite in-memory przez conftest; create_all buduje schemat — brak migracji dla tego featu).
- Izolacja danych: feed dziedziczy `scope_containers` — NIE dodawać własnych reguł widoczności.
- `signals.py` jest CZYSTY: żadnych zapytań do DB, tylko operacje na przekazanych obiektach `Container` i słowniku `deadlines`. Właściwości modelu `Container.is_delayed` / `Container.is_stuck` są bez-DB i wolno ich używać.
- i18n: każdy nowy klucz dodać w 3 locale (PL, EN, PT) w `frontend/src/i18n.ts`.
- Frontend API usuwa przez `api.del`, pobiera `api.get`; typy w `frontend/src/types.ts` lub inline.
- Wagi/progi TYLKO w `SIGNAL_WEIGHTS` (jeden słownik) — żadnych magicznych liczb rozsianych po kodzie.

---

### Task 1: Silnik sygnałów (`signals.py`)

**Files:**
- Create: `backend/app/signals.py`
- Test: `backend/tests/test_signals.py`

**Interfaces:**
- Produces:
  - `SIGNAL_WEIGHTS: dict` — wagi typów + progi + stawki.
  - `compute_signals(containers, deadlines, today, weights=SIGNAL_WEIGHTS) -> list[dict]` — lista sygnałów jako dict-y, posortowana malejąco wg `score`. Każdy dict: `{container_id:int, container_no:str, company_name:str|None, supplier_name:str|None, port_name:str|None, eta:str|None, notify_date:str|None, status:str, type:str, score:float, urgency_days:int, cost_eur:float|None, action_kind:str, summary:str}`.
  - `deadlines`: `dict[int, datetime.date | None]` (container_id → termin demurrage), zgodny z `demurrage_deadlines()` z `notifications.py`.
  - typy sygnałów: `"delayed" | "demurrage" | "stuck" | "missing_avizo" | "missing_eta" | "missing_docs"`.
  - `action_kind`: `"container" | "avizo-form" | "documents"`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_signals.py
"""Silnik sygnałów: wykrywanie typów, punktacja i sort dla listy 'Co dziś'.
Czysta funkcja — bez DB, na lekkich atrapach kontenera."""
import datetime
import types

from app.signals import compute_signals, SIGNAL_WEIGHTS
from app.models import ContainerStatus, DocumentStatus

TODAY = datetime.date(2026, 9, 22)


def _c(**kw):
    """Atrapa kontenera: tylko pola/właściwości, których dotyka compute_signals."""
    defaults = dict(
        id=1, container_no="MEDU1234562",
        company=types.SimpleNamespace(name="ACME"),
        supplier=types.SimpleNamespace(name="Fushide"),
        port=types.SimpleNamespace(name="Gdańsk"),
        eta=None, notify_date=None,
        status=ContainerStatus.W_TRANSPORCIE,
        document_status=DocumentStatus.ZALACZONE,
        is_delayed=False, is_stuck=False,
    )
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


def test_detects_delayed():
    c = _c(is_delayed=True, eta=datetime.date(2026, 9, 15),
           status=ContainerStatus.W_PORCIE)
    feed = compute_signals([c], {c.id: None}, TODAY)
    types_ = {s["type"] for s in feed}
    assert "delayed" in types_


def test_demurrage_has_cost_and_outranks_missing_docs():
    demur = _c(id=1, container_no="MEDU1234562",
               eta=datetime.date(2026, 9, 20), status=ContainerStatus.W_PORCIE)
    docs = _c(id=2, container_no="CAIU7654324",
              document_status=DocumentStatus.BRAK)
    deadlines = {1: datetime.date(2026, 9, 24), 2: None}
    feed = compute_signals([demur, docs], deadlines, TODAY)
    demur_sig = next(s for s in feed if s["type"] == "demurrage")
    docs_sig = next(s for s in feed if s["type"] == "missing_docs")
    assert demur_sig["cost_eur"] and demur_sig["cost_eur"] > 0
    # demurrage z kosztem musi być wyżej na liście niż drobny brak dokumentu
    assert feed.index(demur_sig) < feed.index(docs_sig)


def test_missing_avizo_and_eta_and_action_kinds():
    avizo = _c(id=1, eta=datetime.date(2026, 9, 23), notify_date=None,
               status=ContainerStatus.W_TRANSPORCIE)
    no_eta = _c(id=2, container_no="CAIU7654324",
                eta=None, status=ContainerStatus.W_PORCIE)
    feed = compute_signals([avizo, no_eta], {1: None, 2: None}, TODAY)
    by_type = {s["type"]: s for s in feed}
    assert by_type["missing_avizo"]["action_kind"] == "avizo-form"
    assert "missing_eta" in by_type


def test_one_container_can_emit_multiple_signals():
    c = _c(is_delayed=True, eta=datetime.date(2026, 9, 10),
           status=ContainerStatus.W_PORCIE, document_status=DocumentStatus.BRAK)
    feed = compute_signals([c], {c.id: None}, TODAY)
    assert len({s["type"] for s in feed}) >= 2


def test_empty_when_all_clear():
    c = _c(eta=datetime.date(2026, 10, 30), notify_date=datetime.date(2026, 10, 25),
           status=ContainerStatus.W_TRANSPORCIE, document_status=DocumentStatus.ZALACZONE)
    feed = compute_signals([c], {c.id: None}, TODAY)
    assert feed == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_signals.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.signals'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/signals.py
"""Silnik sygnałów: z listy kontenerów liczy pozycje 'Co dziś' (jedna lista działań).

Czysta funkcja — bez DB. Dane wejściowe: kontenery (ze scope), słownik terminów
demurrage (container_id -> date|None) i 'dziś'. Wagi/progi w SIGNAL_WEIGHTS = pokrętło
strojenia (docelowo panel admina, na razie stałe)."""
import datetime

from .models import ContainerStatus, DocumentStatus

SIGNAL_WEIGHTS = {
    # waga bazowa typu (im wyższa, tym wyżej na liście przy równej pilności)
    "weights": {
        "demurrage": 10.0, "delayed": 6.0, "stuck": 5.0,
        "missing_avizo": 4.0, "missing_eta": 3.0, "missing_docs": 2.0,
    },
    "demurrage_days": 3,      # ile dni do terminu demurrage odpala sygnał
    "avizo_lead_days": 3,     # ETA w ciągu N dni bez awizacji = sygnał
    "demurrage_eur_per_day": 150.0,  # brak pola w configu — stała pokrętła
    "cost_scale": 100.0,      # dzielnik kosztu w punktacji (€ -> punkty)
}

# status 'w drodze/w porcie' = kontener aktywny, oczekuje ETA/awizacji/dokumentów
_ACTIVE = (ContainerStatus.W_TRANSPORCIE, ContainerStatus.W_PORCIE)


def _delay_days(c, today):
    ref = c.eta if (c.eta and c.eta < today) else (
        c.notify_date if (c.notify_date and c.notify_date < today) else None)
    return (today - ref).days if ref else 0


def compute_signals(containers, deadlines, today, weights=SIGNAL_WEIGHTS):
    w = weights["weights"]
    out = []

    def add(c, type_, urgency_days, cost_eur, action_kind, summary):
        cost_factor = (cost_eur or 0) / weights["cost_scale"]
        score = w[type_] * (1 + max(0, urgency_days)) + cost_factor
        out.append({
            "container_id": c.id, "container_no": c.container_no,
            "company_name": c.company.name if c.company else None,
            "supplier_name": c.supplier.name if c.supplier else None,
            "port_name": c.port.name if c.port else None,
            "eta": c.eta.isoformat() if c.eta else None,
            "notify_date": c.notify_date.isoformat() if c.notify_date else None,
            "status": c.status.value, "type": type_, "score": round(score, 2),
            "urgency_days": urgency_days, "cost_eur": cost_eur,
            "action_kind": action_kind, "summary": summary,
        })

    for c in containers:
        dd = _delay_days(c, today)
        deadline = deadlines.get(c.id)

        if deadline is not None and (deadline - today).days <= weights["demurrage_days"]:
            days_over = max(0, (today - deadline).days)
            cost = days_over * weights["demurrage_eur_per_day"] or weights["demurrage_eur_per_day"]
            until = (deadline - today).days
            add(c, "demurrage", -until if until < 0 else weights["demurrage_days"] - until,
                cost, "container", f"demurrage {'za ' + str(until) + ' dni' if until >= 0 else 'po terminie'} ≈ €{cost:.0f}")

        if c.is_delayed and dd > 0:
            add(c, "delayed", dd, None, "container", f"opóźniony +{dd} dni")

        if c.is_stuck:
            add(c, "stuck", dd, None, "container", "utknął (brak ruchu)")

        if c.status in _ACTIVE and c.eta and not c.notify_date \
                and (c.eta - today).days <= weights["avizo_lead_days"]:
            until = (c.eta - today).days
            add(c, "missing_avizo", weights["avizo_lead_days"] - until, None,
                "avizo-form", f"ETA za {until} dni, brak awizacji")

        if c.status in _ACTIVE and not c.eta:
            add(c, "missing_eta", dd, None, "container", "brak ETA")

        if c.document_status == DocumentStatus.BRAK:
            add(c, "missing_docs", dd, None, "documents", "brak dokumentów")

    out.sort(key=lambda s: (s["score"], s["cost_eur"] or 0, s["container_no"]),
             reverse=True)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_signals.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/signals.py backend/tests/test_signals.py
git commit -m "feat(signals): pure silnik sygnałów 'Co dziś' (6 typów + punktacja)"
```

---

### Task 2: Doklejenie `action_feed` do dashboardu

**Files:**
- Modify: `backend/app/routers/containers.py` (funkcja `dashboard`, ~1580-1637)
- Test: `backend/tests/test_dashboard_feed.py` (Create)

**Interfaces:**
- Consumes: `compute_signals`, `SIGNAL_WEIGHTS` z `app.signals`; `demurrage_deadlines` z `app.notifications` (już importowane w funkcji).
- Produces: klucz `"action_feed": list[dict]` w odpowiedzi `/api/stats/dashboard` (posortowany).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_dashboard_feed.py
"""Dashboard zwraca action_feed: jedna posortowana lista sygnałów w zakresie usera."""


def _company_id(client, headers, code):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
               if c["code"] == code)


def test_dashboard_returns_action_feed(client, admin_headers):
    acme_id = _company_id(client, admin_headers, "ACME")
    ports = client.get("/api/ports", headers=admin_headers).json()
    # kontener bez ETA i w porcie → co najmniej sygnał missing_eta
    c = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MEDU1234562", "company_id": acme_id,
        "port_id": ports[0]["id"], "status": "W_PORCIE"}).json()
    data = client.get("/api/stats/dashboard", headers=admin_headers).json()
    assert "action_feed" in data
    assert any(s["container_id"] == c["id"] for s in data["action_feed"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dashboard_feed.py -q`
Expected: FAIL — `KeyError: 'action_feed'` (assert `"action_feed" in data`)

- [ ] **Step 3: Add import and action_feed to dashboard response**

W `backend/app/routers/containers.py` na górze pliku (sekcja importów lokalnych aplikacji) dodaj:

```python
from ..signals import compute_signals
```

W funkcji `dashboard`, w zwracanym słowniku (po `"demurrage_list": ...`) dodaj klucz:

```python
        "action_feed": compute_signals(containers, deadlines, today),
```

(Zmienne `containers`, `deadlines`, `today` są już policzone wyżej w funkcji.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dashboard_feed.py tests/test_signals.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/containers.py backend/tests/test_dashboard_feed.py
git commit -m "feat(dashboard): action_feed z silnika sygnałów w /api/stats/dashboard"
```

---

### Task 3: Frontend — jedna lista „Co dziś" z `action_feed`

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/i18n.ts` (etykiety typów sygnałów — PL/EN/PT)
- Test: `frontend/src/pages/dashboard.ctl.dom.test.tsx` (Modify — dodać przypadek feedu)

**Interfaces:**
- Consumes: `data.action_feed: Signal[]` z `/api/stats/dashboard`.
- Produces (typ inline w DashboardPage):
  ```ts
  interface Signal {
    container_id: number; container_no: string; company_name: string | null
    supplier_name: string | null; port_name: string | null
    eta: string | null; notify_date: string | null; status: string
    type: 'delayed'|'demurrage'|'stuck'|'missing_avizo'|'missing_eta'|'missing_docs'
    score: number; urgency_days: number; cost_eur: number | null
    action_kind: 'container'|'avizo-form'|'documents'; summary: string
  }
  ```

- [ ] **Step 1: Write the failing test**

Dodaj do `frontend/src/pages/dashboard.ctl.dom.test.tsx` przypadek renderujący feed. Zakładając istniejący mock `api.get` w tym pliku, ustaw odpowiedź `/api/stats/dashboard` tak, by zawierała `action_feed` z jedną pozycją i sprawdź, że renderuje się `summary` oraz badge typu:

```tsx
it('renderuje jedną listę Co dziś z action_feed (summary + typ)', async () => {
  mockDashboard({
    today: 0, tomorrow: 0, in_transit: 0, at_port: 1, customs_in_progress: 0,
    delayed: 0, delayed_list: [], today_list: [], demurrage_list: [],
    action_feed: [{
      container_id: 7, container_no: 'MEDU1234562', company_name: 'ACME',
      supplier_name: null, port_name: 'Gdańsk', eta: null, notify_date: null,
      status: 'W_PORCIE', type: 'missing_eta', score: 3, urgency_days: 0,
      cost_eur: null, action_kind: 'container', summary: 'brak ETA',
    }],
  })
  render(<App />)  // lub bezpośrednio <DashboardPage/> wg konwencji pliku
  expect(await screen.findByText('brak ETA')).toBeInTheDocument()
  expect(await screen.findByText('MEDU1234562')).toBeInTheDocument()
})
```

(Uwaga: dopasuj `mockDashboard`/`render` do helperów już użytych w tym pliku — jeśli plik mockuje `api.get` inaczej, użyj istniejącego wzorca zamiast `mockDashboard`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/dashboard.ctl.dom.test.tsx`
Expected: FAIL — „brak ETA" nie renderuje się (lista wciąż z `delayed_list`).

- [ ] **Step 3: Podmień źródło listy na action_feed + kolumna „Co" + deep-link per typ**

W `frontend/src/pages/DashboardPage.tsx`:

3a. Dodaj typ `Signal` (jak w Interfaces) i rozszerz `DashboardData`:

```ts
  demurrage_list: Brief[]
  action_feed: Signal[]
}
```

3b. Zamień `actions` useMemo, by korzystał z `action_feed` (już posortowany przez backend), zachowując filtr spółki:

```ts
  const actions = useMemo(() =>
    (data?.action_feed ?? []).filter(r => !company || r.company_name === company),
    [data, company])

  const companies = useMemo(
    () => [...new Set((data?.action_feed ?? []).map(r => r.company_name).filter(Boolean))] as string[],
    [data])
```

3c. Poziom priorytetu z `score` (zamiast `delay_days`) — nadpisz `priority`:

```ts
function priority(score: number): { level: 1 | 2 | 3 } {
  if (score >= 60) return { level: 1 }
  if (score >= 25) return { level: 2 }
  return { level: 3 }
}
```

3d. Deep-link per typ — dodaj helper i użyj go w wierszu:

```ts
  const goTo = (r: Signal) => {
    if (r.action_kind === 'avizo-form') navigate(`/kontenery/${r.container_id}?akcja=awizacja`)
    else if (r.action_kind === 'documents') navigate(`/kontenery/${r.container_id}?tab=dokumenty`)
    else navigate(`/kontenery/${r.container_id}`)
  }
```

3e. W nagłówku tabeli dodaj kolumnę „Co" po `containerNo` i wyrenderuj `summary`; wiersz używa `priority(r.score)`, `r.container_id` jako klucz i `goTo(r)` na klik. Zastąp blok `actions.map(...)`:

```tsx
{actions.map(r => {
  const p = priority(r.score)
  return (
    <tr key={`${r.container_id}-${r.type}`} className="clickable" onClick={() => goTo(r)}>
      <td><span className={`prio prio-${p.level}`}>P{p.level}</span></td>
      <td className="mono">{r.container_no}</td>
      <td>{t(`sig_${r.type}`)}: {r.summary}</td>
      <td>{r.company_name}</td>
      <td>{r.port_name || '—'}</td>
      <td>{formatDate(r.eta)}</td>
      <td>{r.cost_eur ? `€${Math.round(r.cost_eur)}` : '—'}</td>
      <td><span className={`badge st-${r.status}`}>{t(`st_${r.status}`)}</span></td>
      <td>
        <button className="btn small secondary"
                onClick={e => { e.stopPropagation(); goTo(r) }}>
          {t('details')}
        </button>
      </td>
    </tr>
  )
})}
```

Zaktualizuj `<thead>` do kolumn: Priorytet, ContainerNo, `t('ctlWhat')`, Company, Port, ETA, `t('ctlCostCol')`, Status, Akcja (usuń kolumny Supplier/Awizacja/Opóźnienie, których nowy wiersz nie renderuje — liczba `<th>` musi zgadzać się z `<td>`).

3f. Popraw `doExport` (CSV), by używał pól Signal:

```ts
  const doExport = () => exportCsv('co-dzis.csv',
    [t('containerNo'), t('ctlWhat'), t('company'), t('port'), t('eta'), t('ctlCostCol'), t('status')],
    actions.map(r => [r.container_no, `${t(`sig_${r.type}`)}: ${r.summary}`,
      r.company_name ?? '', r.port_name ?? '', r.eta ?? '',
      r.cost_eur ? `€${Math.round(r.cost_eur)}` : '', t(`st_${r.status}`)]))
```

3g. Kafelek „decyzje" — pokaż liczność feedu zamiast `data.delayed`:

```tsx
        <CtlKpi label={t('ctlDecisions')} value={actions.length}
                sub={t('dashDelayedUnit')} accent="danger" />
```

- [ ] **Step 4: Dodaj klucze i18n (PL/EN/PT)**

W `frontend/src/i18n.ts` w każdym z 3 bloków locale dodaj (przy istniejących kluczach `ctl*`):

PL:
```ts
  sig_delayed: 'Opóźniony', sig_demurrage: 'Demurrage', sig_stuck: 'Utknął',
  sig_missing_avizo: 'Brak awizacji', sig_missing_eta: 'Brak ETA', sig_missing_docs: 'Brak dokumentów',
  ctlWhat: 'Co', ctlCostCol: 'Koszt',
```
EN:
```ts
  sig_delayed: 'Delayed', sig_demurrage: 'Demurrage', sig_stuck: 'Stuck',
  sig_missing_avizo: 'No booking', sig_missing_eta: 'No ETA', sig_missing_docs: 'No documents',
  ctlWhat: 'What', ctlCostCol: 'Cost',
```
PT:
```ts
  sig_delayed: 'Atrasado', sig_demurrage: 'Demurrage', sig_stuck: 'Parado',
  sig_missing_avizo: 'Sem marcação', sig_missing_eta: 'Sem ETA', sig_missing_docs: 'Sem documentos',
  ctlWhat: 'O quê', ctlCostCol: 'Custo',
```

- [ ] **Step 5: Run tests + typecheck**

Run: `cd frontend && npx vitest run src/pages/dashboard.ctl.dom.test.tsx && npx tsc -b --noEmit`
Expected: test PASS, tsc bez błędów.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/i18n.ts frontend/src/pages/dashboard.ctl.dom.test.tsx
git commit -m "feat(wieża): jedna lista 'Co dziś' z action_feed (typ + koszt + deep-link)"
```

---

## Uwagi wykonawcze

- Deep-linki `?akcja=awizacja` / `?tab=dokumenty` zakładają, że karta kontenera potrafi je odczytać. Jeśli obsługi query param jeszcze nie ma, w v1 wystarczy nawigacja do `/kontenery/{id}` (deep-link do sekcji = follow-up) — nie blokuj taska; zostaw prosty `navigate(\`/kontenery/${r.container_id}\`)` i dopisz TODO w commicie.
- Magazyn nadal dostaje 403 na dashboardzie (bez zmian) — feed magazynu to osobny spec.
- Po całości: `cd backend && python -m pytest tests/test_signals.py tests/test_dashboard_feed.py -q` oraz `cd frontend && npx tsc -b --noEmit` muszą być zielone przed PR.

# Timeline kontenera + mapa satelitarna — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jedna chronologiczna oś zdarzeń kontenera (4 źródła + etapy planowane) serwowana z backendu, wyrenderowana wspólnym komponentem na ContainerPage, plus satelitarny podkład NASA Blue Marble na mapie TrackingPage.

**Architecture:** Nowy moduł `backend/app/tracking/timeline.py` skleja PurchaseOrder.etd + TrackingEvent + VesselPortCall + AuditLog(status) + etapy planowane w posortowaną listę; endpoint `GET /api/containers/{id}/timeline` za `get_container_checked()`. Frontend: istniejąca oś „kurierska" w ContainerPage (IIFE, linie ~348-397) zostaje **wydzielona** do `ContainerTimeline.tsx` i przełączona na nowy endpoint. Mapa: `<image>` z bundlowanym JPG equirectangular zastępuje `<rect>+<path>` w SVG TrackingPage — projekcja `project()` pasuje 1:1, markery/zoom bez zmian.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (mapped_column) + pydantic, pytest (SQLite, fixtures z `conftest.py`), React + TS + vitest.

## Global Constraints

- Branch: nowy `claude/container-timeline` od `main` (NIE od `claude/etd-purchase-orders` — model `PurchaseOrder` jest już w main? **sprawdź**: jeśli `PurchaseOrder` istnieje tylko na `claude/etd-purchase-orders`, branchuj od niego).
- Zero nowych zależności; obraz mapy bundlowany lokalnie (CSP bez zewnętrznych hostów).
- Polish-first: tytuły z backendu po polsku; frontend tłumaczy znane kody przez istniejące klucze i18n (`ev_*`, `etdCol`, `eta`, `atd`, `notifyDate`).
- Autoryzacja per-firma WYŁĄCZNIE przez istniejący `get_container_checked()` (deps/containers) — nie powielaj reguł.
- Timestampy w bazie są naiwne UTC (`utcnow` z models.py) — nie używaj timezone-aware.

---

### Task 0: Branch

- [ ] **Step 1:** `git fetch origin && git log origin/main --oneline -3` — sprawdź, czy commit z `PurchaseOrder` (feat kolejka ETD) jest w main.
- [ ] **Step 2:** Jeśli tak: `git checkout -b claude/container-timeline origin/main`. Jeśli nie: `git checkout -b claude/container-timeline claude/etd-purchase-orders`.

---

### Task 1: Backend — `build_timeline()` (moduł + testy)

**Files:**
- Create: `backend/app/tracking/timeline.py`
- Modify: `backend/app/schemas.py` (po `VesselPortCallOut`, ~linia 710)
- Test: `backend/tests/test_timeline.py`

**Interfaces:**
- Consumes: `models.py`: `Container`, `TrackingEvent`, `VesselPortCall`, `TrackedVessel`, `AuditLog`, `PurchaseOrder`, `ContainerStatus`; `tracking/ais.py`: `normalize_name(name: str) -> str`.
- Produces: `schemas.TimelineEntryOut(kind, code, title, location, at, estimated, source)`; `timeline.build_timeline(db: Session, container: Container) -> list[TimelineEntryOut]` (posortowana rosnąco po `at`, wpisy bez daty na końcu).

- [ ] **Step 1: Schemat w `schemas.py`** (obok innych Out trackingu):

```python
class TimelineEntryOut(BaseModel):
    kind: str        # order | carrier | vessel | system | planned
    code: str        # np. PO_ETD, DEPART, PORT_ARRIVE, STATUS_W_PORCIE, ETA, NOTIFY
    title: str       # etykieta PL (fallback gdy front nie zna kodu)
    location: str
    at: datetime.datetime | None
    estimated: bool
    source: str
```

- [ ] **Step 2: Failing test** — `backend/tests/test_timeline.py`. Wzorzec fixtures jak w innych testach: `client`, `admin_headers` z conftest; kontener przez POST `/api/containers`, dane trackingu bezpośrednio przez `db_session`.

```python
import datetime

from app.models import (AuditLog, Container, PurchaseOrder, TrackedVessel,
                        TrackingEvent, VesselPortCall)


def _mk_container(client, admin_headers, **extra):
    payload = {"container_no": "CSNU0110266", "company_id": 1, **extra}
    r = client.post("/api/containers", headers=admin_headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_timeline_merges_and_sorts_sources(client, admin_headers, db_session):
    c = _mk_container(client, admin_headers,
                      vessel="MV DEMO ATLAS", eta="2099-01-10", notify_date="2099-01-14")
    cid = c["id"]
    db_session.add(PurchaseOrder(company_id=1, order_no="PO-1", container_id=cid,
                                 etd=datetime.date(2025, 12, 1), port_of_departure="Ningbo"))
    db_session.add(TrackingEvent(container_id=cid, event_code="DEPART",
                                 description="Vessel departure", location="Ningbo",
                                 occurred_at=datetime.datetime(2025, 12, 2, 8, 0)))
    v = TrackedVessel(name="MV DEMO ATLAS")
    db_session.add(v); db_session.flush()
    db_session.add(VesselPortCall(vessel_id=v.id, port="Singapore",
                                  arrived_at=datetime.datetime(2025, 12, 10, 6, 0),
                                  departed_at=datetime.datetime(2025, 12, 11, 2, 0)))
    db_session.add(AuditLog(entity_type="containers", entity_id=cid, field="status",
                            old_value="ZAPOWIEDZIANY", new_value="W_TRANSPORCIE",
                            created_at=datetime.datetime(2025, 12, 2, 9, 0)))
    db_session.commit()

    entries = client.get(f"/api/containers/{cid}/timeline",
                         headers=admin_headers).json()
    kinds = [e["kind"] for e in entries]
    # wszystkie źródła obecne
    assert {"order", "carrier", "vessel", "system", "planned"} <= set(kinds)
    # sort chronologiczny (None na końcu)
    ats = [e["at"] for e in entries if e["at"]]
    assert ats == sorted(ats)
    # przyszłe ETA/awizacja jako planned + estimated
    planned = [e for e in entries if e["kind"] == "planned"]
    assert {p["code"] for p in planned} == {"ETA", "NOTIFY"}
    assert all(p["estimated"] for p in planned)


def test_timeline_no_tracking_gives_system_history_only(client, admin_headers, db_session):
    c = _mk_container(client, admin_headers)
    db_session.add(AuditLog(entity_type="containers", entity_id=c["id"], field="status",
                            old_value=None, new_value="ZAPOWIEDZIANY"))
    db_session.commit()
    entries = client.get(f"/api/containers/{c['id']}/timeline",
                         headers=admin_headers).json()
    assert entries and all(e["kind"] == "system" for e in entries)


def test_timeline_isolation_other_company(client, admin_headers):
    # user innej firmy nie widzi kontenera — wzorzec z test_isolation.py:
    # firma 2 + user viewer w firmie 2, kontener w firmie 1
    c = _mk_container(client, admin_headers)
    comp = client.post("/api/companies", headers=admin_headers,
                       json={"name": "Obca", "code": "OBC"}).json()
    client.post("/api/admin/users", headers=admin_headers,
                json={"username": "obcy", "password": "obcy1234!", "role": "viewer",
                      "company_id": comp["id"]})
    from .conftest import login
    other = login(client, "obcy", "obcy1234!")
    r = client.get(f"/api/containers/{c['id']}/timeline", headers=other)
    assert r.status_code in (403, 404)
```

Uwaga dla wykonawcy: dopasuj `_mk_container` i tworzenie usera/firmy do realnych endpointów — **skopiuj wzorzec z `backend/tests/test_isolation.py`** (tam jest działający setup firm i userów); pola payloadu kontenera wg `POST /api/containers` w `routers/containers.py`. Nie zgaduj — przeczytaj te dwa miejsca.

- [ ] **Step 3: Run** `cd backend && python -m pytest tests/test_timeline.py -v` — Expected: FAIL (404, endpoint nie istnieje).

- [ ] **Step 4: Implementacja** `backend/app/tracking/timeline.py`:

```python
"""Oś czasu kontenera: 4 źródła + etapy planowane w jednej chronologii."""
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (AuditLog, Container, ContainerStatus, PurchaseOrder,
                      TrackedVessel, TrackingEvent, VesselPortCall, utcnow)
from ..schemas import TimelineEntryOut
from .ais import normalize_name

_STATUS_PL = {
    "ZAPOWIEDZIANY": "Zapowiedziany", "W_TRANSPORCIE": "W transporcie",
    "W_PORCIE": "W porcie", "ODPRAWA": "Odprawa", "AWIZOWANY": "Awizowany",
    "W_DOSTAWIE": "W dostawie", "DOSTARCZONY": "Dostarczony",
    "ZREALIZOWANY": "Zrealizowany",
}
_DELIVERED = {ContainerStatus.W_DOSTAWIE, ContainerStatus.DOSTARCZONY,
              ContainerStatus.ZREALIZOWANY}


def _dt(d: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(d, datetime.time.min)


def build_timeline(db: Session, container: Container) -> list[TimelineEntryOut]:
    entries: list[TimelineEntryOut] = []

    # order — zamówienia z arkusza ETD podpięte do kontenera
    for po in db.scalars(select(PurchaseOrder)
                         .where(PurchaseOrder.container_id == container.id)):
        if po.etd:
            entries.append(TimelineEntryOut(
                kind="order", code="PO_ETD",
                title=f"Zamówienie {po.order_no} — planowane wypłynięcie",
                location=po.port_of_departure, at=_dt(po.etd),
                estimated=True, source="etd-sheet"))

    # carrier — zdarzenia armatora
    events = db.scalars(select(TrackingEvent)
                        .where(TrackingEvent.container_id == container.id)
                        .order_by(TrackingEvent.occurred_at.asc().nulls_last(),
                                  TrackingEvent.id)).all()
    for ev in events:
        entries.append(TimelineEntryOut(
            kind="carrier", code=ev.event_code, title=ev.description,
            location=" · ".join(x for x in (ev.location, ev.vessel) if x),
            at=ev.occurred_at, estimated=ev.is_estimated, source=ev.source))

    # vessel — postoje portowe statku kontenera (geofence AIS)
    if container.vessel:
        vessel = db.scalar(select(TrackedVessel)
                           .where(TrackedVessel.name == normalize_name(container.vessel)))
        if vessel:
            for pc in db.scalars(select(VesselPortCall)
                                 .where(VesselPortCall.vessel_id == vessel.id)
                                 .order_by(VesselPortCall.arrived_at)):
                entries.append(TimelineEntryOut(
                    kind="vessel", code="PORT_ARRIVE",
                    title=f"Statek w porcie {pc.port}", location=pc.port,
                    at=pc.arrived_at, estimated=False, source="ais"))
                if pc.departed_at:
                    entries.append(TimelineEntryOut(
                        kind="vessel", code="PORT_DEPART",
                        title=f"Statek wyszedł z portu {pc.port}", location=pc.port,
                        at=pc.departed_at, estimated=False, source="ais"))

    # system — TYLKO zmiany statusu kontenera z audytu
    for a in db.scalars(select(AuditLog)
                        .where(AuditLog.entity_type == "containers",
                               AuditLog.entity_id == container.id,
                               AuditLog.field == "status")
                        .order_by(AuditLog.created_at)):
        label = _STATUS_PL.get(a.new_value or "", a.new_value or "?")
        entries.append(TimelineEntryOut(
            kind="system", code=f"STATUS_{a.new_value}",
            title=f"Status: {label}", location="",
            at=a.created_at, estimated=False, source="system"))

    # kamienie milowe / planned — logika przeniesiona 1:1 z osi w ContainerPage:
    # ETD tylko gdy brak zdarzenia DEPART (dublują się przy działającym SafeCube)
    if container.etd and not any(e.event_code == "DEPART" for e in events):
        entries.append(TimelineEntryOut(
            kind="planned", code="ETD", title="ETD", location="",
            at=_dt(container.etd), estimated=False, source="system"))
    if container.atd:
        entries.append(TimelineEntryOut(
            kind="planned", code="ATD", title="Dostarczono (ATD)", location="",
            at=_dt(container.atd), estimated=False, source="system"))
    elif container.eta:
        entries.append(TimelineEntryOut(
            kind="planned", code="ETA", title="ETA", location="",
            at=_dt(container.eta), estimated=True, source="system"))
    if container.notify_date:
        entries.append(TimelineEntryOut(
            kind="planned", code="NOTIFY", title="Awizacja", location="",
            at=_dt(container.notify_date),
            estimated=container.status not in _DELIVERED, source="system"))

    entries.sort(key=lambda e: (e.at is None, e.at or datetime.datetime.min))
    return entries
```

- [ ] **Step 5: Endpoint** w `backend/app/routers/tracking.py` (pod `container_events`, ta sama konwencja):

```python
@router.get("/containers/{container_id}/timeline",
            response_model=list[TimelineEntryOut])
def container_timeline(container_id: int, db: Session = Depends(get_db),
                       user: User = viewer):
    container = get_container_checked(db, container_id, user)
    return build_timeline(db, container)
```

Dodaj importy: `from ..schemas import ... TimelineEntryOut` i `from ..tracking.timeline import build_timeline`.

- [ ] **Step 6: Run** `cd backend && python -m pytest tests/test_timeline.py -v` — Expected: 3 PASS.
- [ ] **Step 7: Run full backend suite** `cd backend && python -m pytest -q` — Expected: bez nowych faili.
- [ ] **Step 8: Commit**

```bash
git add backend/app/tracking/timeline.py backend/app/routers/tracking.py backend/app/schemas.py backend/tests/test_timeline.py
git commit -m "feat(tracking): endpoint osi czasu kontenera — 4 źródła + etapy planowane"
```

---

### Task 2: Frontend — komponent `ContainerTimeline` na nowym endpointcie

**Files:**
- Create: `frontend/src/pages/tracking/ContainerTimeline.tsx`
- Modify: `frontend/src/pages/ContainerPage.tsx` (usunięcie IIFE osi ~348-397 + stanu `events`, jeśli nieużywany gdzie indziej — **sprawdź inne użycia `events` w pliku przed usunięciem**; polling po „Track now" (linia ~228) przełącz z `/events` na `/timeline` refetch komponentu przez prop `refreshKey`)
- Test: `frontend/src/container-timeline.dom.test.tsx`

**Interfaces:**
- Consumes: `GET /api/containers/{id}/timeline` → `TimelineEntry[]` (kształt z Task 1).
- Produces: `<ContainerTimeline containerId={number} refreshKey={number} />` — samowystarczalny (sam fetchuje); reużywalny w plastrze 2 (widok kliencki).

- [ ] **Step 1: Failing test DOM** (wzorzec mocków `api` skopiuj z `frontend/src/tracking.poll.dom.test.tsx`):

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ContainerTimeline from './pages/tracking/ContainerTimeline'

vi.mock('./api', () => ({ api: { get: vi.fn().mockResolvedValue([
  { kind: 'carrier', code: 'DEPART', title: 'Vessel departure',
    location: 'Ningbo', at: '2025-12-02T08:00:00', estimated: false, source: 'safecube' },
  { kind: 'planned', code: 'ETA', title: 'ETA', location: '',
    at: '2099-01-10T00:00:00', estimated: true, source: 'system' },
]) } }))

describe('ContainerTimeline', () => {
  it('renderuje wpisy, tłumaczy znane kody i oznacza szacowane', async () => {
    render(<ContainerTimeline containerId={1} refreshKey={0} />)
    expect(await screen.findByText(/Wyjście z portu/)).toBeInTheDocument()   // ev_DEPART pl
    expect(screen.getByText(/szacowane/)).toBeInTheDocument()
  })
})
```

Dopasuj ścieżkę mocka `./api` i providery (i18n/context), kopiując setup z istniejącego testu DOM ContainerPage/tracking — nie wymyślaj własnego.

- [ ] **Step 2: Run** `cd frontend && npx vitest run container-timeline` — Expected: FAIL (brak modułu).
- [ ] **Step 3: Implementacja komponentu** — przenieś renderowanie `.ctimeline` z ContainerPage (istniejące klasy CSS `ctimeline`, `ct-dot`, `ct-when`, `ct-label`, `ct-sub` — zero nowego CSS; dodaj tylko modyfikator koloru kropki po kind, np. `className={'k-' + en.kind}` + 5 reguł koloru w miejscu, gdzie zdefiniowano `.ctimeline`):

```tsx
import { useEffect, useState } from 'react'
import { api } from '../../api'
import { useT, formatDateTime, parseServerTs } from '../../i18n'   // dopasuj do realnych eksportów

export type TimelineEntry = {
  kind: string; code: string; title: string; location: string
  at: string | null; estimated: boolean; source: string
}

const KEYED: Record<string, string> = {   // kody z tłumaczeniem w i18n
  ETD: 'etdCol', ETA: 'eta', ATD: 'atd', NOTIFY: 'notifyDate',
}

export default function ContainerTimeline({ containerId, refreshKey = 0 }:
    { containerId: number; refreshKey?: number }) {
  const t = useT()
  const [entries, setEntries] = useState<TimelineEntry[]>([])
  useEffect(() => {
    let alive = true
    api.get<TimelineEntry[]>(`/api/containers/${containerId}/timeline`)
      .then(e => { if (alive) setEntries(e) }).catch(() => {})
    return () => { alive = false }
  }, [containerId, refreshKey])
  if (entries.length === 0) return <p style={{ color: 'var(--muted)' }}>{t('noEvents')}</p>
  const nowMs = Date.now()
  const label = (en: TimelineEntry) =>
    en.kind === 'carrier' ? (t(`ev_${en.code}`) || en.title)
      : KEYED[en.code] ? t(KEYED[en.code]) : en.title
  return (
    <ol className="ctimeline">
      {entries.map((en, i) => {
        const done = !en.estimated && !!en.at && parseServerTs(en.at).getTime() <= nowMs
        return (
          <li key={i} className={`k-${en.kind} ${done ? 'done' : en.estimated ? 'est' : ''}`}>
            <span className="ct-dot" aria-hidden="true" />
            <span className="ct-when mono">{en.at ? formatDateTime(en.at) : '—'}</span>
            <span className="ct-label">
              {label(en)}
              {en.estimated && <span className="muted"> ({t('estimated')})</span>}
            </span>
            {en.location && <span className="ct-sub muted">{en.location}</span>}
          </li>
        )
      })}
    </ol>
  )
}
```

Dopasuj importy (`useT`/`t`, `formatDateTime`, `parseServerTs`) do realnych eksportów — sprawdź nagłówek `ContainerPage.tsx`, tam wszystkie trzy są już używane.

- [ ] **Step 4:** W `ContainerPage.tsx` zastąp cały IIFE osi (linie ~348-397) przez `<ContainerTimeline containerId={container.id} refreshKey={trackRefresh} />`; dodaj stan `const [trackRefresh, setTrackRefresh] = useState(0)` inkrementowany w pollingu po „Track now". Usuń stan `events` i jego fetche TYLKO jeśli nic innego w pliku z nich nie korzysta.
- [ ] **Step 5: Run** `cd frontend && npx vitest run` — Expected: wszystkie PASS (w tym istniejące testy ContainerPage).
- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/tracking/ContainerTimeline.tsx frontend/src/pages/ContainerPage.tsx frontend/src/container-timeline.dom.test.tsx
git commit -m "feat(ui): wspólny komponent osi czasu kontenera na endpointcie /timeline"
```

---

### Task 3: Mapa satelitarna Blue Marble na TrackingPage

**Files:**
- Create: `frontend/src/assets/blue-marble.jpg` (pobrany)
- Modify: `frontend/src/pages/TrackingPage.tsx:6,264-265`

**Interfaces:**
- Consumes: `WORLD_W=1000, WORLD_H=500` z `worldmap.ts`; obraz equirectangular (pełny świat, lon -180..180, lat 90..-90) — dokładnie ta sama projekcja co `project()`.
- Produces: brak zmian API; `WORLD_PATH` przestaje być używany w TrackingPage (eksport w `worldmap.ts` zostaje — mockują go testy DOM).

- [ ] **Step 1: Pobierz obraz** (NASA, domena publiczna, equirectangular 2048×1024):

```bash
curl -L -o frontend/src/assets/blue-marble.jpg \
  https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57752/land_shallow_topo_2048.jpg
```

Sprawdź: plik istnieje, rozmiar ~0,3–1 MB, otwiera się jako pełna mapa świata (nie fragment). Jeśli URL martwy — NASA Visible Earth „land_shallow_topo" (Blue Marble land surface), dowolna wersja equirectangular ≥2048 px szer.

- [ ] **Step 2: Podmień tło SVG** w `TrackingPage.tsx`. Import na górze:

```tsx
import blueMarble from '../assets/blue-marble.jpg'
```

Zastąp linie 264–265:

```tsx
<rect width={WORLD_W} height={WORLD_H} fill="#0d1f36" />
<path d={WORLD_PATH} fill="#24425f" stroke="#3a5c7e" strokeWidth="0.5" />
```

przez:

```tsx
<rect width={WORLD_W} height={WORLD_H} fill="#0d1f36" />
<image href={blueMarble} width={WORLD_W} height={WORLD_H}
       preserveAspectRatio="none" />
```

(`rect` zostaje pod spodem jako tło na czas ładowania JPG). Usuń `WORLD_PATH` z importu w linii 6 (zostaw `WORLD_H`, `WORLD_W`).

- [ ] **Step 3: Deklaracja typu dla importu jpg** — sprawdź `frontend/src/vite-env.d.ts` / `tsconfig`; Vite ma wbudowane typy dla `*.jpg` przez `vite/client`. Jeśli `tsc` krzyczy, dodaj w `vite-env.d.ts`: `declare module '*.jpg'`.
- [ ] **Step 4: Run** `cd frontend && npx vitest run tracking && npx tsc --noEmit` — Expected: PASS (testy trackingu mockują `worldmap`, importu jpg vitest obsługuje przez vite).
- [ ] **Step 5: Weryfikacja wizualna** — uruchom dev (`npm run dev` + backend), otwórz TrackingPage: markery i trasy AIS czytelne na satelitarnym tle (markery mają białą obwódkę). Jeśli trasy giną na ciemnym oceanie — pogrub/rozjaśnij linię trasy w miejscu jej rysowania (TrackingPage, warstwa AIS). Zrób screenshot do PR.
- [ ] **Step 6: Commit**

```bash
git add frontend/src/assets/blue-marble.jpg frontend/src/pages/TrackingPage.tsx
git commit -m "feat(ui): satelitarny podklad NASA Blue Marble na mapie trackingu"
```

---

### Task 4: Finał

- [ ] **Step 1:** Pełne suity: `cd backend && python -m pytest -q` oraz `cd frontend && npx vitest run && npx tsc --noEmit` — Expected: zielono; pokaż wyniki.
- [ ] **Step 2:** Push + PR na `main` (tytuł: „Oś czasu kontenera + mapa satelitarna"), body ze screenshotem mapy i stopką:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01KEVcYV7LAU69MxTTmrJkoj
```

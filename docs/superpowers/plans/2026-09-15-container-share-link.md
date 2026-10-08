# Publiczny link kliencki kontenera — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin/logistyka generuje z ContainerPage publiczny link `/k/{token}`; klient bez logowania widzi status + oś czasu kontenera (reużyty `ContainerTimeline`).

**Architecture:** Nowy model `ContainerShareLink` (hash SHA-256, wzorzec 1:1 z `DriverLink` w `models.py:855`) + router `share.py` z POST za `get_container_checked()` i publicznym GET. Frontend: `ContainerTimeline` dostaje opcjonalny prop `entries` (nie fetchuje, gdy podany), nowa publiczna strona `SharePage` pod `/k/:token` (wzorzec `/dostawa/:token` w App.tsx), przycisk „Link dla klienta" na ContainerPage.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + alembic, pytest; React + TS + vitest.

## Global Constraints

- Branch: `claude/container-share-link` (już istnieje, spec zacommitowana).
- Zero nowych zależności.
- Publiczna odpowiedź zawiera DOKŁADNIE 5 pól: `container_no`, `status`, `eta`, `notify_date`, `timeline` — nic więcej (strażnik przed wyciekiem: test asertuje zbiór kluczy).
- Token: surowy tylko w URL (`secrets.token_urlsafe(32)`), w bazie hash SHA-256 hex (String(64)); wzorzec z `routers/driver.py:30`.
- Wygasanie: 410 gdy status ZREALIZOWANY i ostatni wpis AuditLog (entity_type="containers", field="status", new_value="ZREALIZOWANY") starszy niż 30 dni; brak wpisu → link ważny.
- Timestampy naiwne UTC (`utcnow` z models.py).
- Polish-first komunikaty; stylistyka stal+bursztyn (istniejące tokeny CSS).

---

### Task 1: Backend — model, migracja, endpointy, testy

**Files:**
- Modify: `backend/app/models.py` (po klasie `DriverLink`, ~linia 867)
- Create: `backend/migrations/versions/<rev>_container_share_links.py` (przez `alembic revision`, down_revision = aktualny head `b4d2e5f6a7c8` — zweryfikuj `python -m alembic heads`)
- Create: `backend/app/routers/share.py`
- Modify: `backend/app/main.py` (include_router obok `driver.router`, ~linia 263)
- Modify: `backend/app/schemas.py` (obok `TimelineEntryOut`)
- Test: `backend/tests/test_share_link.py`

**Interfaces:**
- Consumes: `get_container_checked(db, container_id, user)` z deps; `build_timeline(db, container)` z `app.tracking.timeline`; wzorce z `routers/driver.py` (`_hash_token`, router prefix `/api`).
- Produces: `POST /api/containers/{id}/share-link` → `{"token": str}` (201); `GET /api/public/containers/{token}` → `PublicContainerOut`.

- [ ] **Step 1: Model** w `models.py` (pod `DriverLink`):

```python
class ContainerShareLink(Base):
    """Publiczny link kliencki „mój kontener" — token hashowany jak w awizo/driver.

    Jeden aktywny link per kontener: ponowne wygenerowanie kasuje poprzedni."""
    __tablename__ = "container_share_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # SHA-256
    container_id: Mapped[int] = mapped_column(
        ForeignKey("containers.id"), unique=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    container: Mapped["Container"] = relationship()
```

- [ ] **Step 2: Migracja** — `cd backend && python -m alembic revision -m "container_share_links"`, w wygenerowanym pliku (down_revision musi wskazywać aktualny head):

```python
def upgrade() -> None:
    op.create_table(
        "container_share_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("container_id", sa.Integer(),
                  sa.ForeignKey("containers.id"), nullable=False),
        sa.Column("created_by_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_container_share_links_token",
                    "container_share_links", ["token"], unique=True)
    op.create_index("ix_container_share_links_container_id",
                    "container_share_links", ["container_id"], unique=True)


def downgrade() -> None:
    op.drop_table("container_share_links")
```

- [ ] **Step 3: Schemat** w `schemas.py` (obok `TimelineEntryOut`):

```python
class PublicContainerOut(BaseModel):
    container_no: str
    status: str
    eta: datetime.date | None
    notify_date: datetime.date | None
    timeline: list[TimelineEntryOut]
```

- [ ] **Step 4: Failing testy** — `backend/tests/test_share_link.py`. Setup firm/userów SKOPIUJ z `backend/tests/test_isolation.py` (nie zgaduj payloadów); kontener przez POST `/api/containers` jak w `tests/test_timeline.py`:

```python
import datetime

from app.models import AuditLog, ContainerShareLink


def _mk_container(client, admin_headers, **extra):
    payload = {"container_no": "CSNU0110266", "company_id": 1, **extra}
    r = client.post("/api/containers", headers=admin_headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _mk_link(client, admin_headers, cid):
    r = client.post(f"/api/containers/{cid}/share-link", headers=admin_headers)
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_generate_and_public_read(client, admin_headers):
    c = _mk_container(client, admin_headers, eta="2099-01-10")
    token = _mk_link(client, admin_headers, c["id"])
    r = client.get(f"/api/public/containers/{token}")  # bez auth!
    assert r.status_code == 200
    body = r.json()
    # strażnik przed wyciekiem: DOKŁADNIE te pola i żadnych innych
    assert set(body.keys()) == {"container_no", "status", "eta",
                                "notify_date", "timeline"}
    assert body["container_no"] == "CSNU0110266"
    assert isinstance(body["timeline"], list)


def test_rotation_kills_old_token(client, admin_headers):
    c = _mk_container(client, admin_headers)
    old = _mk_link(client, admin_headers, c["id"])
    new = _mk_link(client, admin_headers, c["id"])
    assert client.get(f"/api/public/containers/{old}").status_code == 404
    assert client.get(f"/api/public/containers/{new}").status_code == 200


def test_bad_token_404(client, admin_headers):
    assert client.get("/api/public/containers/xxx").status_code == 404


def test_viewer_cannot_generate(client, admin_headers):
    # user viewer wg wzorca z test_isolation.py (skopiuj tworzenie usera + login)
    ...


def test_expired_after_closed_30_days(client, admin_headers, db_session):
    c = _mk_container(client, admin_headers)
    token = _mk_link(client, admin_headers, c["id"])
    # przestaw status na ZREALIZOWANY bezpośrednio w bazie + stary wpis audytu
    from app.models import Container, ContainerStatus
    cont = db_session.get(Container, c["id"])
    cont.status = ContainerStatus.ZREALIZOWANY
    db_session.add(AuditLog(
        entity_type="containers", entity_id=c["id"], field="status",
        old_value="DOSTARCZONY", new_value="ZREALIZOWANY",
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=31)))
    db_session.commit()
    assert client.get(f"/api/public/containers/{token}").status_code == 410
```

Uzupełnij `test_viewer_cannot_generate` realnym setupem viewera z `test_isolation.py`; oczekiwany status 403.

- [ ] **Step 5: Run** `cd backend && python -m pytest tests/test_share_link.py -v` — Expected: FAIL (404, endpointy nie istnieją).

- [ ] **Step 6: Router** `backend/app/routers/share.py`:

```python
"""Publiczny link kliencki „mój kontener": generowanie + odczyt bez logowania."""
import datetime
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_container_checked
from ..models import (AuditLog, Container, ContainerShareLink, ContainerStatus,
                      User, utcnow)
from ..schemas import PublicContainerOut
from ..tracking.timeline import build_timeline

router = APIRouter(prefix="/api", tags=["share"])

_EXPIRY_DAYS = 30


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("/containers/{container_id}/share-link", status_code=201)
def create_share_link(container_id: int, db: Session = Depends(get_db),
                      user: User = ...):  # editors — patrz uwaga niżej
    container = get_container_checked(db, container_id, user)
    raw = secrets.token_urlsafe(32)
    db.query(ContainerShareLink).filter(
        ContainerShareLink.container_id == container.id).delete()
    db.add(ContainerShareLink(token=_hash_token(raw), container_id=container.id,
                              created_by_id=user.id))
    db.commit()
    return {"token": raw}


@router.get("/public/containers/{token}", response_model=PublicContainerOut)
def public_container(token: str, db: Session = Depends(get_db)):
    link = db.scalar(select(ContainerShareLink)
                     .where(ContainerShareLink.token == _hash_token(token)))
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nieznany link.")
    container = link.container
    if container.status == ContainerStatus.ZREALIZOWANY:
        closed_at = db.scalar(
            select(AuditLog.created_at)
            .where(AuditLog.entity_type == "containers",
                   AuditLog.entity_id == container.id,
                   AuditLog.field == "status",
                   AuditLog.new_value == "ZREALIZOWANY")
            .order_by(AuditLog.created_at.desc()).limit(1))
        if closed_at and closed_at < utcnow() - datetime.timedelta(days=_EXPIRY_DAYS):
            raise HTTPException(status.HTTP_410_GONE, "Link wygasł.")
    return PublicContainerOut(
        container_no=container.container_no,
        status=container.status.value,
        eta=container.eta,
        notify_date=container.notify_date,
        timeline=build_timeline(db, container))
```

Uwaga o roli: dependency dla POST dobierz z istniejących w repo — zajrzyj do `backend/app/routers/driver.py` i `deps.py`, użyj tej samej zależności, którą mają akcje admin/logistics (prawdopodobnie `editors`; NIE twórz nowej). Import statusów/enum zweryfikuj w `models.py`.

- [ ] **Step 7: Rejestracja** w `main.py`: `from .routers import share` (w istniejącym imporcie routerów) + `app.include_router(share.router)` obok `driver.router`.
- [ ] **Step 8: Run** `cd backend && python -m pytest tests/test_share_link.py -v` — Expected: wszystkie PASS.
- [ ] **Step 9: Run** `cd backend && python -m pytest tests/test_dev_schema_shim.py tests/test_timeline.py -q` — Expected: PASS (migracja zgodna z modelem).
- [ ] **Step 10: Commit**

```bash
git add backend/app/models.py backend/migrations/versions backend/app/routers/share.py backend/app/main.py backend/app/schemas.py backend/tests/test_share_link.py
git commit -m "feat(share): publiczny link kliencki kontenera — token hashowany, rotacja, wygasanie"
```

---

### Task 2: Frontend — prop `entries`, strona `/k/:token`, przycisk

**Files:**
- Modify: `frontend/src/pages/tracking/ContainerTimeline.tsx`
- Create: `frontend/src/pages/SharePage.tsx`
- Modify: `frontend/src/App.tsx` (routes publiczne ~linie 522-523 i 540-541 — dodaj `/k/:token` w OBU miejscach, wzorzec `/dostawa/:token`)
- Modify: `frontend/src/pages/ContainerPage.tsx` (przycisk „Link dla klienta" obok innych akcji admin/logistics)
- Test: `frontend/src/share-page.dom.test.tsx`

**Interfaces:**
- Consumes: `GET /api/public/containers/{token}` → `{container_no, status, eta, notify_date, timeline: TimelineEntry[]}`; `POST /api/containers/{id}/share-link` → `{token}`; `ContainerTimeline` z Task 1 plastra 1.
- Produces: `<ContainerTimeline entries={TimelineEntry[]} containerId={0} />` — z prop `entries` komponent NIE woła api; `SharePage` pod `/k/:token`.

- [ ] **Step 1: Prop `entries`** w `ContainerTimeline.tsx` — rozszerz sygnaturę i efekt:

```tsx
export default function ContainerTimeline({ containerId, refreshKey = 0, entries: given }:
    { containerId: number; refreshKey?: number; entries?: TimelineEntry[] }) {
  const t = useT()
  const [fetched, setFetched] = useState<TimelineEntry[]>([])
  useEffect(() => {
    if (given) return
    let alive = true
    api.get<TimelineEntry[]>(`/api/containers/${containerId}/timeline`)
      .then(e => { if (alive) setFetched(Array.isArray(e) ? e : []) }).catch(() => {})
    return () => { alive = false }
  }, [containerId, refreshKey, given])
  const entries = given ?? fetched
  ...  // reszta bez zmian
}
```

- [ ] **Step 2: Failing test DOM** `frontend/src/share-page.dom.test.tsx` (mock `./api` jak w `container-timeline.dom.test.tsx`):

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import SharePage from './pages/SharePage'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('./api', () => ({ api: { get: apiGet }, errorMessage: (e: unknown) => String(e) }))

const renderAt = (token: string) => render(
  <MemoryRouter initialEntries={[`/k/${token}`]}>
    <Routes><Route path="/k/:token" element={<SharePage />} /></Routes>
  </MemoryRouter>)

describe('SharePage', () => {
  it('renderuje status i oś czasu', async () => {
    apiGet.mockResolvedValue({
      container_no: 'CSNU1', status: 'W_TRANSPORCIE', eta: '2099-01-10',
      notify_date: null,
      timeline: [{ kind: 'planned', code: 'ETA', title: 'ETA', location: '',
                   at: '2099-01-10T00:00:00', estimated: true, source: 'system' }],
    })
    renderAt('tok')
    expect(await screen.findByText('CSNU1')).toBeTruthy()
    expect(screen.getByText(/W transporcie/i)).toBeTruthy()
    // ContainerTimeline z prop entries NIE woła api — jedyny call to publiczny endpoint
    expect(apiGet).toHaveBeenCalledTimes(1)
  })

  it('pokazuje komunikat wygaśnięcia przy 410', async () => {
    apiGet.mockRejectedValue({ status: 410 })
    renderAt('tok')
    expect(await screen.findByText(/wygasł/i)).toBeTruthy()
  })
})
```

Dopasuj kształt odrzuconego błędu (`{status: 410}`) do realnego kształtu błędów z `frontend/src/api.ts` — przeczytaj `errorMessage`/klasę błędu i asertuj to, co naprawdę leci; sprawdź też jak ContainerPage mapuje status na etykietę PL (użyj tego samego słownika/klucza i18n).

- [ ] **Step 3: Run** `cd frontend && npx vitest run share-page` — Expected: FAIL (brak modułu).

- [ ] **Step 4: `SharePage.tsx`** — prosta strona bez topnavu (własny kontener max-width, tokeny CSS repo):

```tsx
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import { useT } from '../i18n'
import ContainerTimeline, { TimelineEntry } from './tracking/ContainerTimeline'

type PublicContainer = {
  container_no: string; status: string
  eta: string | null; notify_date: string | null
  timeline: TimelineEntry[]
}

export default function SharePage() {
  const { token } = useParams()
  const t = useT()
  const [data, setData] = useState<PublicContainer | null>(null)
  const [err, setErr] = useState<'gone' | 'notfound' | null>(null)
  useEffect(() => {
    api.get<PublicContainer>(`/api/public/containers/${token}`)
      .then(setData)
      .catch((e: unknown) => setErr((e as { status?: number }).status === 410 ? 'gone' : 'notfound'))
  }, [token])
  if (err === 'gone') return <main className="share-page"><p>Link wygasł.</p></main>
  if (err === 'notfound') return <main className="share-page"><p>Link nieprawidłowy.</p></main>
  if (!data) return <main className="share-page"><p>{t('loading')}</p></main>
  return (
    <main className="share-page" style={{ maxWidth: 640, margin: '0 auto', padding: 24 }}>
      <h1 className="mono">{data.container_no}</h1>
      <p><span className={`badge status-${data.status}`}>{t(`st_${data.status}`) || data.status}</span></p>
      {data.eta && <p>ETA: {data.eta}</p>}
      {data.notify_date && <p>{t('notifyDate')}: {data.notify_date}</p>}
      <ContainerTimeline containerId={0} entries={data.timeline} />
    </main>
  )
}
```

Dopasuj klasy badge'a statusu i klucze i18n (`st_*`, `loading`, `notifyDate`) do realnych z `i18n.ts` / ContainerPage — jeśli klucza statusu nie ma, użyj istniejącego słownika etykiet statusów z QueuePage/ContainerPage. Daty formatuj przez `formatDate` z `dates.ts` jak reszta appki.

- [ ] **Step 5: Route** w `App.tsx` — dodaj `<Route path="/k/:token" element={<SharePage />} />` w obu blokach routes publicznych (obok `/dostawa/:token`, linie ~522-523 i ~540-541) + import.

- [ ] **Step 6: Przycisk** na ContainerPage (obok istniejących akcji dla admin/logistics — sprawdź, jak są warunkowane rolą inne przyciski, np. „Track now"/SMS, i użyj tego samego warunku):

```tsx
const shareLink = async () => {
  const { token } = await api.post<{ token: string }>(`/api/containers/${container.id}/share-link`, {})
  await navigator.clipboard.writeText(`${window.location.origin}/k/${token}`)
  toast(t('shareLinkCopied'))  // dodaj klucz PL/EN w i18n.ts: „Link dla klienta skopiowany — poprzedni przestał działać"
}
```

Użyj istniejącego mechanizmu toastów z `feedback.tsx` (jak reszta ContainerPage).

- [ ] **Step 7: Run** `cd frontend && npx vitest run && npx tsc --noEmit` — Expected: wszystko PASS.
- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/tracking/ContainerTimeline.tsx frontend/src/pages/SharePage.tsx frontend/src/App.tsx frontend/src/pages/ContainerPage.tsx frontend/src/share-page.dom.test.tsx frontend/src/i18n.ts
git commit -m "feat(ui): publiczna strona /k/{token} + przycisk Link dla klienta"
```

---

### Task 3: Finał

- [ ] **Step 1:** Pełne suity: `cd backend && python -m pytest -q` oraz `cd frontend && npx vitest run && npx tsc --noEmit` — Expected: zielono (backend: 1 znany skip); pokaż wyniki.
- [ ] **Step 2:** Push + PR na `main` (tytuł: „Publiczny link kliencki kontenera"), body z opisem zakresu danych publicznych i stopką:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01QPtr6gmknEkM3RJCErodMe
```

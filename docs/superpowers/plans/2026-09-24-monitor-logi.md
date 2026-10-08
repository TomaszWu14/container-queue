# Monitor serwera cz. 2 (dziennik) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zapis błędnych/wolnych żądań, liczników ruchu i przebiegów zadań tła do bazy + przeglądarka w panelu admina + dzwonek przy 5xx / padniętym zadaniu.

**Architecture:** Moduł `backend/app/applog.py` trzyma bufor w pamięci (lista wpisów + liczniki minutowe) i funkcje `record_request`, `record_job`, `flush(db)`, `purge(db)`, `maybe_alert(...)`. Middleware (w `main.py`) i `job_loop` (w `jobs.py`) tylko dopisują do bufora; pętla `applog_loop` w lifespan zrzuca bufor co 30 s. Router `routers/logs.py` czyta dane. Front: podzakładki w Monitorze serwera.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic, React 19 + vitest.

Spec: `docs/superpowers/specs/2026-09-24-monitor-logi-design.md`.

## Global Constraints

- Max 500 linii na plik (`scripts/check_file_lengths.py`); `main.py` ma ~461 linii — dopisuj tam minimum (middleware jako klasa w `applog.py`, w `main.py` tylko `add_middleware` i start pętli).
- Migracja od jedynej głowy alembica: **`avatar001`**.
- Nowe teksty UI tylko w `frontend/src/i18n/features/monitor-logi.ts`.
- Zapis żądania gdy `status >= 400` albo `duration_ms > 1000`. Pomijane: ścieżki nie zaczynające się od `/api/`, `/api/health`, 401 z `GET /api/auth/me`.
- Ścieżka zawsze przez `redact_tokens` (z `app/main.py` — przenieś lub zaimportuj bez cyklu; zob. Task 1).
- Retencja 30 dni. Alert max 1/h na rodzaj (`request`, `job`), kind `system-error`, odbiorcy: aktywni `Role.admin`.
- Endpointy tylko admin (`admin_only` jak w `routers/system.py`).
- Testy backendu z `backend/`, jeden pytest naraz. Przed PR: pełny pytest, `npx vitest run`, `npm run build`.

---

### Task 1: Zbieranie — modele, migracja, `applog.py`, middleware, hook w `job_loop`

**Files:**
- Create: `backend/app/models/applog.py` (+ eksport w `backend/app/models/__init__.py` wzorem innych modułów)
- Create: `backend/migrations/versions/log001_applog.py`
- Create: `backend/app/applog.py`
- Modify: `backend/app/main.py` (middleware + pętla w lifespan)
- Modify: `backend/app/jobs.py` (`job_loop` zapisuje przebiegi; `build_jobs` dostaje job retencji)
- Modify: `backend/app/security.py` (`get_current_user` ustawia `request.state.user_id`)
- Test: `backend/tests/test_applog.py`

**Interfaces (Produces):**
- Modele: `RequestLog`, `RequestCounter`, `JobRun` (pola jak w specu).
- `applog.record_request(*, method: str, path: str, status: int, duration_ms: int, user_id: int | None, ip: str, request_id: str, error: str = "") -> None`
- `applog.record_job(*, job: str, fn: str, started_at: datetime, duration_ms: int, ok: bool, detail: str) -> None`
- `applog.flush(db) -> int` (zapisuje bufor + liczniki, commit, zwraca liczbę wpisów; wywołuje alerty)
- `applog.purge(db, days: int = 30) -> int`
- `applog.RequestLogMiddleware` (Starlette `BaseHTTPMiddleware`)
- `async applog.applog_loop()` — co 30 s `flush` w wątku (`asyncio.to_thread`), wyjątki logowane, pętla nie umiera.

- [ ] **Step 1: Failing tests** — `backend/tests/test_applog.py`:

```python
"""Dziennik żądań/zadań: co trafia do bazy, maskowanie, alerty, retencja."""
import datetime

from sqlalchemy import select

from app import applog
from app.models import JobRun, Notification, RequestCounter, RequestLog, utcnow
from tests.conftest import login


def _flush(db_session):
    applog.flush(db_session)
    db_session.expire_all()


def test_error_and_slow_requests_logged_ok_counted_only(client, db_session):
    applog.reset_for_tests()
    h = login(client)
    client.get("/api/containers/999999", headers=h)          # 404 → zapis
    client.get("/api/companies", headers=h)                   # 200 → tylko licznik
    client.get("/api/health")                                 # pomijane całkiem
    _flush(db_session)
    rows = db_session.scalars(select(RequestLog)).all()
    assert [(r.method, r.path, r.status) for r in rows] == [("GET", "/api/containers/999999", 404)]
    assert rows[0].user_id is not None and rows[0].request_id
    total = sum(c.total for c in db_session.scalars(select(RequestCounter)).all())
    assert total >= 3          # login + 404 + companies (health nie liczony)


def test_public_token_masked_in_path(db_session):
    applog.reset_for_tests()
    applog.record_request(method="GET", path="/api/avizo/abcdefghijklmnopqrstuv", status=404,
                          duration_ms=5, user_id=None, ip="1.2.3.4", request_id="r1")
    _flush(db_session)
    row = db_session.scalars(select(RequestLog)).one()
    assert "abcdefghijklmnopqrstuv" not in row.path


def test_5xx_alerts_admins_once_per_hour(db_session):
    applog.reset_for_tests()
    for _ in range(3):
        applog.record_request(method="GET", path="/api/x", status=500, duration_ms=3,
                              user_id=None, ip="", request_id="r", error="Traceback…")
        _flush(db_session)
    alerts = db_session.scalars(select(Notification).where(Notification.kind == "system-error")).all()
    assert len(alerts) == len({a.user_id for a in alerts}) >= 1   # jeden na admina, nie trzy


def test_failed_job_recorded(db_session):
    applog.reset_for_tests()
    applog.record_job(job="demo", fn="boom", started_at=utcnow(), duration_ms=12, ok=False,
                      detail="ValueError: x")
    _flush(db_session)
    run = db_session.scalars(select(JobRun)).one()
    assert (run.job, run.fn, run.ok) == ("demo", "boom", False)


def test_purge_removes_older_than_30_days(db_session):
    old = utcnow() - datetime.timedelta(days=31)
    db_session.add(RequestLog(at=old, method="GET", path="/api/a", status=500, duration_ms=1,
                              ip="", request_id="", error=""))
    db_session.add(JobRun(job="j", fn="f", started_at=old, duration_ms=1, ok=True, detail=""))
    db_session.add(RequestCounter(minute=old.replace(second=0, microsecond=0), total=1, c4xx=0,
                                  c5xx=0, dur_ms_sum=1))
    db_session.commit()
    assert applog.purge(db_session) == 3
```

(`reset_for_tests()` — czyści bufor i znaczniki alertów; publiczna, bo testy dzielą proces.)
Uwaga: w testach pętle tła są wyłączone (`conftest`), więc flush wołamy ręcznie. Sprawdź nazwę statusu 404 dla nieistniejącego kontenera — jeśli endpoint zwraca inny kod ≥ 400, dopasuj asercję.

- [ ] **Step 2: Run** `python -m pytest -q tests/test_applog.py` → FAIL.

- [ ] **Step 3: Modele** `backend/app/models/applog.py`:

```python
"""Dziennik serwera: błędne/wolne żądania, liczniki ruchu per minuta, przebiegi zadań tła."""
import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class RequestLog(Base):
    __tablename__ = "request_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime.datetime] = mapped_column(DateTime, index=True)
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(500))
    status: Mapped[int] = mapped_column(Integer, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    request_id: Mapped[str] = mapped_column(String(16), default="")
    error: Mapped[str] = mapped_column(Text, default="")


class RequestCounter(Base):
    __tablename__ = "request_counters"
    id: Mapped[int] = mapped_column(primary_key=True)
    minute: Mapped[datetime.datetime] = mapped_column(DateTime, unique=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    c4xx: Mapped[int] = mapped_column(Integer, default=0)
    c5xx: Mapped[int] = mapped_column(Integer, default=0)
    dur_ms_sum: Mapped[int] = mapped_column(Integer, default=0)


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(60), index=True)
    fn: Mapped[str] = mapped_column(String(120))
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[str] = mapped_column(Text, default="")
```

Uwaga: `user_id` z `ondelete="SET NULL"` — usunięcie użytkownika nie może blokować się na logach (Postgres FK). Sprawdź w `routers/admin.py` `delete_user`, czy ręcznie czyści powiązane tabele — jeśli tak, dopisz `RequestLog.user_id = NULL` dla tego usera.

- [ ] **Step 4: Migracja** `backend/migrations/versions/log001_applog.py` — `revision="log001"`, `down_revision="avatar001"`; `op.create_table` dla trzech tabel (kolumny i typy jak w modelach, `user_id` z `sa.ForeignKey("users.id", ondelete="SET NULL")`, `server_default=sa.text("''")` dla stringów/Text z domyślnym pustym, `server_default=sa.text("0")` dla liczników) + indeksy `ix_request_logs_at`, `ix_request_logs_status`, `ix_job_runs_job`, `ix_job_runs_started_at` oraz unikat na `request_counters.minute`; `downgrade` = `drop_table` ×3.

- [ ] **Step 5: `backend/app/applog.py`**

```python
"""Dziennik serwera: bufor w pamięci → baza co 30 s (applog_loop), alerty dla adminów.

Middleware i job_loop tylko dopisują do bufora (bez SQL na ścieżce żądania). Każdy
proces ma własny bufor i własną pętlę zrzutu (także instancja bez pętli tła)."""
import asyncio
import datetime
import logging
import threading
import time

from sqlalchemy import delete, select
from starlette.middleware.base import BaseHTTPMiddleware

from .database import SessionLocal
from .models import JobRun, RequestCounter, RequestLog, Role, User, utcnow

logger = logging.getLogger(__name__)

SLOW_MS = 1000
RETENTION_DAYS = 30
ALERT_EVERY_S = 3600
FLUSH_EVERY_S = 30

_lock = threading.Lock()
_requests: list[dict] = []
_jobs: list[dict] = []
_counters: dict[datetime.datetime, list[int]] = {}   # minuta → [total, 4xx, 5xx, dur_sum]
_last_alert: dict[str, float] = {}


def reset_for_tests() -> None:
    with _lock:
        _requests.clear(); _jobs.clear(); _counters.clear(); _last_alert.clear()


def _skip(method: str, path: str, status: int) -> bool:
    return (not path.startswith("/api/") or path == "/api/health"
            or (status == 401 and method == "GET" and path == "/api/auth/me"))


def record_request(*, method: str, path: str, status: int, duration_ms: int,
                   user_id: int | None, ip: str, request_id: str, error: str = "") -> None:
    from .main import redact_tokens   # ponytail: import w funkcji (main importuje applog)
    if _skip(method, path, status):
        return
    minute = utcnow().replace(second=0, microsecond=0)
    with _lock:
        c = _counters.setdefault(minute, [0, 0, 0, 0])
        c[0] += 1
        c[1] += 400 <= status < 500
        c[2] += status >= 500
        c[3] += duration_ms
        if status >= 400 or duration_ms > SLOW_MS:
            _requests.append(dict(at=utcnow(), method=method, path=redact_tokens(path)[:500],
                                  status=status, duration_ms=duration_ms, user_id=user_id,
                                  ip=ip[:64], request_id=request_id[:16], error=error[:4000]))


def record_job(*, job: str, fn: str, started_at: datetime.datetime, duration_ms: int,
               ok: bool, detail: str) -> None:
    with _lock:
        _jobs.append(dict(job=job[:60], fn=fn[:120], started_at=started_at,
                          duration_ms=duration_ms, ok=ok, detail=detail[:2000]))


def _alert(db, kind: str, title: str, body: str) -> None:
    now = time.monotonic()
    if now - _last_alert.get(kind, -ALERT_EVERY_S) < ALERT_EVERY_S:
        return
    _last_alert[kind] = now
    from .notifications import notify
    admins = list(db.scalars(select(User).where(User.is_active, User.role == Role.admin)))
    notify(db, admins, kind="system-error", title=title, body=body)


def flush(db) -> int:
    with _lock:
        reqs, jobs, counters = list(_requests), list(_jobs), dict(_counters)
        _requests.clear(); _jobs.clear(); _counters.clear()
    for minute, (total, c4, c5, dur) in counters.items():
        row = db.scalar(select(RequestCounter).where(RequestCounter.minute == minute))
        if row is None:
            db.add(RequestCounter(minute=minute, total=total, c4xx=c4, c5xx=c5, dur_ms_sum=dur))
        else:
            row.total += total; row.c4xx += c4; row.c5xx += c5; row.dur_ms_sum += dur
    db.add_all(RequestLog(**r) for r in reqs)
    db.add_all(JobRun(**j) for j in jobs)
    errors = [r for r in reqs if r["status"] >= 500]
    if errors:
        _alert(db, "request", f"Błąd serwera ({len(errors)}×)",
               f"{errors[0]['method']} {errors[0]['path']} → {errors[0]['status']}")
    failed = [j for j in jobs if not j["ok"]]
    if failed:
        _alert(db, "job", f"Zadanie tła nie powiodło się: {failed[0]['job']}/{failed[0]['fn']}",
               failed[0]["detail"][:300])
    db.commit()
    return len(reqs) + len(jobs)


def purge(db, days: int = RETENTION_DAYS) -> int:
    cutoff = utcnow() - datetime.timedelta(days=days)
    n = 0
    for model, col in ((RequestLog, RequestLog.at), (JobRun, JobRun.started_at),
                       (RequestCounter, RequestCounter.minute)):
        n += db.execute(delete(model).where(col < cutoff)).rowcount or 0
    db.commit()
    return n


async def applog_loop() -> None:
    def _once():
        with SessionLocal() as db:
            flush(db)
    while True:
        await asyncio.sleep(FLUSH_EVERY_S)
        try:
            await asyncio.to_thread(_once)
        except Exception:  # noqa: BLE001 — pętla nie umiera
            logger.exception("Zrzut dziennika serwera nie powiódł się")


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Mierzy czas i status każdego żądania; wyjątek = 500 z tracebackiem w dzienniku."""

    async def dispatch(self, request, call_next):
        import traceback
        start = time.perf_counter()
        error, status = "", 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception:
            error = traceback.format_exc()
            raise
        finally:
            from .security import client_ip
            record_request(method=request.method, path=request.url.path, status=status,
                           duration_ms=int((time.perf_counter() - start) * 1000),
                           user_id=getattr(request.state, "user_id", None),
                           ip=client_ip(request) or "", request_id=getattr(request.state, "request_id", ""),
                           error=error)
```

Uwagi dla implementera:
- Jeśli `from .main import redact_tokens` powoduje cykl przy imporcie `main` → przenieś `redact_tokens` (+ oba regexy) do nowego modułu `app/redact.py`, w `main.py` zostaw `from .redact import redact_tokens` (zachowaj publiczną nazwę `app.main.redact_tokens`, bo mogą jej używać testy — sprawdź grepem).
- Sprawdź sygnaturę `client_ip` w `app/security.py` (może wymagać innych argumentów) i dopasuj.
- Wyjątki w endpointach FastAPI zwykle kończą się 500 przez handler wyjątków, zanim dotrą do middleware — jeśli w teście 500 nie ma tracebacku, dodaj w `main.py` handler `@app.exception_handler(Exception)` tylko jeśli już istnieje podobny (sprawdź); w przeciwnym razie zostaw `error` puste dla takich przypadków i zanotuj w raporcie.

- [ ] **Step 6: Podpięcie**
  - `main.py`: `app.add_middleware(RequestLogMiddleware)` **przed** `app.add_middleware(RequestIDMiddleware)` w kodzie (Starlette: dodany później = zewnętrzny; `RequestIDMiddleware` musi ustawić `request.state.request_id` zanim nasz middleware go odczyta — więc RequestLog ma być WEWNĘTRZNY, czyli dodany WCZEŚNIEJ). Zweryfikuj testem, że `request_id` w logu nie jest pusty.
  - lifespan: `applog_loop` startuje zawsze (także gdy `run_background_jobs` = False) — utwórz task przed gałęzią `if not settings.run_background_jobs` i anuluj przy wyjściu w obu gałęziach. W testach lifespan może działać — pętla śpi 30 s, więc nie przeszkadza; jeśli testy mają flagę wyłączającą pętle tła, sprawdź, czy nie trzeba jej respektować.
  - `security.get_current_user`: przed każdym `return <user>` ustaw `request.state.user_id = <user>.id` (przy impersonacji — id użytkownika, który JEST widoczny w aplikacji, czyli zwracanego obiektu).
  - `jobs.job_loop`: wokół każdego `fn` mierz `time.perf_counter()` i `utcnow()` startu; po sukcesie `applog.record_job(..., ok=True, detail=repr(result)[:2000] if result else "")`, w `except` `ok=False, detail=traceback.format_exc()`.
  - `jobs.build_jobs`: `Job("applog_retention", 24 * HOUR, (applog.purge,))`.

- [ ] **Step 7: Run** `python -m pytest -q tests/test_applog.py tests/test_migration_chain.py tests/test_api.py` → PASS; `python -m alembic heads` → `log001`.

- [ ] **Step 8: Commit** `feat(monitor): dziennik błędnych/wolnych żądań, liczniki ruchu i przebiegi zadań tła`

---

### Task 2: API dziennika

**Files:**
- Create: `backend/app/routers/logs.py`
- Modify: `backend/app/main.py` (import + `include_router(logs.router)`; jeśli brak miejsca w limicie linii — w jednej linii z innymi)
- Test: `backend/tests/test_logs_api.py`

**Interfaces (Produces, HTTP, wszystko `admin_only`):**
- `GET /api/admin/logs/requests?status=&q=&user_id=&date_from=&date_to=&page=1&per_page=50` → `{"total": int, "items": [{"id","at","method","path","status","duration_ms","user_id","user_login","ip","request_id","error"}]}` — sortowanie `at desc`; `status`: `"4xx"` (400–499), `"5xx"` (≥500), `"slow"` (duration_ms > 1000), albo liczba (dokładny kod); `q` = `path ILIKE %q%`; `per_page ≤ 200`.
- `GET /api/admin/logs/traffic?hours=24` (1–168) → `[{"at": iso, "total", "c4xx", "c5xx", "avg_ms"}]` zagregowane do 5-minutowych kubełków (agregacja w Pythonie po pobraniu wierszy z zakresu — wolumen ≤ 10 080 wierszy).
- `GET /api/admin/logs/jobs` → `{"latest": [{"job","fn","started_at","duration_ms","ok","detail"}], "history": [... ostatnie 200 ...]}` — `latest` = najnowszy przebieg per (job, fn).
- `GET /api/admin/logs/client-errors` → ostatnie 200 z `client_errors` (`id, created_at, name, message, stack, url, user_agent`).

- [ ] **Step 1: Failing tests** `backend/tests/test_logs_api.py` — seed przez modele (`db_session.add(RequestLog(...))` itd.), potem:
  - admin: `requests?status=5xx` zwraca tylko 5xx; `status=slow` tylko > 1000 ms; `q=containers` filtruje ścieżkę; `user_login` wypełnione dla wpisu z `user_id` admina.
  - `traffic?hours=1` sumuje liczniki z jednego 5-min kubełka (dwa wiersze minutowe w tym samym kubełku → jeden punkt z sumą).
  - `jobs`: dwa przebiegi tej samej pary → w `latest` jeden, nowszy.
  - `client-errors` zwraca dodany `ClientError`.
  - użytkownik logistics (utwórz jak w `tests/test_watchers.py`) → 403 na każdy z 4 endpointów.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implementacja** `routers/logs.py` (`APIRouter(prefix="/api", tags=["monitor"])`, `admin_only` importowany jak w `routers/system.py`; login użytkownika przez `outerjoin(User, User.id == RequestLog.user_id)`; `page`/`per_page` przez `Query(ge=1)` / `Query(le=200)`).
- [ ] **Step 4: Run** `python -m pytest -q tests/test_logs_api.py tests/test_applog.py` → PASS.
- [ ] **Step 5: Commit** `feat(monitor): API dziennika — żądania, ruch, zadania tła, błędy frontu`

---

### Task 3: UI — podzakładki Monitora serwera

**Files:**
- Create: `frontend/src/i18n/features/monitor-logi.ts`
- Create: `frontend/src/pages/admin/logs/LogsRequests.tsx` (wykres ruchu + tabela + filtry + rozwijany wiersz)
- Create: `frontend/src/pages/admin/logs/LogsJobs.tsx`
- Create: `frontend/src/pages/admin/logs/LogsClientErrors.tsx`
- Create: `frontend/src/pages/admin/logs/MonitorTabs.tsx` (podzakładki: Zasoby = istniejący `MonitorPanel`, Żądania, Zadania tła, Błędy frontu; aktywna podzakładka w stanie lokalnym)
- Modify: `frontend/src/pages/admin/SystemTab.tsx` (render `MonitorTabs` zamiast `MonitorPanel`)
- Test: `frontend/src/pages/admin/logs/logs.dom.test.tsx`

**Interfaces (Consumes):** HTTP z Task 2 (kształty jak wyżej). `api.get` z `frontend/src/api.ts`, `useT` z `frontend/src/i18n`, `formatDateTime` / `formatNum` z `frontend/src/dates`.

**Wymagania:**
- Żądania: filtry `status` (select: wszystkie / 4xx / 5xx / wolne), `q` (tekst, debounce 300 ms albo przycisk „Szukaj”), zakres dat (`<input type="date">`). Tabela: czas, metoda, ścieżka, status (kolor: 5xx czerwony, 4xx bursztyn, wolne szare z „⏱”), czas ms, użytkownik, request-id. Klik w wiersz rozwija `<pre>` z `error` (jeśli pusty — „brak szczegółów”). Stronicowanie „Wcześniejsze / Nowsze”.
- Wykres ruchu 24 h: prosty SVG (słupki `total` na kubełek, na nich nałożone `c5xx` na czerwono) — bez nowych zależności; sprawdź, czy w repo jest już komponent wykresu (np. w `MonitorPanel.tsx` historia CPU/RAM) i reużyj jego wzorca.
- Zadania tła: kafelki z `latest` (nazwa `job/fn`, zielony „OK” / czerwony „Błąd”, „x min temu”, czas trwania); pod spodem tabela `history` (błędne wiersze wyróżnione, klik → `<pre>` z `detail`).
- Błędy frontu: tabela (czas, nazwa, komunikat, URL), klik → `<pre>` ze `stack`.
- Każda podzakładka ładuje dane dopiero po otwarciu; przycisk „Odśwież”. Odpowiedź o nieoczekiwanym kształcie (brak `items`/`latest`/tablicy) → pusty stan, nie wyjątek (patrz pamięć: ogólne mocki api w testach stron).
- Style: istniejące klasy (`.panel`, `.btn`, `.btn.secondary`, `.btn.small`, tabele z panelu System) — grep `frontend/src/styles`; nowe reguły minimalne, w pliku ≤ 500 linii.
- Teksty pl/en/pt w `monitor-logi.ts` (prefiks kluczy `log…`).

- [ ] **Step 1: Failing tests** `logs.dom.test.tsx` (mock `../../../api` jak w `pages/watch/watch.dom.test.tsx`, `useT` → klucz):
  - Żądania: po otwarciu podzakładki woła `/api/admin/logs/requests?…` i `/api/admin/logs/traffic?hours=24`; renderuje wiersz 500 z klasą błędu; klik w wiersz pokazuje `error`; zmiana filtra na `5xx` woła API z `status=5xx`.
  - Zadania tła: kafelek z `ok: false` ma oznaczenie błędu; klik w wiersz historii pokazuje `detail`.
  - Odpowiedź `{}` dla każdej podzakładki → brak wyjątku, widoczny pusty stan.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implementacja** (pliki ≤ 250 linii każdy).
- [ ] **Step 4: Run** `npx vitest run` (całość) i `npm run build` → PASS; `python scripts/check_file_lengths.py` → rc 0.
- [ ] **Step 5: Commit** `feat(monitor): przeglądarka dziennika — żądania, ruch, zadania tła, błędy frontu`

---

### Task 4: Weryfikacja i PR

- [ ] Pełny `python -m pytest -q` (backend), `npx vitest run`, `npm run build`, `alembic heads` → `log001`.
- [ ] Push `claude/monitor-logi`, `gh pr create` (opis: zakres, testy, uwaga o migracji `log001` i o tym, że dzwonek „system-error” podlega matrycy reguł powiadomień).

# Zlecenia spedycyjne — Plaster 1 (design, wersja zrewidowana)

**Data:** 2026-09-06
**Moduł:** #9 z serii usprawnień kolejki.
**Status:** zatwierdzony do implementacji. Plaster 1 z 3.

## ⚠️ Rewizja po diagnozie kodu

Pierwotny projekt zakładał nową encję `ForwardingRequest`. Diagnoza wykazała, że
**wielokontenerowy pipeline zlecenia + RFQ już istnieje** i jest kompletny:

- **`TransportJob`** (models.py) — „paczka kontenerów" z numerem, statusami
  `SZKIC→WYSLANE→ZLECONE→ANULOWANE`, pickup/delivery, `items` (`TransportJobContainer`),
  terminem odpowiedzi, SCFI, danymi agenta. Router `quotes.py` (807 linii): `create_job`,
  `send_job`, `submit_quote`, `choose_quote`, `cancel`/`reopen`, KPI, CSV.
- **`Quote`** — oferta spedytora per job (RFQ).
- Tworzenie joba **już wpięte w kolejkę**: multi-select → „💰 Nowa wycena" →
  `QuoteRequestModal({ containers, forwarders, onDone, onClose })` → POST `/transport-jobs`.

Wniosek: cały cykl kontener→RFQ→oferty→wystawienie **już działa** (moduł `wyceny`).
Nowa encja byłaby duplikatem (sprzeczne z CLAUDE.md „nie powielać, deps.py to jedno źródło").

**Decyzja: opcja A — reużyć `TransportJob`.** Plaster 1 to cienki dodatek: brakuje tylko
**skupionego widoku „kolejka do zlecenia"** (które aktywne kontenery nie mają jeszcze joba)
+ ręcznej flagi.

## Zakres Plastra 1

Nowy osobny widok „Zlecenia spedycyjne" (route `/zlecenia-spedycyjne`, menu Logistyka):
lista kontenerów wymagających wystawienia zlecenia → multi-select → **reużycie istniejącego
`QuoteRequestModal`** (tworzy `TransportJob`). Plus ręczna flaga „do zlecenia".

**Poza Plastrem 1 (bo już działa lub później):** RFQ/oferty/wybór/wystawienie (moduł `wyceny`),
ścieżka e-mail do spedytora bez konta, PDF, mostek do `TransportOrder`.

## Rozstrzygnięte: Plaster 2 (RFQ) = istniejące `wyceny` (decyzja D11, 2026-09-24)

Pytanie A/B „RFQ jako osobny byt czy istniejące wyceny” jest **zamknięte na A**:
Plaster 2 konsumuje istniejące wyceny (`TransportJob` + `Quote`). Wybrana oferta
(`choose_quote`) staje się zleceniem. **Nie** tworzymy osobnej encji RFQ, bo byłaby
duplikatem pipeline'u. Praktyka już to zakłada: #414 (tranzyt 47 → auto-SZKIC wyceny)
reużywa `TransportJob`/`Quote`.

## Reguła kolejki „Do zlecenia"

Kontener wchodzi do kolejki, gdy:
- jest **aktywny** (`status not in Container.FINISHED`),
- **nie należy** do żadnego **aktywnego** `TransportJob` (status `SZKIC` lub `WYSLANE`;
  `ZLECONE`/`ANULOWANE` = zamknięte, kontener może wrócić),
- **oraz** (`needs_forwarding == true` **lub** `forwarder_id is null`),
- scoping per spółka (użytkownik widzi tylko swoje spółki).

## Zmiany

### Backend
- **`Container.needs_forwarding`** — `Mapped[bool]`, default `False`. Migracja alembic
  (dodanie kolumny; wzór: `backend/migrations/versions/*`, `alembic upgrade head` w Dockerfile).
- **`GET /api/containers/to-forward`** (router `containers.py`, dostęp `editors` =
  admin/logistics) → `list[ContainerOut]` wg reguły wyżej; scoping przez `deps.py`
  (`scope_containers`/`check_container_access` — jak istniejące endpointy).
- **`PATCH /api/containers/{id}/needs-forwarding`** body `{value: bool}` → ustawia flagę,
  `check_container_access`, zwraca zaktualizowany `ContainerOut`.
- **Reużycie** `create_job`/`QuoteRequestModal` — zero nowej logiki zleceń.

### Frontend
- **`pages/ForwardingRequestsPage.tsx`** — route `/zlecenia-spedycyjne`.
  - Fetch `GET /api/containers/to-forward` (+ `GET /api/forwarders` dla modala).
  - Tabela: nr kontenera (link do `/kontenery/:id`), port/pochodzenie, magazyn/cel,
    ETA/awizacja (`formatDate`), checkbox zaznaczenia, przycisk flagi „do zlecenia"
    (toggle `needs_forwarding`).
  - Multi-select → **„Utwórz zlecenie z zaznaczonych"** → otwiera reużyty
    `QuoteRequestModal` z zaznaczonymi kontenerami; `onDone` → refetch kolejki.
  - Stany: `Skeleton`/`LoadError`/empty; ciche błędy → `setError`/toast (wg audytu).
- **`App.tsx`** — link w sekcji `Logistyka` (`show: some('admin','logistics')`) + `<Route>`
  z `Guarded ok={role admin||logistics}`.
- **`types.ts`** — `needs_forwarding: boolean` w `Container`.
- **i18n** — klucze etykiet (PL/EN/PT) dla tytułu, kolumn, przycisków.

## Testy

- **Backend** (`backend/tests/test_forwarding_queue.py`):
  - reguła `to-forward`: kontener bez spedytora i bez joba → jest; z aktywnym `TransportJob`
    (SZKIC/WYSLANE) → znika; po `ANULOWANE`/`ZLECONE` → wraca; flaga `needs_forwarding`
    dodaje kontener mimo przypisanego spedytora; scoping per spółka (obca spółka niewidoczna).
  - `PATCH needs-forwarding` przełącza flagę i respektuje `check_container_access`.
- **Frontend** (`frontend/src/forwarding-queue.dom.test.tsx`):
  - render kolejki z mockowanego API; multi-select + „Utwórz zlecenie" otwiera modal;
    toggle flagi wywołuje PATCH i odświeża.

## Dotknięte pliki

- Backend: `app/models.py` (+`needs_forwarding`), nowa migracja, `app/routers/containers.py`
  (+2 endpointy), `app/schemas.py` (jeśli trzeba body dla PATCH). Scoping w `deps.py` — reużycie.
- Frontend: `pages/ForwardingRequestsPage.tsx` (nowy), `App.tsx` (route+link), `types.ts`,
  `i18n.ts`, test DOM.

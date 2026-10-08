# Tracking kontenerów: powiadomienia, kolumny trackingowe w Excelu, konflikty sync

Data: 2026-09-02 · Repo: TIMPORYE · Ustalone w 30 pytaniach (sesja brainstormingu)

## Kontekst

Aplikacja śledzi kontenery przez SafeCube (Sinay) i synchronizuje kolejkę z arkuszem
Excel, który operatorzy trzymają jako główne miejsce pracy. Dziś tracking **zapisuje
dane, ale o niczym nie informuje** — operator musi sam zauważyć, że statek wypłynął,
ETA się przesunęła albo kontener zniknął z API armatora. Równolegle Excel nie widzi
żadnych danych trackingowych, więc ta sama informacja jest przepisywana ręcznie.

Cel: zamknąć pętlę. Zdarzenia z trackingu mają **same** trafiać do ludzi (e-mail) i do
arkusza (kolumny read-only), a sytuacje wymagające decyzji człowieka — błędy trackingu
i konflikty sync — mają mieć **jedno widoczne miejsce** zamiast ginąć w logach.

## Co już istnieje (i czego NIE budujemy)

Zwiad wykazał, że fundament jest gotowy. Reużywamy:

| Element | Gdzie | Rola w tej zmianie |
|---|---|---|
| `TrackingEvent` + `UniqueConstraint(container_id, event_code, occurred_at, location)` | `backend/app/models.py:599` | naturalny klucz deduplikacji powiadomień |
| `sync_all()`, `sync_container()`, `apply_result()` | `backend/app/tracking/service.py` | miejsce wpięcia detekcji zdarzeń |
| `tracking_loop()` | `backend/app/main.py:503` | pętla do zmiany na adaptacyjną |
| `Container.tracked_at`, `tracking_error` | `models.py:324+` | świeżość i błędy — gotowe pola |
| `send_html_email()`, `_submit`, `mail_html.esc()` | `backend/app/notifications.py`, `mail_html.py` | wysyłka poza ścieżką żądania |
| `HEADER_MAP`, `_map_headers()` | `backend/app/routers/imports.py:39` | mapowanie po nagłówku (odporne na sort/przestawienie kolumn) |
| three-way merge: `container_baseline()`, `_process_row()`, `reconcile_queue()`, `WRITABLE_FIELDS` | `imports.py:281-410` | dokładamy tylko obsługę konfliktu |
| `_load_workbook()`, `_parse_rows()`, `_pick_sheet()` (openpyxl) | `imports.py:99-139` | odczyt wgranego arkusza |
| `POST /api/import/containers` (upload XLSX) | `imports.py` | wzorzec endpointu uploadu |
| `VoyageProgress`, `TrackingPage.tsx` | `frontend/src/pages/` | istniejący UI trackingu |

**Transport pliku: ręczny upload/download w panelu.** Żadnej automatyki po stronie
transportu — bez n8n, bez Microsoft Graph, bez udziału SMB. Operator pobiera arkusz,
edytuje w Excelu, wgrywa z powrotem. Zero zewnętrznej infrastruktury i zero zależności
od Azure (zgodne z Fazą 3). Cena: ktoś musi kliknąć — nie ma cyklicznego syncu.

**Round-trip zachowujący formatowanie.** Zamiast generować arkusz od zera (co kasuje
formatowanie, filtry i kolumny dodane przez użytkownika), pracujemy na **wgranym pliku**:
odczyt → dry-run → zapis punktowy w komórki kolumn trackingowych → zwrot poprawionego
pliku do pobrania. Jeden przebieg obsługuje oba kierunki. Wymaga `load_workbook()` bez
`read_only=True` dla ścieżki zapisu (istniejący `_load_workbook` czyta read-only —
potrzebny drugi wariant).

**Odpada wraz z rezygnacją z automatyki:** webhooki o zmianie pliku, debounce edycji,
odnawianie subskrypcji, wykrywanie blokady pliku otwartego w Excelu, `file_mtime` jako
rozstrzygacz konfliktu.

**Model danych bez zmian.** Nie ma bytu `Delivery` — dane dostawy leżą płasko na
kontenerze (`delivery_note`, `incoming_delivery_no`, `order_numbers`). „Opiekun dostawy"
= **spedytor z `TransportOrder`** (relacja 1:N do kontenera, już istnieje).

## Zakres — trzy niezależne PR-y

### PR 1 — Powiadomienia o zdarzeniach trackingu

Nowy moduł `backend/app/tracking/notify.py` wołany z `apply_result()`.

**Wyzwalacze** (wszystkie pięć):
- `DEPART` — kontener wypłynął
- `ARRIVE` / `DISCHARGE` — statek w porcie docelowym
- `GATE_OUT` — kontener opuścił port
- **zmiana ETA** o ≥ próg (nowe `tracking_eta_alert_days: int = 2` w `config.py`)
- **problemy** — `tracking_error`, kontener nieznany w SafeCube (404), konflikt sync

**Reguły:**
- Kanał: **e-mail** przez istniejące `notify()` (`notifications.py:202`), które jednym
  wywołaniem robi in-app + e-mail + Teams. Nie budujemy osobnej ścieżki mailowej.
- Wysyłka **natychmiastowa**, osobny mail na zdarzenie — bez digestu.
- **Tylko zdarzenia rzeczywiste** (`is_estimated=False`). Wyjątek: zmiana ETA jest
  z natury prognozą i powiadamia mimo to, od progu `tracking_eta_alert_days`.
- Adresaci: `container_watchers()` (`notifications.py:274`) = logistyka spółki + admini
  + spedytor + agencja celna. Pokrywa i „opiekunów", i „listę zbiorczą" — **bez** nowego
  ustawienia z listą adresów.
- Deduplikacja: **bez nowej tabeli**. `apply_result` wstawia wyłącznie zdarzenia
  nieobecne w bazie (chroni je `UniqueConstraint` na `tracking_events`), więc świeżo
  wstawiony wiersz jest dowodem, że jeszcze nie powiadamialiśmy. Alert o błędzie
  trackingu wysyłany **raz** — warunkiem jest pusty `Container.tracking_error`;
  odpytywanie trwa dalej.
- Jedyne nowe ustawienie: `tracking_eta_alert_days: int = 2`.

### PR 2 — Kolumny trackingowe w arkuszu + adaptacyjny scheduler

**Kolumny (read-only, apka → Excel):** dopisujemy do `HEADER_MAP` i do zapisu
zwrotnego, **poza** `WRITABLE_FIELDS` w obecnym znaczeniu — nigdy nie są czytane
z powrotem, więc edycja w Excelu ich nie rusza:

| Nagłówek | Źródło |
|---|---|
| `STATUS TRACKING` | ostatni `TrackingEvent.event_code` |
| `OSTATNIE ZDARZENIE` | `description` + `location` |
| `DATA ZDARZENIA` | `occurred_at` (data) |
| `ETD` | `Container.etd` (już wypełniane z pierwszego DEPART) |
| `PORT` | `Container.port` |
| `AKTUALIZACJA` | `Container.tracked_at` |
| `BŁĄD TRACKINGU` | `Container.tracking_error` |

Jeden wiersz = **jeden kontener** (dostawy zwinięte) — zgodne z istniejącym arkuszem.
Adresowanie komórek po nagłówku + numerze kontenera, punktowo (`_map_headers` już to
robi przy odczycie — ta sama mapa służy zapisowi). `ETA` i `STATEK` zostają jak są
(dwukierunkowe), bo już tak działają. Brakujące kolumny trackingowe **dopisujemy na
końcu wiersza nagłówka**, żeby stary arkusz zadziałał bez ręcznego przygotowania.

**Scheduler:** `tracking_loop()` przestaje traktować wszystkie kontenery jednakowo.
Zamiast stałego `tracking_interval_hours` — próg zależny od bliskości ETA
(nowe `tracking_interval_near_eta_hours: float = 3.0`, `tracking_near_eta_days: int = 2`).
Kontener kończy cykl po **GATE_OUT** (dziś: po `arrived`).

**Ręczne odświeżenie:** endpoint per kontener wołający `sync_container_bg()`, limit
1×/5 min na kontener, przycisk w `ContainerPage.tsx`.

### PR 3 — Konflikty sync + ekran „Stan synchronizacji"

**Zmiana reguły konfliktu.** Dziś `_process_row()` (`imports.py:386`) rozstrzyga
konflikt `e≠b ∧ a≠b ∧ e≠a` po `file_mtime` — nowsza zmiana cicho wygrywa. Przy ręcznym
uploadzie `file_mtime` i tak przestaje być wiarygodny (data pliku ≠ data edycji pola),
więc ta gałąź znika w całości.
Nowa reguła: **pole zostaje wstrzymane** (żadna strona nie nadpisuje), a konflikt
trafia do nowej tabeli `sync_conflict` (`container_id`, `field`, `excel_value`,
`app_value`, `detected_at`, `resolved_at`, `resolved_by`). Baseline dla tego pola
pozostaje stary, więc konflikt utrzymuje się aż do rozstrzygnięcia.

**Wiersze odrzucone.** Dziś niepoprawny numer kontenera jest cicho pomijany
(`imports.py:334`, tylko `logger.warning`). Nowo: wiersz trafia do raportu odrzuceń
z **propozycją najbliższego dopasowania** (odległość Levenshteina do istniejących
numerów, `difflib.get_close_matches` ze stdlib — bez nowej zależności).

**Przepływ uploadu (dwa kroki, bez trzymania pliku na serwerze):**
1. `POST /api/sync/preview` — wgrany XLSX, zwraca diff: co się zmieni, co w konflikcie,
   co odrzucone. Nic nie zapisuje.
2. `POST /api/sync/apply` — ten sam plik + potwierdzenie; zapisuje do bazy i **zwraca
   poprawiony XLSX** z uzupełnionymi kolumnami trackingowymi do pobrania.

Plik wędruje w żądaniu dwa razy zamiast leżeć w sesji — prościej i bez stanu.
`require_sync_token()` nie jest tu potrzebny: to zwykły endpoint panelu z autoryzacją
użytkownika, jak istniejący `POST /api/import/containers`.

**Ekran „Stan synchronizacji"** (`frontend/src/pages/SyncStatusPage.tsx`): historia
cykli sync, lista konfliktów z wyborem strony, lista odrzuconych wierszy z podpowiedzią,
kontenery z `tracking_error`. Jedno miejsce — bez badge'y rozsianych po kolejce.

**UI trackingu:** `ContainerPage.tsx` dostaje pełną oś czasu `TrackingEvent`
(kod, opis, miejsce, statek, data, rzeczywiste vs prognoza) — dziś jest tylko
`VoyageProgress` w kolejce.

## Weryfikacja

Testy w `backend/tests/`, pytest, uruchamiane z katalogu `backend`: `python -m pytest tests -q`.

| PR | Test | Co sprawdza |
|---|---|---|
| 1 | `test_tracking_notify.py` | DEPART wysyła raz; drugi cykl z tym samym zdarzeniem nie wysyła; zdarzenie `is_estimated` nie wysyła; ETA +1 dzień milczy, +3 dni wysyła; 404 alertuje raz |
| 2 | `test_tracking.py` (rozszerzenie) | kontener blisko ETA odpytany w krótszym cyklu; kontener po GATE_OUT wypada z kolejki; limit ręcznego odświeżenia |
| 2 | `test_sync.py` (rozszerzenie) | kolumny trackingowe zapisane do zwróconego arkusza; edycja tych kolumn w Excelu **nie** wraca do bazy; arkusz bez kolumn trackingowych dostaje je dopisane |
| 3 | `test_sync.py` (rozszerzenie) | konflikt wstrzymuje pole (ani Excel, ani apka nie wygrywa) i tworzy `sync_conflict`; baseline niezmieniony; `preview` nic nie zapisuje; zły numer daje propozycję dopasowania |

End-to-end: `tracking_provider=mock`, przejechać cykl trackingu (mail wychodzi raz),
potem w panelu wgrać arkusz → obejrzeć diff → zatwierdzić → pobrać zwrócony plik
i sprawdzić, że kolumny trackingowe są uzupełnione, a formatowanie oryginału zachowane.
Ekran „Stan synchronizacji" pokazuje wstrzymany konflikt.

## Backlog: kontenery tranzytowe (osobny moduł, po PR 1–3)

Ustalone 2026-09-02, do rozpisania we własnym specu — **nie wchodzi** do PR 1–3.

- **Czym są:** kontenery obsługiwane **poza główną kolejką do naszego magazynu**.
  Najczęściej spółki ACME, ale przynależność do spółki ich nie definiuje — definiuje
  je cel: nie jadą do nas.
- **Stan dzisiejszy:** nie istnieją w systemie w żadnej postaci. Nie ma ich w pliku
  Excel, nie ma w bazie — są zarządzane wyłącznie mailowo. **Brak danych do migracji
  i brak rekordów do sklasyfikowania.**
- **Wejście danych:** ręcznie w panelu (reużycie `POST /api/containers`). Bez arkusza,
  bez syncu, bez parsowania maili.
- **Widok:** własna zakładka w panelu obok istniejących. Zakładki są dziś zaszyte
  w `frontend/src/pages/QueuePage.tsx:30` (`type Module`, `MODULE_CODE`,
  `MODULE_WAREHOUSE`) — nie są generowane ze spółek, więc dojdzie tam nowy wpis.
- **Precedens do naśladowania:** moduł DLT nie jest spółką, tylko `ACME` + filtr
  magazynu (`MODULE_WAREHOUSE`). Tranzyt to ten sam wzorzec odwrócony — „poza naszym
  magazynem" zamiast „magazyn = DLT".
- **Do rozstrzygnięcia w osobnej rundzie:** czym tranzyt jest odróżniony w danych
  (brak `warehouse_id` / dedykowany magazyn / nowa flaga na `Container`), jakie pola
  są wymagane, co z odprawą celną i demurrage, kto go obsługuje.
- **Co działa za darmo:** tracking SafeCube pyta po numerze kontenera niezależnie od
  spółki, magazynu i pliku — tranzyt wpięty w kolejkę od razu dostaje śledzenie
  i powiadomienia z PR 1.

## Ustalenia poza zakresem

- SMS i Teams jako kanały powiadomień (infrastruktura jest, decyzja: e-mail wystarczy)
- Automatyczny sync pliku w tle: n8n, Microsoft Graph / SharePoint, udział SMB
  (transport jest ręczny; wrócić, jeśli klikanie zacznie uwierać)
- Istniejące endpointy `/api/import/sync*` i `require_sync_token()` zostają nietknięte —
  nie usuwamy ich w tej zmianie, ale nowy przepływ ich nie używa
- Model `Delivery` (dane dostawy zostają płasko na kontenerze)
- Digest / okna ciszy (powiadomienia natychmiastowe; wrócić, jeśli skrzynki zaczną tonąć)
- Flaga „N kontenerów → 1 dostawa" jako sytuacja podejrzana — wymaga najpierw ustalenia,
  po czym rozpoznajemy tę samą dostawę na dwóch kontenerach

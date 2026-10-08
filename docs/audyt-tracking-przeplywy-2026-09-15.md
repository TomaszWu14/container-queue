# Audyt logiki przepływów trackingu — 2026-09-15

Trzy równoległe soczewki: ingest danych (SafeCube/AIS→baza), semantyka dat i zakresów,
konsumpcja we froncie. Poniżej znaleziska po weryfikacji, posortowane wg wagi.

## KRYTYCZNE

**K1. Sync Excela nadpisuje `notify_date` z pominięciem reguły zamrożenia planu**
`routers/imports.py:317-389` pisze `notify_date`/`eta` przez `setattr`, omijając `planning.py`
(jedyne miejsce z regułą zamrożenia). Kontener POTWIERDZONY ze spedycją dostaje z arkusza
nową datę, ale `planning_status` zostaje POTWIERDZONE — liczy się do limitu dziennego pod
terminem, którego nikt nie uzgodnił. **Fix:** sync przy zmianie `notify_date` na kontenerze
POTWIERDZONYM woła `reset_plan` (albo odmawia nadpisania z konfliktem do ręcznej decyzji).

**K2. Dedup zdarzeń trackingowych gubi korekty `is_estimated`**
`tracking/service.py:94-110`: zdarzenie o tym samym `(event_code, occurred_at, location)`
nigdy nie jest aktualizowane. Prognozowany DEPART potwierdzony przez armatora tą samą datą
zostaje „szacowany" na zawsze → powiadomienie „kontener wypłynął" nigdy nie wychodzi
(`notify.py:44` odrzuca `is_estimated`). **Fix:** update-path dla istniejącego klucza
(przynajmniej `is_estimated` i opis).

**K3. Trasy statków przez antymerydian rysują fałszywą kreskę przez całą mapę**
`TrackingPage.tsx:50-53` + polyline trasy: brak wrap-around przy przejściu 180°/-180°
(trasy pacyficzne). **Fix:** tnij polyline na segmenty przy skoku |Δlon|>180°.

## WAŻNE

**W1. Jedna zła wiadomość AIS ubija całą sesję websocket** — `ais.py:206` commit bez
try/except; kolizja `TrackedVessel.mmsi` (statek zmienił nazwę) → IntegrityError → backoff
do 15 min i utrata pozycji WSZYSTKICH statków. Fix: try/rollback per wiadomość.

**W2. Geofence bez histerezy — Gdańsk/Gdynia ~8 Mm od siebie przy promieniu 15 Mm**
(`geo.py:19,73-81` + `ais.py:178-193`): statek na redzie oscyluje między portami,
generując serię fałszywych „wszedł/wyszedł" + spam powiadomień. Fix: histereza
(wyjście dopiero po >X Mm od portu wejścia) albo mniejszy promień dla sąsiadujących.

**W3. Dwa źródła „dziś" w backendzie** — `is_delayed`/dashboard liczą `utcnow().date()`,
a `queue_view` (okno domyślne), `confirm_plan` i `_derive_status` importu — lokalne
`date.today()`. Na hoście poza UTC granica dnia rozjeżdża się między miejscami.
Fix: wszędzie `utcnow().date()`.

**W4. Front „dziś" lokalnie vs backend UTC** — baner „dziś" w kolejce (`todayISO()`,
zegar ścienny) vs backendowe UTC: w oknie 0:00–2:00 czasu PL kafelki dziś/jutro
i baner mogą się nie zgadzać. Świadoma decyzja frontu — do decyzji, które „dziś" rządzi.

**W5. `is_delayed` ślepy na kontener utkwiony w porcie** — ETA liczona tylko dla
ZAPOWIEDZIANY/W_TRANSPORCIE (`models.py:525`); W_PORCIE z minioną ETA i bez `notify_date`
nigdy nie zapala flagi. Do decyzji biznesowej (może celowe), ale brak sygnału „utknął".

**W6. ETD zamrażane pierwszą wartością** (`service.py:61-69`) — błędna/prognozowana data
z pierwszego DEPART nie ma ścieżki korekty.

**W7. TrackingPage bez seq-guarda** — wyścig między interwałowym `load()` a pollingiem
`syncNow()`: starsza odpowiedź może nadpisać nowszą (ContainerPage ma wzorcowy `loadSeq`
— skopiować).

**W8. Cichy fail warstwy AIS na mapie** — `/tracking/vessels` i `/weather` z
`.catch(()=>{})`: awaria = mapa bez statków bez żadnego komunikatu.

**W9. Badge klastra „+N" gubi się dla nie-reprezentanta** (`TrackingPage.tsx:180-191`
vs `423-427`) — lookup po współrzędnych aktywnego punktu nie trafia w klucz grupy.

## DROBNE

- `vessel_positions` bez retencji — tabela rośnie bez ograniczeń (`ais.py:168`).
- `normalize_name` nie łapie typograficznego apostrofu/typów kontenera bez separatora —
  statek cicho się nie dopasowuje (`ais.py:37-48`).
- Demurrage: dni kalendarzowe zamiast roboczych (repo ma `CalendarDay` — nieużyty tu);
  `demurrage_free_days=None` = temat całkiem cichy, brak domyślnej wartości.
- Retry po trwałym błędzie SafeCube: kontener-fail wraca na czoło kolejki co cykl
  (circuit breaker łagodzi, ale slot się marnuje).
- `ContainerTimeline`: `done` liczone jednym `Date.now()` na render — długo otwarta
  strona nie „domyka" minionych wpisów.
- `clusterDist` zakłada stałą szerokość SVG; reset replay tylko po zmianie id statku.
- Kontenery/PO bez `notify_date` niewidoczne w każdym trybie zakresu kolejki poza
  „Wszystko" (NULL nie wchodzi w BETWEEN) — spójne ze stanem plastra PO, ale warto wiedzieć.
- Niespójne utcnow: `_predicted_late` używa deprecated `datetime.utcnow()`, weather-cache
  jako jedyny aware `now(timezone.utc)`.

## Co jest SOLIDNE

- „Status tylko w przód" scentralizowany w `apply_result` — jedna ścieżka dla sync i Track now.
- Circuit breaker + deadline + kolejność „najdawniej synchronizowane" w `sync_all`.
- Izolacja per-firma konsekwentnie przez `scope_containers` we wszystkich endpointach trackingu.
- `is_delayed` jako computed property (nigdy w bazie) + jedno źródło prawdy dla frontu;
  brak off-by-one (ostro `< today`); zakresy wszędzie inclusive spójnie.
- `planning.py` jako jedyne miejsce reguły zamrożenia (poza wyjątkiem K1) + `eta_shift_days`
  liczone względem `planning_eta_at_send`.
- `parseServerTs` (dokleja `Z` do naiwnego UTC) — udokumentowany fix, konsekwentnie używany;
  pętle tła nie umierają (poprawny re-raise CancelledError, backoff z jitterem).

## Proponowana kolejność napraw

1. K1 (integralność planu — realne ryzyko operacyjne przy każdym sync z arkusza),
2. K2 (gubione powiadomienia o wypłynięciu), W1+W2 razem (stabilność AIS),
3. K3+W7+W8+W9 (jeden PR „mapa trackingu"),
4. W3 (ujednolicenie „dziś" w backendzie — tania, systemowa poprawka),
5. reszta wg okazji.

---

## Status napraw (2026-09-15, wieczór)

Wszystkie pozycje z kolejności napraw dowiezione i na produkcji:
- K1 → poprawka (reset planu przy zmianie notify_date z sync)
- K2+W6 → poprawka (update-path zdarzeń + korekta ETD chroniona audytem)
- W1+W2 → poprawka (rollback per wiadomość AIS + histereza z pasmem przełączenia 2 NM)
- K3+W7+W8+W9 → poprawka (segmenty tras, seq-guard, komunikat awarii warstwy, klucz klastra)
- W3 → poprawka (utcnow().date() wszędzie)

Otwarte świadomie: W4 (front „dziś” lokalnie — decyzja UX), W5 (is_delayed a utknięcie
w porcie — do decyzji biznesowej), minory (retencja vessel_positions, normalize_name,
demurrage dni robocze, done w ContainerTimeline).

# Plan dostaw — data dostawy i cykl potwierdzeń ze spedycją

Data: 2026-09-02
Status: zatwierdzony do implementacji
Zakres: podsystem **B** z dekompozycji „planowanie dostaw" (patrz „Kontekst i dekompozycja")

## Problem

`Container.notify_date` pełni dziś dwie role naraz: jest planowaną datą dostawy i kluczem,
po którym kontener trafia do konkretnego dnia kolejki (razem z limitem dziennym, domyślnie 7).

Skutki:

- Nie widać różnicy między datą zgadniętą przez nas a uzgodnioną ze spedycją. Limit dzienny
  liczy jedno i drugie tak samo, więc „7 na dzień" nie znaczy siedmiu realnych ciężarówek.
- Spedycja potwierdza dziś przez formularz awizacyjny **fakt dostawy i dane kierowcy, ale nie datę**
  (`backend/app/routers/avizo.py`, `frontend/src/pages/AvizoFormPage.tsx`).
- Nie ma śladu, kto i kiedy uzgodnił datę — a to jest przedmiot późniejszych sporów.

## Cel

Kontener przechodzi jawny cykl: **propozycja → wysłane do spedycji → potwierdzone**.
Dopiero `POTWIERDZONE` liczy się do limitu dziennego i znaczy „zaplanowany w 100%".

## Kontekst i dekompozycja

Pierwotny zakres obejmował siedem niezależnych podsystemów. Rozbicie i kolejność:

| # | Podsystem | Status |
|---|---|---|
| A | Widok kolejki (wysokość wierszy, widok tygodniowy/dwutygodniowy, zwijanie) | osobny spec |
| **B** | **Data dostawy i cykl potwierdzeń** | **ten dokument** |
| C | Moduł planistyczny (zaznaczanie grupowe, jedna data dla N kontenerów, estymacja ML) | osobny spec, wymaga B |
| D | Awizacja godzinowa + SMS + kod kierowcy | osobny spec, wymaga C |
| E | Statusy rampowe (Podstawiony / Rozładowany / Przyjęty / Rozliczony) | osobny spec, wymaga D |
| F | Faktury transportowe od spedycji | osobny spec, niezależny |
| G | Ranking pilności + priorytet ręczny | osobny spec, niezależny |

### Co już istnieje w repo (ustalone rozpoznaniem)

- **Rola spedytora działa.** `Role.forwarder` (`models.py:17-24`), `User.forwarder_id` (N:1 — kilku
  użytkowników na jedną firmę). Izolacja danych w `deps.py` jest **fail-closed**: `scope_containers`
  zawęża po `Container.forwarder_id`, a użytkownik bez `forwarder_id` dostaje 403, nie pusty widok.
- **Spedytor loguje się i widzi własną kolejkę** (`/kolejka` z zawężeniem), a także Spedycja, Wyceny,
  Śledzenie, Reklamacje, Kalendarz, Dashboard (`routing.tsx:57-78`, `App.tsx:288-298`).
- **Awizacja tokenowa działa** — mail do spedytora + publiczny formularz bez logowania,
  token SHA-256, ważność 14 dni.
- **`proposed_delivery_date` istnieje w modelu, ale jest nieużywane.** Ten projekt go **nie używa** —
  patrz „Decyzje projektowe".
- **Zaproszenia użytkowników są półręczne** — `POST /api/users` z `send_invite` ustawia hasło
  tymczasowe i `must_change_password`, ale mail otwiera się przez `mailto` w Outlooku
  (`admin.py:123-160`, `UsersTab.tsx`). Serwerowej wysyłki brak.

## Model danych

Do `Container` dochodzi sześć kolumn. **`notify_date` pozostaje kluczem kolejki bez zmian.**

| Kolumna | Typ | Rola |
|---|---|---|
| `planning_status` | enum `PROPOZYCJA` / `WYSLANE` / `POTWIERDZONE`, domyślnie `PROPOZYCJA`, indeks | stan cyklu |
| `notify_date_manual` | `bool`, domyślnie `False` | człowiek wpisał datę ręcznie — API jej nie nadpisuje |
| `planning_sent_at` | `datetime`, nullable | kiedy poszło do spedycji (tekst nagłówka) |
| `planning_confirmed_at` | `datetime`, nullable | kiedy spedycja potwierdziła |
| `planning_confirmed_by_id` | FK → `users`, nullable | kto potwierdził; `NULL` gdy potwierdzenie przez token |
| `planning_eta_at_send` | `date`, nullable | zdjęcie ETA w chwili zamrożenia |

### Dlaczego `planning_eta_at_send`, a nie flaga alertu

Alert „ETA przesunięta o X dni" **liczymy w locie** jako `eta - planning_eta_at_send`, zamiast trzymać
flagę w bazie. Flaga wymagałaby synchronizacji przy każdej zmianie ETA i cicho rozjeżdżałaby się
z rzeczywistością. Punkt odniesienia nie wymaga niczego.

Alert pokazujemy, gdy `planning_eta_at_send` jest ustawione i różnica jest niezerowa.

## Reguła zamrożenia daty

Jedna reguła, **jedno miejsce w kodzie** — funkcja w warstwie domenowej, wołana przez tracking:

```
ETA z API przelicza notify_date = eta + 4 dni
wtedy i tylko wtedy, gdy:
    planning_status == PROPOZYCJA  AND  notify_date_manual == False
```

We wszystkich pozostałych przypadkach zmiana ETA **nie rusza daty** — podnosi wyłącznie alert.

Konsekwencje:

- `POST /api/containers/plan/send` zamraża datę i robi zdjęcie ETA.
- Ręczna edycja daty ustawia `notify_date_manual = True` i zamraża datę także w stanie `PROPOZYCJA`.
- Kontener nigdy nie zmienia sam dnia w kolejce po uzgodnieniu ze spedycją.

Domyślne `eta + 4` obowiązuje przy nadaniu/aktualizacji ETA. Kontener bez ETA zostaje bez
`notify_date` i nie pojawia się w kolejce — tak jak dziś.

## Limit dzienny

`GET /api/queue` liczy dziś `used` jako kontenery nie-zakończone i nie-tranzytowe
(`containers.py:823-824`). Dochodzi **jeden** warunek: `planning_status == POTWIERDZONE`.

Propozycje i wysłane są w dniu widoczne, ale **nie zajmują miejsc**. `over_limit` liczy się
wyłącznie z potwierdzonych.

## Widok kolejki

W obrębie każdego dnia kontenery grupują się pod zwijanymi nagłówkami sekcji, w kolejności:

1. **Potwierdzone (N)**
2. **Wysłane do spedycji (N)**
3. **Propozycje (N)**

Sekcje puste są ukryte. Stan zwinięcia zapisuje się w `localStorage` — tym samym wzorcem, co
istniejące `hiddenCols` w `QueuePage.tsx`.

**Filtr „zaplanowane / niezaplanowane" jest realizowany jako zwijanie tych sekcji**, nie jako
osobny mechanizm filtrowania. Jeden model interakcji zamiast dwóch.

Na wierszu kontenera w stanie `WYSLANE` widnieje adnotacja „Wysłany do spedycji {data}, czeka na
potwierdzenie". Przy niezerowym przesunięciu ETA — adnotacja „ETA przesunięta o {X} dni".

### Bloker edycji

Próba zmiany `notify_date` na rekordzie `POTWIERDZONE` wymaga potwierdzenia w dialogu
(„spedycja potwierdziła tę datę — na pewno chcesz zmienić?"). W stanach `PROPOZYCJA` i `WYSLANE`
edycja jest bez pytania.

Zmiana daty potwierdzonego rekordu **cofa `planning_status` do `PROPOZYCJA`**, czyści
`planning_confirmed_at` / `planning_confirmed_by_id` i zwalnia miejsce w limicie. Bez tego
zostałaby data uznana za uzgodnioną, której spedycja nigdy nie widziała.

## Wysyłka i potwierdzenie

### Wysyłka

`POST /api/containers/plan/send` — body: lista `container_ids`. Dla każdego kontenera:
ustawia `planning_status = WYSLANE`, `planning_sent_at = teraz`, `planning_eta_at_send = eta`,
po czym powiadamia spedycję.

Kontener bez przypisanego spedytora nie może zostać wysłany — endpoint zwraca go w liście
`no_forwarder`, wzorem istniejącego `POST /api/avizo/send`.

### Dwie drogi potwierdzenia, jedna logika

Spedytor **z kontem** widzi w swoim module listę „Do potwierdzenia" i akceptuje datę albo wpisuje
własną. Spedytor **bez konta** dostaje mail z linkiem tokenowym — istniejący formularz awizacyjny,
rozszerzony o pole daty wypełnione naszą propozycją.

Obie drogi wołają **tę samą funkcję domenową**:

```
confirm_plan(container, date, confirmed_by: User | None) -> None
```

Ustawia `planning_status = POTWIERDZONE`, `planning_confirmed_at`, `planning_confirmed_by_id`
(`None` przy tokenie) oraz `notify_date = date`.

Kontrpropozycja daty również daje `POTWIERDZONE`, z widoczną adnotacją
„spedycja zmieniła: {nasza} → {ich}". Różnicę odczytujemy z istniejącego audytu (`record_changes`),
bez dodatkowej kolumny.

### Izolacja

Spedytor potwierdza wyłącznie własne kontenery. Realizowane przez istniejące `_enforce_scope`
/ `get_scoped` w `deps.py` — **bez powielania reguł w routerze**, zgodnie z `CLAUDE.md`.

## Zaproszenia użytkowników

`POST /api/users` z `send_invite` wysyła maila **serwerowo**, przez ten sam kanał SMTP, którego
używa awizacja. Zastępuje to otwieranie Outlooka przez `mailto` w `UsersTab.tsx`.
`must_change_password` działa już dziś i pozostaje bez zmian.

Zakres świadomie minimalny: jeden szablon maila, bez zarządzania cyklem życia zaproszeń
(ponawianie, wygasanie, odwoływanie).

## Decyzje projektowe

**Jedno pole daty + status, a nie dwa pola.** Rozważano trzymanie propozycji w istniejącym
`proposed_delivery_date` i wypełnianie `notify_date` dopiero po potwierdzeniu. Odrzucone: dwa pola
daty wymagają rozstrzygania „które jest prawdziwe" w każdym zapytaniu, powiadomieniu i eksporcie.
Jedno pole plus status ma jedno źródło prawdy. Ceną jest kolejka od pierwszego dnia pełna
niepewnych dat — łagodzona tym, że sekcje wizualnie je oddzielają, a limit ich nie liczy.

`proposed_delivery_date` pozostaje nieużywane. Jego usunięcie jest poza zakresem tego specu.

**Zamrożenie zamiast ciągłego przeliczania.** Rozważano cofanie potwierdzenia przy każdej zmianie
ETA. Odrzucone: wywraca obietnicę „zaplanowany 100%" i generuje hałas przy każdym drgnięciu ETA.
Wybrano alert wymagający świadomej decyzji człowieka.

**Portal jako główna droga, token jako zapas.** Wyłącznie portal wykluczyłby małe spedycje bez kont
z procesu „zaplanowany 100%". Wyłącznie token zostawiłby moduł spedycji wizytówką.

## Testy

Backend:

- przejścia stanów `PROPOZYCJA → WYSLANE → POTWIERDZONE`;
- reguła zamrożenia: ETA przelicza datę w `PROPOZYCJA`; **nie** przelicza w `WYSLANE`,
  w `POTWIERDZONE` ani gdy `notify_date_manual == True`;
- `used` w `/api/queue` liczy wyłącznie `POTWIERDZONE`; propozycje i wysłane nie podbijają `over_limit`;
- spedytor nie potwierdzi cudzego kontenera (403 przez `_enforce_scope`);
- potwierdzenie przez wygasły token odrzucone;
- zmiana daty potwierdzonego rekordu cofa status do `PROPOZYCJA` i zwalnia miejsce w limicie;
- wysyłka kontenera bez spedytora trafia do `no_forwarder`.

Frontend (DOM): sekcje-nagłówki z licznikami, zwijanie jako filtr zaplanowane/niezaplanowane,
dialog blokera przy edycji potwierdzonej daty.

## Migracja

Jedna migracja Alembica dodająca sześć kolumn, z indeksem na `planning_status`.
Kolumny nullable lub z `server_default`, wartości istniejących rekordów: `PROPOZYCJA`.

**Nowe kolumny muszą trafić także do dev-shimu** `ensure_new_columns()` w `app/main.py` —
pilnuje tego `tests/test_dev_schema_shim.py`.

**Przed dopisaniem migracji sprawdzić `alembic heads`** — w tym repo zdarzyła się już kolizja
identyfikatorów rewizji dająca `CycleDetected`.

## Poza zakresem

Idzie do C i dalej: grupowe przypisywanie jednej daty wielu kontenerom, estymacja czasu rozładunku
(ML), godziny slotów 7:15 / DLT 7:00, SMS-y i kod awizacyjny kierowcy, statusy rampowe, faktury
transportowe, ranking pilności.

## Ryzyko do obserwacji po wdrożeniu

„Wysyłamy plan tydzień przed wpłynięciem" zderza się z ruchomą ETA. Tydzień przed wpłynięciem
propozycja `eta + 4` bywa jeszcze niepewna, a wysyłka ją zamraża — alert „ETA przesunięta" może
odpalać częściej, niż jest to użyteczne. Projekt tego nie zmienia; jeśli alerty okażą się hałaśliwe,
naturalnym krokiem jest próg (np. alert dopiero od 2 dni różnicy) albo późniejsza wysyłka planu.

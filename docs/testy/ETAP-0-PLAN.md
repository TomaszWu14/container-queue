# System testów regresji TIMPORYE — Etap 0: analiza i plan

Stan na `origin/main` 2026-09-26. Etap 0 nie zawiera nowych testów. Powstały tu: inwentarz, szkice
`tests/permissions.yaml` i `tests/ui-permissions.yaml` (z generatorem `tests/gen_permissions.py`),
mapa ryzyk, scenariusze E2E oraz `BUGS-FOUND.md` z 6 podejrzeniami.

## 1. Co już jest: rozbudowujemy, nie duplikujemy

| Warstwa | Stan | Kluczowe pliki |
|---|---|---|
| Backend pytest | 188 plików, ~1024 testy, ~7 min | `backend/tests/`, `conftest.py` (SQLite + szablon kopiowany per test) |
| Scoping ról (deps.py) | dobre pokrycie jednostkowe | `test_deps*.py` (26), `test_isolation.py`, `test_purchasing_role.py`, `test_audyt_dostep.py` |
| Auth na trasach | nowy strażnik (PR w toku) | `test_routes_require_auth.py`: każda trasa z logowaniem albo na liście PUBLIC |
| Frontend vitest | 134 pliki, ~491 testów | `frontend/src/**/*.test.ts(x)` |
| E2E Playwright | 7 testów, 2 role, tylko ręcznie | `frontend/e2e/`, `.github/workflows/e2e.yml` |
| Bezpieczeństwo CI | Bandit, pip-audit, npm audit, gitleaks, Trivy (co miesiąc) + Dependabot | `security.yml`, `.github/dependabot.yml` |
| Ochrona main | bramka „CI OK” (od #637) | `automerge.yml` |

**Luki:** macierz rola × trasa, IDOR dla wszystkich zasobów z `{id}`, scoping eksportów, nagłówki
bezpieczeństwa, CSRF, freezegun/DST, fabryki danych, globalna blokada sieci, coverage, migracje
upgrade/downgrade na PostgreSQL, współbieżność, E2E dla ról warehouse/forwarder/customs/purchasing.

## 2. Inwentarz

- **Role (6):** admin, logistics, warehouse, forwarder, customs, purchasing. Wymiary dodatkowe:
  flaga `view_all_companies` (nie działa dla warehouse), zawężenie warehouse do magazynu, podgląd
  admina „jako rola” (mutacje 403), konto serwisowe automatyzacji (n8n).
- **Spółki:** kody z bazy. `SUPPLIER_COMPANY_CODES=ACME,PT`. Testy używają min. 2 spółek (A/B).
- **Trasy backendu:** 400 par trasa×metoda.
  - 27 publicznych,
  - 88 tylko admin,
  - 108 admin+logistics,
  - 108 dla każdej zalogowanej roli (zakres pilnowany w treści przez `scope_*` / `get_scoped`),
  - reszta to kombinacje.
  - 26 tras ma dodatkowe sprawdzenie roli w treści (w macierzy „?”).
  - Pełna lista: `tests/permissions.yaml`.
- **Frontend:** ~35 tras, 22 pozycje menu, 32 sekcje admin/master-data pod własnymi adresami, 12 starych
  adresów z przekierowaniem (w tym `/dzis`). Szczegóły: `tests/ui-permissions.yaml`.
- **Formularze zapisujące:** ~20 (kontener, status, awizacja, wycena, zlecenie transportowe, reklamacja,
  odprawa, kierowca, użytkownicy, 10 słowników, EditableTable w master data).
- **Importy (13):** kontenery xlsx, sync kolejki, PO/ETD, pozycje SAP, EKKO, MARM, stany DLT, porty,
  LFA1, auto-detekcja, materiały, PAZ, analityka. Część jest „wszystko albo nic”, część częściowa (savepoint per wiersz).
- **Eksporty:** kolejka xlsx, wywołania DLT xlsx, paczka faktur xlsx, wyceny CSV, wzory importu, raport
  błędów SAP, CMR, list reklamacyjny, ZIP-y, .eml.
- **Zadania w tle (13):** demurrage, odprawy/SMS, reklamacje, palety, digesty, weryfikacja backupu,
  awizacje/RODO, monitor, retencja logów, SharePoint, congestion, AIS websocket, applog.
- **Integracje:** AIS (websocket), open-meteo, Wikimedia, poczta (Graph/SMTP/.eml), SMS (SMSAPI), Teams,
  n8n, SharePoint, Power BI, NBP, Ollama (LLM), serwis paletyzacji, Sentry. **SafeCube został z kodu usunięty.**
- **Zmienne środowiskowe:** ~120 (pełna lista w `backend/app/config.py`). Fail-fast na prod dotyczy tylko
  SECRET_KEY, ADMIN_PASSWORD, SECURE_COOKIES, PUBLIC_BASE_URL i AUTOMATION_API_TOKEN.
- **Statusy kontenera:** **10, nie 8:** ZAPOWIEDZIANY → W_PRODUKCJI → TRANSPORT_WSTEPNY → W_TRANSPORCIE →
  W_PORCIE → ODPRAWA → AWIZOWANY → W_DOSTAWIE → DOSTARCZONY → ZREALIZOWANY.
  - Reguły: do przodu dowolnie, wstecz o 1 krok tylko z notatką, więcej niż 1 krok wstecz tylko admin.
  - Warehouse może ustawić tylko DOSTARCZONY lub ZREALIZOWANY.
- **Baza:** prod PostgreSQL 16, testy SQLite (schemat z `create_all`, nie z alembica). 92 migracje, 89 z działającym `downgrade()`.

## 3. Mapa ryzyk: co najbardziej boli, gdy się zepsuje

| # | Ryzyko | Skutek | P-stwo | Pokrycie dziś | Etap |
|---|---|---|---|---|---|
| R1 | Wyciek danych między spółkami (IDOR, eksport, wyszukiwarka, liczniki) | krytyczny: dane klienta u konkurenta | średnie | częściowe | 2 |
| R2 | Migracja psuje prod (dwie głowy, różnica SQLite↔PG) | krytyczny: prod nie wstaje | średnie (2 incydenty) | tylko struktura | 1–2 |
| R3 | Import nadpisuje lub gubi dane (sync kolejki, snapshot DLT) | wysoki: błędny plan dostaw | średnie | dobre dla happy path | 2 |
| R4 | Ciche nadpisanie przy równoczesnej edycji (B-004) | wysoki | wysokie przy kilku logistykach | brak | 2 |
| R5 | Eskalacja uprawnień (niższa rola woła admin API) | krytyczny | niskie | dobre w deps | 2 |
| R6 | Zła data „dziś”/DST/przełom roku → awizacje w zły dzień | wysoki | średnie | punktowe | 2 |
| R7 | Zmiana statusu z pominięciem reguł (sync Excela omija walidację) | średni | średnie | częściowe | 2 |
| R8 | Frontend pokazuje akcję, której API odmawia (lub odwrotnie) | średni: frustracja, zgłoszenia | wysokie | brak | 4 |
| R9 | Wyciek PII do Sentry/logów (RODO) | wysoki | niskie | dobre | 2 |
| R10 | Deploy psuje prod bez wykrycia | krytyczny | średnie | bramka CI OK | 6 |
| R11 | Wolne widoki przy rosnących danych (N+1) | średni | rośnie w czasie | brak | 5 |
| R12 | Awaria integracji zewnętrznej wywala stronę (Ollama, serwis paletyzacji, NBP) | średni | średnie | mocki lokalne | 1–2 |

## 4. Propozycja ~15 scenariuszy E2E (do akceptacji)

Każdy scenariusz jest parametryzowany po rolach, które go widzą. Rola bez dostępu sprawdza brak przycisku albo ekran 403.

1. Logowanie każdą rolą → strona startowa wg roli → wylogowanie unieważnia sesję.
2. Dodanie kontenera (ISO 6346: poprawny, zła cyfra kontrolna, małe litery, spacje) → wiersz na kolejce.
3. Edycja kontenera i anulowanie: przycisk, Esc, zamknięcie modala, ostrzeżenie o niezapisanych zmianach.
4. Zmiana statusu: do przodu, 1 krok wstecz z notatką, magazyn potwierdza rozładunek. Pasek postępu = etykieta.
5. Zmiana daty awizacji i magazynu z menu „⋯” na wierszu. Liczniki DLT/ACME/bez magazynu się aktualizują.
6. Operacje masowe: zaznacz kilka → status, data, magazyn. Admin: usuń.
7. Obserwowane i specjalna troska: przełączenie, filtr „tylko obserwowane”, izolacja per użytkownik.
8. Kopiowanie numeru kontenera, zamówienia i dostawy → zawartość schowka.
9. Wyszukiwarka: podpowiedzi, klawiatura (↑↓ Enter Esc), brak wyników ze spółki B.
10. Kalendarz rok → miesiąc → dzień → panel dnia. Przełom roku.
11. Sekcje Administracji i Master data pod własnymi adresami: odświeżenie, Wstecz, link bezpośredni, 403 dla roli.
12. Import przez UI (kontenery xlsx: podgląd dry-run → zatwierdzenie; plik błędny → raport).
13. Eksport kolejki xlsx zawiera tylko dane spółki użytkownika.
14. Awizacja: wysłanie linku → strona publiczna kierowcy/spedytora → wybór slotu → status na kolejce.
15. Odprawa: customs zmienia status sprawy, logistyka widzi zmianę. Forwarder: zlecenie transportowe → akceptacja.
16. Przekierowania: `/dzis` → `/kolejka` z zachowaniem query. Stare adresy (`/admin`, `/container/:id`).

## 5. Korekty planu wynikające z analizy

- **SafeCube:** usunięty z kodu. Zamiast jego mocków proponuję nagrane odpowiedzi dla integracji, które
  istnieją: AIS (sesja WS), open-meteo, NBP, serwis paletyzacji, Ollama, SMSAPI, Graph/SMTP, Teams, SharePoint.
- **Statusy 1–8 → 1–10.** Macierz przejść obejmie 10×10 per rola.
- **Baza testowa:** szybki tryb zostaje na SQLite (7 min, runner self-hosted). PostgreSQL 16 w
  `docker-compose.test.yml` dla trybu pełnego i dla testu migracji. Uruchamianie całych 1000 testów
  na PG przy każdym PR podwoiłoby czas.
- **Zakres:** etapy 1–7 to realnie kilkadziesiąt PR-ów. Proponuję dowozić je małymi PR-ami (zasada
  repo „1 PR = 1 temat”), w kolejności ryzyka: macierz uprawnień + IDOR (R1, R5) → migracje na PG (R2) →
  importy (R3) → współbieżność (R4) → daty (R6) → E2E per rola → bezpieczeństwo → wydajność.
- **Dist frontendu:** `frontend/dist` nie jest w repo (build w Dockerfile), więc test „aktualności dist”
  jest zbędny. Zastąpi go build obrazu Dockera + health check w CI (Etap 6).
- **Chromium + Edge:** Edge w Playwright to kanał `msedge`. Na self-hosted runnerze Linux trzeba go
  doinstalować, więc proponuję go tylko w pipeline nocnym.

## 6. Decyzje właściciela (2026-09-26)

1. SafeCube: zamiast niego mocki istniejących integracji (AIS, NBP, serwis paletyzacji, Ollama, SMS, poczta, Teams, SharePoint). ✅
2. Komórki „?” w `permissions.yaml` rozstrzyga test w Etapie 2 (rzeczywiste zachowanie). Pytamy tylko przy podejrzeniu błędu. ✅
3. UI:
   - (a) forwarder MA mieć Zamówienia (B-006);
   - (b) „Analiza rozładunków” tylko dla admin, logistics i warehouse (B-007);
   - (c) karta rozładunku i dostawca: bez decyzji, zostaje stan obecny.
4. Runner `hetzner-gha` ma Dockera (runbook), więc PostgreSQL 16 idzie w CI.
5. Smoke produkcyjny: do wyjaśnienia (patrz sesja).
6. Kolejność: małe PR-y według ryzyka. ✅

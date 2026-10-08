> **Projekt portfolio.** Nazwy firm są zamienione na fikcyjne, a dane demo i testowe są syntetyczne.
>
> Kod udostępniony do wglądu (portfolio), wszelkie prawa zastrzeżone — patrz [`LICENSE`](LICENSE).

# TIMPORYE — system zarządzania kolejką kontenerów

[![ci-backend](https://github.com/TomaszWu14/container-queue/actions/workflows/ci-backend.yml/badge.svg)](https://github.com/TomaszWu14/container-queue/actions/workflows/ci-backend.yml) [![ci-frontend](https://github.com/TomaszWu14/container-queue/actions/workflows/ci-frontend.yml/badge.svg)](https://github.com/TomaszWu14/container-queue/actions/workflows/ci-frontend.yml)

Zastępuje Excela `KOLEJKA KONTENERÓW` wspólnym systemem dla spółek (Borealis, Cobalt Sport,
Iberia, Acme), magazynów i spedytorów (SPEDALFA, SPEDBETA, Delta Brokers).
Pełna specyfikacja z wywiadu projektowego: [docs/SPECYFIKACJA.md](docs/SPECYFIKACJA.md).

## W skrócie

| | |
|---|---|
| **Problem** | Kolejka kontenerów kilku spółek prowadzona w Excelu wysyłanym mailem — brak jednego statusu, historii zmian i widoczności dla magazynów i spedytorów. |
| **Rozwiązanie** | Wspólny system: kolejka i kalendarz awizacji, 8 etapów cyklu kontenera, śledzenie statków (AIS), zlecenia spedycyjne z ofertami, import i walidacja zgłoszeń SAD, faktury z OCR, pełny audyt zmian, role i separacja danych spółek. |
| **Stack** | Python 3.12, FastAPI, SQLAlchemy + Alembic, PostgreSQL/SQLite, React + TypeScript (Vite), Playwright, Docker, Coolify. |
| **Jakość** | ~2100 testów backendu (pytest), ~960 testów frontendu (vitest), testy E2E i wizualne (Playwright), CI na GitHub Actions, skany bezpieczeństwa (Bandit, Trivy, pip-audit). |
| **Dane** | Wszystkie dane w repo są fikcyjne — m.in. zgłoszenia SAD w testach pochodzą z generatora `backend/tests/fixtures/sad/generate_synthetic.py`. |

## Korzyści

1. **Uporządkowana kolejka kontenerów w jednym miejscu** — koniec z wersjami Excela wysyłanymi mailem.
2. **Bieżący status każdego kontenera dla wszystkich stron** — 8 etapów cyklu życia + osobny status odprawy celnej.
3. **Pełna separacja danych spółek** — każda spółka widzi swoje kontenery; logistyka Acme i admin mają widok całości.
4. **Podpięcie do API** — REST + OpenAPI/Swagger; śledzenie statków z AIS (aisstream.io) na mapie i osi czasu kontenera.
5. **Mniej telefonów i maili o „gdzie jest kontener”** — statusy, opóźnienia i historia dostępne po zalogowaniu, także na telefonie.
6. **Lepsze planowanie awizacji i rozładunku** — limity dzienne per magazyn (z nadpisaniem na konkretny dzień) i kalendarz dni wolnych PL/PT.
7. **Historia i ślad zmian** — audyt każdego pola: kto, kiedy, co zmienił i dlaczego (np. powód przeniesienia awizacji).
8. **Przejrzystość odpowiedzialności między firmami** — role (admin / logistyka / magazyn), magazyn potwierdza rozładunek, spedytor dostanie własny moduł zleceń.
9. **Szybsza reakcja na opóźnienia i zmiany** — automatyczna flaga „opóźniony”, filtr opóźnionych, alerty demurrage (Etap 4).
10. **Redukcja przestojów i lepsza koordynacja transportu** — wspólny obraz kolejki, raport kontenerów/miesiąc, archiwum zrealizowanych.

## Struktura

```
backend/   FastAPI + SQLAlchemy (PostgreSQL / SQLite) — API, autoryzacja JWT, audyt
frontend/  React + TypeScript (Vite) — panel PL/EN/PT
docs/      specyfikacja projektu
```

## Wdrożenie: Docker + Coolify (on-prem lub VPS)

Obraz: `docker-compose.coolify.yml` + `Dockerfile.coolify` — opis konfiguracji w Coolify:
[docs/DEPLOY_COOLIFY.md](docs/DEPLOY_COOLIFY.md). Obraz sam buduje panel ze źródeł i przy starcie
robi `alembic upgrade head`; po wdrożeniu `scripts/smoke.sh` sprawdza `/health`.
Kopie: [docs/BACKUPY.md](docs/BACKUPY.md). Bezpieczeństwo: [docs/BEZPIECZENSTWO.md](docs/BEZPIECZENSTWO.md),
zmienne: [docs/ZMIENNE-SRODOWISKOWE.md](docs/ZMIENNE-SRODOWISKOWE.md), onboarding: [docs/ONBOARDING-DEV.md](docs/ONBOARDING-DEV.md).

Kilka aplikacji na jednej domenie (brama nginx + niezależny stack n8n,
token serwisowy dla workflow, webhook zdarzeń): [docs/N8N.md](docs/N8N.md).

## Szybki start (Docker)

```bash
cp .env.example .env   # uzupełnij sekrety — compose bez nich nie wystartuje
docker compose up --build
# panel:  http://localhost:8080   (login/hasło admina z .env)
# API:    http://localhost:8000/docs (Swagger)
```

Wymagane w `.env` (obok `docker-compose.yml`): `POSTGRES_PASSWORD`, `SECRET_KEY`,
`ADMIN_PASSWORD` (opcjonalnie `ADMIN_LOGIN`, domyślnie `admin`). Porty są
bindowane tylko na `127.0.0.1` — dev-stack nie jest dostępny z sieci.

## Panel serwowany przez backend (jeden adres)

`frontend/dist` **nie jest w repozytorium** (`.gitignore`) — trzeba go zbudować (Node 22.12+); obraz
`Dockerfile.coolify` robi to sam. Lokalnie:

```bash
cd frontend && npm ci && npm run build   # tworzy frontend/dist
cd ../backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Panel i API pod jednym adresem: **http://localhost:8000** (admin / admin123). Inna ścieżka builda: `FRONTEND_DIST`.

## Development bez Dockera

```bash
# backend (Python 3.12 — jak obraz i CI)
cd backend
pip install -r requirements.txt -r requirements-dev.txt   # dev = pytest, ruff (poza obrazem)
uvicorn app.main:app --reload          # http://localhost:8000/docs


# testy
python -m pytest tests/

# frontend (Node 22.12+ — wymóg vitest/vite; CI: Node 24, obraz: Node 26)
cd frontend
npm install
npm run dev                            # http://localhost:5173 (proxy /api -> :8000)

# E2E (Playwright): patrz sekcja „Testy E2E" niżej
```

## Testy E2E (Playwright)

E2E odpala realny backend (uvicorn, SQLite `e2e.db`) i frontend (`vite dev`),
klika w przeglądarce. Seed danych (firmy, userzy per rola, kontenery) robi
`e2e/global-setup.ts` przez REST admina. W CI biegnie co noc na self-hosted runnerze (`e2e.yml`);
opis, wymagania runnera i lista stron bez testów: `docs/testy/E2E.md`.

```bash
cd frontend
npx playwright install chromium   # raz
npm run e2e                        # headless (jak CI)
npm run e2e -- --headed            # z widoczną przeglądarką (debug widoku)
npm run e2e -- --debug             # inspektor krok po kroku
```

**Uwaga:** E2E serwuje frontend z `vite dev` — build `dist/` nie jest potrzebny do testów E2E. Artefakty faili (screenshot/trace/wideo) lądują w
`frontend/test-results/`.

## Najważniejsze endpointy

| Endpoint | Opis |
|---|---|
| `POST /api/auth/login`, `/refresh` | logowanie (OAuth2 password + refresh token) |
| `GET/POST/PATCH /api/containers` | kolejka z filtrami (status, odprawa, daty, dostawca, spedytor, magazyn, szukajka, opóźnione) |
| `POST /api/containers/{id}/status` | zmiana statusu z opcjonalnym komentarzem |
| `GET /api/containers/{id}/history` | pełny audyt zmian kontenera |
| `GET /api/queue` | widok dzienny: kontenery + limit + dni wolne PL/PT |
| `PUT /api/limits`, `PUT /api/calendar` | limit na konkretny dzień, wyjątki kalendarza |
| `GET /api/stats/monthly` | raport kontenery/miesiąc per spółka |
| `GET /api/containers/{id}/events` | oś zdarzeń trackingu armatora |
| `POST /api/containers/{id}/track` | ręczne odświeżenie trackingu |
| `POST /api/tracking/sync` | synchronizacja wszystkich aktywnych (admin) |
| `GET/POST /api/transport-orders`, `POST .../{id}/status` | zlecenia transportowe (obieg: wystawione → zaakceptowane/odrzucone → w realizacji → wykonane → potwierdzone) |
| `GET/POST /api/containers/{id}/messages` | wątek wiadomości przy kontenerze |
| `GET/POST /api/containers/{id}/attachments`, `GET /api/attachments/{id}/download` | dokumenty transportowe (CMR, zlecenia, kwity) |
| `PATCH /api/containers/{id}/customs` | spedytor wskazuje agenta celnego i status odprawy |
| `/api/companies`, `/api/users`, słowniki | administracja |

## Moduł spedytora (Etap 3)

Konto spedytora (rola `forwarder`, powiązane z pozycją słownika spedytorów) widzi
wyłącznie kontenery przypisane do jego firmy — ze wszystkich spółek, które mu zleciły.
Spedytor akceptuje/odrzuca i realizuje zlecenia transportowe, wymienia wiadomości
i pliki przy kontenerze oraz aktualizuje agenta celnego i status odprawy.
Nie może edytować pozostałych danych kontenera ani statusu głównego.
Załączniki trafiają do `UPLOADS_DIR` (domyślnie `./uploads`, limit `MAX_UPLOAD_MB`).

## Awizacja dwuetapowa ze spedycją (linki tokenowe)

Kontakt ze spedycją w sprawie dostaw idzie dwoma jednorazowymi linkami (bez logowania):

1. **Etap 1 — potwierdzenie dostaw.** Z kolejki (`POST /api/avizo/send`) powstaje zlecenie
   awizacji per (spedytor, spółka) i mail z linkiem `/avizo/<token>`. Spedycja dla każdego
   kontenera wybiera: *potwierdzam* / *zmiana terminu* (data + opcjonalny slot) / *problem*
   (z komentarzem). Formularz można wysłać **raz**; odpowiedzi czekają na decyzję logistyki
   i nie zmieniają jeszcze planu.
2. **Decyzja w panelu „Awizacje”** (`/api/avizo-requests`): *Zatwierdź* stosuje terminy/sloty
   (`planning.confirm_plan`) i automatycznie wysyła **jeden** mail etapu 2; *Odrzuć z komentarzem*
   wysyła nowy link etapu 1 z komentarzem. Są też *Unieważnij* (linki), *Wyślij ponownie*
   (`?stage=1|2`) i *Anuluj*. Szczegóły zlecenia pokazują odpowiedzi, tokeny (bez hashy)
   i log maili z błędami dostawy.
3. **Etap 2 — dane kierowców** (`/avizo/driver/<token>`): imię i nazwisko, telefon (E.164 / PL),
   nr ciągnika i naczepy, opcjonalnie nr dowodu — per kontener. Dane trafiają do pól
   `Container.driver_*` (widoczne w kolejce, SMS kierowcy, brama); audyt maskuje telefon i dowód.

Statusy: `DRAFT → SENT_STAGE1 → CONFIRMED_BY_FORWARDER → APPROVED_BY_US | REJECTED (→ SENT_STAGE1)
→ SENT_STAGE2 → DRIVERS_SUBMITTED → CLOSED`, oraz `EXPIRED`, `CANCELLED`. Przejścia wyłącznie
przez `app/avizo_workflow.py` (niedozwolone → 409, każde w audycie).

Bezpieczeństwo linków: token `secrets.token_urlsafe(32)`, w bazie tylko SHA-256; token etapu 1
nie otwiera etapu 2; po wysłaniu 409 „formularz już wysłany”, wygasły/unieważniony 410.
Endpointy publiczne mają limit 30 żądań/min na IP (429 + `Retry-After`), POST wymaga
`application/json` i zgodnego `Origin`/`Referer` (zamiast tokenu CSRF — brak ciasteczek),
odpowiedzi mają `Referrer-Policy: no-referrer` i `X-Robots-Tag: noindex, nofollow`,
a token jest maskowany w logach uvicorn/aplikacji i w Sentry (`/avizo/[token]`).

Pętla dzienna: zlecenia bez aktywnego linku bieżącego etapu → `EXPIRED`; wszystkie kontenery
`DOSTARCZONY/ZREALIZOWANY` → `CLOSED`; po `DRIVER_DATA_RETENTION_DAYS` od zamknięcia dane
kierowców są czyszczone (RODO, wpis w audycie). Stare linki (sprzed wdrożenia) działają jako
tokeny etapu 1; `/api/avizo/{token}/propose` i `/api/avizo-proposals` zostają do ich wygaśnięcia.

### Wysyłka maili przez Microsoft 365 (Graph)

Mailer (`app/mailer.py`) ma trzy backendy: `graph` (Microsoft Graph `sendMail`), `smtp`
i `console` (tylko log — workflow działa przed konfiguracją M365). Wysyłka idzie w tle,
z 3 ponowieniami (1 s / 4 s / 16 s); wynik każdej próby trafia do logu maili zlecenia i audytu.
Język maila wg słownika spedytorów (pl/en), CC — pole „CC awizacji” spółki.

Konfiguracja po stronie administratora M365 / IT:

1. **Rejestracja aplikacji** — Entra ID → *App registrations* → *New registration*
   (jednodzierżawowa). Zanotuj *Directory (tenant) ID* i *Application (client) ID*.
2. **Uprawnienie** — *API permissions* → *Microsoft Graph* → *Application permissions* →
   `Mail.Send` → *Grant admin consent*. (Uprawnienie delegowane nie wystarczy — backend
   wysyła bez zalogowanego użytkownika, przepływem client credentials.)
3. **Sekret** — *Certificates & secrets* → *New client secret*; zapisz wartość (widoczna raz)
   i termin wygaśnięcia (odnów przed upływem).
4. **Ograniczenie do jednej skrzynki** — bez tego `Mail.Send` pozwala wysyłać jako
   *dowolny* użytkownik organizacji. W Exchange Online PowerShell:

   ```powershell
   Connect-ExchangeOnline
   # grupa zabezpieczeń zawierająca wyłącznie skrzynkę nadawcy
   New-DistributionGroup -Name "TIMPORYE Mail Senders" -Type Security -Members awizacje@firma.pl
   New-ApplicationAccessPolicy -AppId <MS_CLIENT_ID> `
       -PolicyScopeGroupId "TIMPORYE Mail Senders" -AccessRight RestrictAccess `
       -Description "TIMPORYE: wysyłka awizacji tylko ze skrzynki awizacje@"
   # weryfikacja (Granted dla skrzynki nadawcy, Denied dla innej)
   Test-ApplicationAccessPolicy -Identity awizacje@firma.pl -AppId <MS_CLIENT_ID>
   Test-ApplicationAccessPolicy -Identity ktos.inny@firma.pl -AppId <MS_CLIENT_ID>
   ```

   Propagacja polityki może potrwać do ok. godziny. (Microsoft zastępuje Application Access
   Policies mechanizmem *RBAC for Applications* — `New-ManagementRoleAssignment` z rolą
   `Application Mail.Send` i zakresem ograniczonym do skrzynki — działa równoważnie.)

Zmienne środowiskowe (Coolify):

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `MAIL_BACKEND` | puste → `smtp` przy `SMTP_HOST`, inaczej `console` | `graph` / `smtp` / `console` |
| `MS_TENANT_ID` | — | Directory (tenant) ID |
| `MS_CLIENT_ID` | — | Application (client) ID |
| `MS_CLIENT_SECRET` | — | sekret klienta (maskowany w Sentry) |
| `MAIL_SENDER` | — | skrzynka nadawcy objęta Application Access Policy, np. `awizacje@firma.pl` |
| `AVIZO_STAGE1_DAYS` | `7` | ważność linku etapu 1 (dni) |
| `AVIZO_STAGE2_DAYS` | `5` | ważność linku etapu 2 (dni) |
| `DRIVER_DATA_RETENTION_DAYS` | `90` | po ilu dniach od zamknięcia zlecenia czyścić dane kierowców |
| `AUDIT_AUTH_RETENTION_DAYS` | `90` | po ilu dniach usuwać log logowań (`audit_log` z `entity_type=auth`: IP, wpisane loginy); historia biznesowa zostaje (GDPR-004) |
| `TOKEN_RETENTION_DAYS` | `30` | po ilu dniach od wygaśnięcia usuwać refresh tokeny i tokeny resetu hasła |
| `SMS_RETENTION_DAYS` | `90` | po ilu dniach usuwać historię SMS (telefon kierowcy, treść) |
| `CLIENT_ERROR_RETENTION_DAYS` | `30` | po ilu dniach usuwać błędy JS z beaconu (URL, User-Agent) |
| `NOTIFICATION_RETENTION_DAYS` | `180` | po ilu dniach kasować **przeczytane** powiadomienia (nieprzeczytane zostają); produkcja (`docker-compose.coolify.yml`): `90` |
| `PUBLIC_BASE_URL` | — | adres panelu w linkach maili (wymagany w produkcji) |
| `LOG_FILE` | — (tylko stdout) | trwały plik logów z rotacją 10×10 MB, np. `/data/logs/app.log` (wolumen `logs`) — przeżywa Redeploy; tokeny linków maskowane, linie z `rid=` = `X-Request-ID` |

Reply-To maila to adres operatora, który wysłał/zatwierdził awizację (fallback `MAIL_SENDER`).
Test na izolowanej instancji: `MAIL_BACKEND=console` — poza produkcją treść maila (z linkiem)
idzie na stdout procesu; logi aplikacji zawierają tylko temat i adresatów (token jest maskowany).
`docker-compose.coolify.yml` przekazuje do kontenera wszystkie te zmienne (pełna lista: [docs/ZMIENNE-SRODOWISKOWE.md](docs/ZMIENNE-SRODOWISKOWE.md)).

## Śledzenie (Etap 2)

Moduł `backend/app/tracking/`: pozycje **statków** z AIS (aisstream.io, kolektor websocketowy),
mapa/globus „Śledzenie", oś czasu kontenera (zdarzenia + ręczne statusy), kongestia portów
i alerty opóźnień/demurrage. Zewnętrznego providera trackingu kontenerów nie ma — status
kontenera zmienia się ręcznie. Konfiguracja w env:

```
AISSTREAM_API_KEY=twój-klucz      # pusty = kolektor AIS wyłączony
TRACKING_INTERVAL_HOURS=12        # co ile godzin liczona jest kongestia portów
```

### Faktury (CIPL) → Excel

Panel „Faktury (CIPL)" na karcie kontenera (admin, logistyka, zakupy) przyjmuje PDF-y
faktur — także zestawy CIPL (faktura + packing lista w jednym pliku). Pipeline działa
lokalnie w backendzie (`app/invoices/`), bez zewnętrznych usług (OCR lokalnym Tesseractem dla skanów):

1. **Cięcie** PDF-zestawu na dokumenty po tekście stron (faktura / proforma / packing lista / inne).
2. **Ekstrakcja** tabeli pozycji z warstwy tekstowej (pdfplumber) — auto-detekcja kolumn albo
   mapa kolumn dostawcy (słownik dostawców → pole „Mapa kolumn", np. `ref=Item No.; qty=Q'ty; net=Amount`).
   PDF z tekstem, ale bez linii tabeli (eksport z Excela) dostaje kolumny z pozycji słów.
   **Skany** idą przez OCR (Tesseract, `OCR_LANG=pol+eng`, `OCR_DPI=220`): strona bez warstwy
   tekstowej jest renderowana i czytana, komórki tabeli odtwarzane z pozycji słów; dokument
   dostaje znacznik „OCR" (sprawdź liczby w weryfikacji). Bez binarki tesseract skan = błąd dokumentu.
   Dokument błędnie wzięty za fakturę (certyfikat, duplikat) można „Pominąć" — nie liczy się do paczki;
   „Przywróć" cofa pominięcie (ponowna ekstrakcja).
3. **Dopasowanie** REF do **master daty materiałów** (Administracja → Materiały, import z xlsx):
   nazwa PL, kod CN, SENT, przelicznik jednostki; wagi netto/brutto z packing listy.
   Słownik jest globalny z możliwością nadpisania pól per spółka. Gdy reguły nie dopasują,
   **moduł ML** (`app/invoices/ml.py`, scikit-learn) podpowiada REF: z historii zatwierdzonych
   weryfikacji (dostawca + REF z faktury → REF master) i z podobieństwa TF-IDF do master daty;
   sugestia ≥ `ML_AUTO_APPLY_THRESHOLD` (0.9) jest stosowana automatycznie (źródło „ML"),
   słabsza czeka na kliknięcie „Zastosuj" (niejednoznaczne X/X1 rozstrzyga tylko historia tego
   dostawcy). Klasyfikator typu dokumentu (TF-IDF + regresja logistyczna) uczy się z tekstów
   zatwierdzonych dokumentów i ratuje cięcie skanów, gdy OCR zniekształci nagłówek; startuje od
   `ML_MIN_EXAMPLES` (20) przykładów. Modele dotrenowują się w tle po każdym zatwierdzeniu
   i imporcie (`ML_AUTO_TRAIN`, `ML_TRAIN_IN_BACKGROUND`), ręcznie: Materiały → „Trenuj modele";
   pliki w `ML_MODEL_DIR` (domyślnie katalog `ml` obok uploadów, np. `/data/ml` — nie w wolumenie
   uploadów; każdy plik ma podpis HMAC `.sig`, bez ważnego podpisu model nie jest wczytywany, AI-007).
4. **Weryfikacja** — użytkownik poprawia REF/ilość/kwotę, rozstrzyga pozycje niejednoznaczne
   (X/X1 blokują zatwierdzenie; brak w master nie blokuje), zatwierdza dokument.
5. **Excel** (11 kolumn: Nr faktury, Ilość, REF, Nazwa PL, Waga netto, Waga brutto,
   Przelicznik jednostki, Kwota, Kod celny (CN), SENT, Status dopasowania) trafia do
   załączników kontenera — widoczny także dla spedytora/magazynu/agencji.

Dane z poprzedniej aplikacji Compare (materiały, przeliczniki, mapy kolumn dostawców)
przenosi `python -m scripts.import_compare_db --db <url bazy Compare>` (domyślnie podgląd,
`--commit` zapisuje). Limit stron jednego PDF: `INVOICE_PDF_MAX_PAGES` (domyślnie 60).

## Statusy

Cykl życia (10 statusów, `ContainerStatus`): `ZAPOWIEDZIANY → W_PRODUKCJI → TRANSPORT_WSTEPNY → W_TRANSPORCIE → W_PORCIE → ODPRAWA → AWIZOWANY → W_DOSTAWIE → DOSTARCZONY → ZREALIZOWANY`
(magazyn może ustawić tylko `DOSTARCZONY` — potwierdzenie rozładunku; `ZREALIZOWANY` ustawia logistyka po zamknięciu formalności).

Odprawa celna (pole niezależne, `CustomsStatus`): `BRAK → DOKUMENTY_KOMPLETNE → ZLECONA → DRAFT_WYSLANY → DRAFT_POTWIERDZONY → ODPRAWIONY → ZWOLNIONY → ROZLICZONY`, oraz `REWIZJA`. `ZWOLNIONY` = towar zwolniony (SAD-PW), można wydać.
Zgodność z enumami pilnuje `backend/tests/test_docs_statusy.py`.

Numer kontenera walidowany blokująco wg **ISO 6346** (format + cyfra kontrolna).

## Powiadomienia i eksport (Etap 4)

Powiadomienia in-app (dzwoneczek w panelu) tworzone są zawsze; e-mail i Teams/Slack
włączają się po konfiguracji i nigdy nie blokują operacji:

```
SMTP_HOST=... SMTP_PORT=587 SMTP_USER=... SMTP_PASSWORD=... SMTP_FROM=timporye@firma.pl
TEAMS_WEBHOOK_URL=https://...   # webhook kanału Teams/Slack
DEMURRAGE_ALERT_DAYS=3          # wyprzedzenie alertu o końcu demurrage
```

Zdarzenia: zmiana ETA / opóźnienie (z trackingu), automatyczna zmiana statusu,
nowe zlecenie transportowe i każdy krok obiegu, nowa wiadomość, nowy plik,
zbliżający się koniec demurrage (termin = data przybycia z trackingu lub ETA
+ dni wolne; jeden alert na kontener dziennie). Eksport przefiltrowanej kolejki:
przycisk „Eksport Excel” lub `GET /api/containers/export/xlsx`.

## Migracje bazy (Alembic)
Obraz Dockera uruchamia `alembic upgrade head` przed startem API. Na produkcji (`ENVIRONMENT=production`) start aplikacji nie wykonuje żadnego DDL (`create_all`/`ensure_new_columns` tylko w dev/testach) — przy rozjeździe z głową migracji loguje ERROR. Ręcznie (z `backend/`):

```bash
python -m alembic upgrade head                       # aktualizacja schematu
python -m alembic revision --autogenerate -m "opis"  # nowa migracja po zmianie modeli
```

## Zrealizowane etapy

1. **Fundament** — spółki, role, kolejka, statusy, audyt, awizacje, limity, kalendarz PL/PT, import Excela, panel React.
2. **Śledzenie** — pozycje statków z AIS, mapa/globus, oś czasu kontenera, kongestia portów.
3. **Moduł spedytora** — zlecenia transportowe z pełnym obiegiem, wymiana plików, wiadomości, agent celny.
4. **Powiadomienia i raporty** — in-app / e-mail / Teams, alerty demurrage, eksport xlsx.
5. **Widoki i produkcja** — dashboard ze statystykami, kalendarz awizacji z limitami, migracje Alembic.

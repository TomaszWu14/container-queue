# Zmienne środowiskowe TIMPORYE

Katalog pól klasy `Settings` z `backend/app/config.py` (**bez wartości — żadnych sekretów w tym pliku**).

- Kolumna „W compose” mówi, czy `docker-compose.coolify.yml` jawnie przekazuje zmienną do kontenera `app` —
  „nie” oznacza, że zadziała tylko, jeśli Coolify wstrzykuje wszystkie zmienne.
- **Utrzymanie:** po dodaniu pola w `Settings` dopisz wiersz. Pilnuje tego `backend/tests/test_env_docs.py`
  (test pada, gdy jakieś pole `Settings` nie występuje tu jako `` `NAZWA` ``). Dopisz też linię
  `NAZWA=<domyślna>` z komentarzem do `.env.example` — pilnuje `backend/tests/test_env_example.py`
  (brak pola, martwy wpis, wartość ≠ domyślna z kodu, niepusty sekret).

Dodatkowo poza `Settings`: `LOG_LEVEL` (main.py, domyślnie INFO), `FORWARDED_ALLOW_IPS` (CMD w Dockerfile),
`POSTGRES_PASSWORD` (compose → baza i `DATABASE_URL`), w stacku n8n: `N8N_ENCRYPTION_KEY` (SEKRET — utrata = utrata credentiali),
`N8N_PUBLIC_BASE_URL`, `N8N_PROXY_HOPS`. Skrypt kopii `backend/scripts/backup.sh`: `BACKUP_KEEP` (kopie bazy, domyślnie 14), `BACKUP_KEEP_UPLOADS` (archiwa załączników, domyślnie 7), `BACKUP_AGE_RECIPIENT` (klucz publiczny age — kopie tylko zaszyfrowane, BACKUP-007) i `BACKUP_AGE_IDENTITY` (klucz prywatny, tylko `restore.sh`); patrz `docs/BACKUPY.md`. Frontend: `VITE_API_TARGET` (tylko dev proxy).

Limity kontenerów w compose (INFRA-004): `APP_MEM_LIMIT` (domyślnie 1536m), `APP_CPUS` (1; nie więcej niż rdzeni hosta), `N8N_MEM_LIMIT` (1g), `N8N_CPUS` (1).

## Rdzeń i baza

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `APP_NAME` | str | ma bezpieczny domyślny | **nie** |  |
| `ENVIRONMENT` | str | wymagane świadomie na prod | tak | dev / production — production wymusza bezpieczne sekrety |
| `APP_VERSION` | str | ma bezpieczny domyślny | **nie** | SHA commita — ustawiany w obrazie z build arg `SOURCE_COMMIT` (Coolify: „Include Source Commit in Build”); nie ustawiaj ręcznie |
| `BUILD_TIME` | str | ma bezpieczny domyślny | **nie** | data/godzina builda obrazu (UTC) |
| `DATABASE_URL` | str | SEKRET (ustaw w Coolify, nigdy w repo) | tak |  |
| `DB_POOL_SIZE` | int | ma bezpieczny domyślny | **nie** | Pula połączeń (tylko PostgreSQL). Domyślne 10+20=30 pokrywa threadpool Starlette (~40 wątków dla synchronicznych handlerów), zostając poniżej max_connections… |
| `DB_MAX_OVERFLOW` | int | ma bezpieczny domyślny | **nie** |  |
| `DB_POOL_TIMEOUT` | int | ma bezpieczny domyślny | **nie** | s czekania na wolne połączenie |
| `DB_POOL_RECYCLE` | int | ma bezpieczny domyślny | **nie** | s — recykling połączenia |
| `SECRET_KEY` | str | SEKRET (ustaw w Coolify, nigdy w repo) | tak |  |
| `DATA_ENCRYPTION_KEY` | str | SEKRET (ustaw w Coolify, nigdy w repo); puste = klucz z `SECRET_KEY` | **nie** | klucz szyfrowania danych w bazie (cache MSAL/Power BI), osobny od `SECRET_KEY` (SEC-017). Wygeneruj np. `python -c "import secrets; print(secrets.token_hex(32))"`. Po ustawieniu stare wartości dalej się czytają (odczyt próbuje też klucza z `SECRET_KEY`), nowe zapisy idą nowym kluczem. `SECRET_KEY` rotuj dopiero, gdy dane przepisano nowym kluczem (cache Power BI zapisuje się przy odświeżeniu tokenu — ok. 1 h używania — albo po ponownym połączeniu Power BI); inaczej stare wartości staną się nieczytelne. Nie zmieniaj go później — dane nim zaszyfrowane staną się nieczytelne. Wymaga dopisania do `docker-compose.coolify.yml` (lista `environment`) |
| `RUN_BACKGROUND_JOBS` | bool | ma bezpieczny domyślny | **nie** | False = instancja wtórna na wspólnej bazie: bez pętli tła (alerty, digest, SMS-y, kolektor AIS, sync trackingu) — inaczej wysyłki dublują się per serwer |
| `WEB_CONCURRENCY` | int | ma bezpieczny domyślny (1) | **nie** | BUILD-003: liczba workerów uvicorna (uvicorn czyta ją sam — CMD bez `--workers`), 1–16. >1 tylko na PostgreSQL (na SQLite start odmawia); pętle tła prowadzi jeden worker-lider. Budżet: każdy worker ~260 MB RAM i `DB_POOL_SIZE`+`DB_MAX_OVERFLOW`+2 połączeń — suma < `max_connections`. Procedura: `docs/JEDNA-INSTANCJA.md` |

## Uwierzytelnianie i limity

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `ACCESS_TOKEN_MINUTES` | int | ma bezpieczny domyślny | **nie** | 2 h — decyzja 2026-09-18 |
| `REFRESH_REUSE_GRACE_SECONDS` | int | ma bezpieczny domyślny | **nie** | okno łaski dla ponownego użycia zrotowanego refresh tokenu (wyścig kart) — s; domyślnie 10, w oknie tylko nowy access token bez nowego refresh (SEC-010) |
| `REFRESH_TOKEN_DAYS` | int | ma bezpieczny domyślny | **nie** |  |
| `ADMIN_LOGIN` | str | ma bezpieczny domyślny | tak |  |
| `ADMIN_PASSWORD` | str | SEKRET (ustaw w Coolify, nigdy w repo) | tak |  |
| `CORS_ORIGINS` | str | puste = funkcja wyłączona / auto | **nie** | pusta lista = brak CORS (panel serwowany z tego samego adresu go nie potrzebuje) |
| `SECURE_COOKIES` | bool | wymagane świadomie na prod | tak | True za HTTPS: cookies z flagą Secure + nagłówek HSTS |
| `LOGIN_MAX_ATTEMPTS` | int | ma bezpieczny domyślny | **nie** | limit nieudanych logowań… |
| `LOGIN_WINDOW_MINUTES` | int | ma bezpieczny domyślny | **nie** | …w oknie czasowym (na parę IP+login) |
| `LOGIN_MAX_ATTEMPTS_PER_IP` | int | ma bezpieczny domyślny | **nie** | suma porażek logowania z jednego IP (wiele loginów) — wyżej niż para IP+login, bo za NAT biura siedzi wielu ludzi |
| `LOGIN_ACCOUNT_LOCK_AFTER` | int | ma bezpieczny domyślny | **nie** | SEC-012: porażki jednego konta ze wszystkich IP w oknie `LOGIN_WINDOW_MINUTES`, od których zaczyna się progresywna przerwa (domyślnie 10) + alert do adminów |
| `LOGIN_ACCOUNT_LOCK_SECONDS` | int | ma bezpieczny domyślny | **nie** | SEC-012: pierwsza przerwa konta (s, domyślnie 30); każda kolejna porażka ją podwaja, maks. okno logowań |
| `API_RATE_LIMIT_PER_MINUTE` | int | ma bezpieczny domyślny | tak | globalny limit żądań API na IP w oknie minutowym (0 = wyłączony) |
| `PASSWORD_RESET_MINUTES` | int | ma bezpieczny domyślny | **nie** | ważność linku resetu hasła |
| `PASSWORD_MIN_LENGTH` | int | ma bezpieczny domyślny | **nie** | W14 #89: polityka haseł — minimalna długość (+ wymóg litery i cyfry w kodzie) |
| `BCRYPT_ROUNDS` | int | ma bezpieczny domyślny (12) | **nie** | koszt bcrypt nowych hashy haseł; produkcja min. 12 (start odmawia niżej), testy 4 — szybkie CI |
| `REQUIRE_2FA_ADMIN` | bool | domyślnie `false` | **nie** | SEC-006: przy `true` konto admina bez 2FA po zalogowaniu widzi ekran włączania 2FA; do tego czasu tylko odczyt (zapisy poza `/api/auth/*` → 403). domyślnie wymóg wyłączony (decyzja właściciela 2026-09-29); 2FA mogą włączyć wszystkie role |
| `CLIENT_ERROR_RATE_PER_MINUTE` | int | ma bezpieczny domyślny | **nie** | W14 #50: limit beaconów błędów JS z panelu (na IP, okno minutowe) |

## Pliki i kopie

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `VERIFY_BACKUP_WEEKDAY` | int | ma bezpieczny domyślny | **nie** | W14 #47: dzień tygodnia cotygodniowej weryfikacji backupu (0=pon … 6=niedziela) |
| `BACKUP_DIR` | str | ma bezpieczny domyślny | tak |  |
| `ALLOWED_UPLOAD_EXTENSIONS` | str | ma bezpieczny domyślny | **nie** |  |

## Monitoring

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `SENTRY_DSN` | str | SEKRET (ustaw w Coolify, nigdy w repo) | tak | puste = monitoring błędów wyłączony |
| `SENTRY_RELEASE` | str | puste = funkcja wyłączona / auto | **nie** | SHA/tag builda dla Sentry; puste = `APP_VERSION` z obrazu (gdy ≠ „dev”) |
| `SENTRY_TRACES_RATE` | float | ma bezpieczny domyślny (`0.05`) | **nie** | odsetek transakcji (wydajność) wysyłanych do Sentry, 0–1; błędy zawsze w 100% (OBS-010) |

## Adresy, proxy, branding

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `PUBLIC_BASE_URL` | str | puste = funkcja wyłączona / auto | tak | adres panelu w linkach e-mail (WYMAGANY w produkcji) |
| `PORTAL_BRAND_NAME` | str | puste = funkcja wyłączona / auto | **nie** | branding stron publicznych (portal kliencki) — bez hardkodu nazwy spółki w kodzie puste = app_name |
| `PORTAL_LOGO_URL` | str | puste = funkcja wyłączona / auto | **nie** | opcjonalny URL logo w nagłówku portalu |
| `DEMO_READONLY_LOGINS` | str | puste = funkcja wyłączona / auto | **nie** | instancja pokazowa (portfolio): loginy tylko do odczytu (CSV) — każdy zapis z tych kont = 403; puste = zwykła instancja |
| `DEMO_LOGIN_HINT` | str | puste = funkcja wyłączona / auto | **nie** | podpowiedź „login / hasło” na ekranie logowania instancji pokazowej |
| `ALLOWED_HOSTS` | str | puste = funkcja wyłączona / auto | tak | dozwolone nagłówki Host (CSV) — ochrona przed host-header injection; puste = bez filtra |
| `TRUSTED_PROXY_COUNT` | int | ma bezpieczny domyślny | tak | liczba zaufanych proxy przed aplikacją — IP klienta bierzemy z tej pozycji X-Forwarded-For |
| `TRUSTED_PROXY_CIDRS` | str | ma bezpieczny domyślny | **nie** | X-Forwarded-For honorujemy TYLKO, gdy bezpośredni peer jest w tych sieciach (CSV CIDR); domyślnie sieci prywatne = proxy Coolify/Traefik w sieci dockera. Pee… |

## SMS / kierowcy / portal

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `SMS_PROVIDER` | str | ma bezpieczny domyślny | **nie** | SMS do kierowców (łącznik kierowcy) smsapi / mock / off |
| `SMSAPI_TOKEN` | str | SEKRET (ustaw w Coolify, nigdy w repo) | **nie** |  |
| `SMSAPI_URL` | str | ma bezpieczny domyślny | **nie** |  |
| `SMS_DAILY_CAP` | int | ma bezpieczny domyślny (`200`) | **nie** | COST-003: globalny limit prób SMS na dobę (czas PL, także nieudanych); ponad → 429 i wstrzymanie auto-SMS do północy, alert adminów przy 80% i 100%; `0` = bez limitu |
| `SMS_AUTO_MAX_ATTEMPTS` | int | ma bezpieczny domyślny (`2`) | **nie** | COST-003: ile prób auto-przypomnienia na kontener i datę dostawy w dobie (nieudane nie są ponawiane w nieskończoność) |
| `PUBLIC_LINK_MAX_DAYS` | int | ma bezpieczny domyślny (90) | **nie** | SEC-014: twardy limit ważności KAŻDEGO publicznego linku (udostępnienie kontenera → 410, DLT → jednolite 404) liczony od wystawienia — także gdy link nie ma własnego terminu (DLT bez terminu, kontener „w drodze”). Stare linki działają do dnia wystawienia + limit; po nim wystarczy wygenerować nowy link |

## Tracking / AIS

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `TRACKING_INTERVAL_HOURS` | float | ma bezpieczny domyślny | tak | interwał joba kongestii portów (AIS) |
| `TRACKING_ETA_ALERT_DAYS` | int | ma bezpieczny domyślny | **nie** | próg powiadomienia o zmianie ETA — drobne drgania ETA armatora to szum |
| `AISSTREAM_API_KEY` | str | SEKRET (ustaw w Coolify, nigdy w repo) | **nie** | AIS (aisstream.io) — darmowe pozycje STATKÓW jako uzupełnienie trackingu kontenerów: klucz włącza kolektor websocketowy; pusty = wyłączone |
| `AISSTREAM_URL` | str | ma bezpieczny domyślny | **nie** |  |
| `AIS_RESUBSCRIBE_SECONDS` | float | ma bezpieczny domyślny | **nie** | co ile sekund zrywamy i odnawiamy subskrypcję (odświeżenie listy statków z kolejki) |
| `AIS_ERROR_BACKOFF_SECONDS` | float | ma bezpieczny domyślny | **nie** |  |
| `AIS_ANCHOR_ALERT_HOURS` | float | ma bezpieczny domyślny | **nie** | 36: alert, gdy statek stoi przy porcie dluzej niz N godzin |
| `AIS_STALE_HOURS` | float | ma bezpieczny domyślny | **nie** | statek bez wiadomości AIS dłużej niż N godzin ma „zamrożony" near_port (poza zasięgiem / poza filtrem MMSI) — nie alarmujemy o jego postoju |

## Serwis paletyzacji

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `PALLET_API_URL` | str | puste = funkcja wyłączona / auto | **nie** | Serwis paletyzacji (REST, X-API-Key) — puste = sekcja paletyzacji na karcie rozładunku pokazuje "Serwis paletyzacji nie skonfigurowany" (patrz routers/containers.py: palleti… |
| `PALLET_API_TOKEN` | str | SEKRET (ustaw w Coolify, nigdy w repo) | **nie** |  |
| `PALLET_API_TIMEOUT` | float | ma bezpieczny domyślny | **nie** |  |

## Faktury, OCR, AI, ML

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `INVOICE_PDF_MAX_PAGES` | int | ma bezpieczny domyślny | **nie** | Faktury (CIPL) → Excel: limit stron jednego PDF-zestawu (ochrona przed 300-stronicowym skanem, który zajmie worker na minuty — ekstrakcja tekstu/tabel jest s… |
| `DOCS_ETA_DAYS` | int | ma bezpieczny domyślny | **nie** | W5 dokumenty: horyzont alertu braków dokumentów przed ETA (dni; nadpisywalne ustawieniem admina docs_reminder_days) i tolerancja rozjazdu faktura↔zamówienie (%) |
| `INVOICE_TOLERANCE_PCT` | float | ma bezpieczny domyślny | **nie** |  |
| `SUPPLIER_COMPANY_CODES` | str | ma bezpieczny domyślny | **nie** | kartoteka dostawców (spec 2026-09-25): kody spółek (Company.code, CSV) pracujących na materiałach Acme — widzą i używają globalnej kartoteki. Pozostałe (Ti… |
| `ARCHIVE_ZIP_MAX_FILES` | int | ma bezpieczny domyślny | **nie** | masowy ZIP miesiąca: twardy limit liczby plików w archiwum |
| `OCR_ENABLED` | bool | ma bezpieczny domyślny | **nie** | OCR skanów (Tesseract): strona bez warstwy tekstowej jest renderowana (pypdfium2) i czytana przez tesseract. Brak binarki = OCR pomijany (dokument dostaje bł… |
| `OCR_LANG` | str | ma bezpieczny domyślny | **nie** |  |
| `OCR_DPI` | int | ma bezpieczny domyślny | **nie** |  |
| `INVOICE_OCR_IN_BACKGROUND` | bool | ma bezpieczny domyślny (`true`) | **nie** | ARCH-004: upload faktur zwraca 202, a cięcie/OCR/ekstrakcję robi pętla tła (`invoice_ingest`, co 30 s); front odpytuje paczkę. `false` albo `RUN_BACKGROUND_JOBS=false` na instancji = wszystko w żądaniu HTTP (201) |
| `OLLAMA_URL` | str | puste = funkcja wyłączona / auto | **nie** | lokalny LLM (Ollama) — dane NIE wychodzą poza własny serwer. Pusty URL = wyłączone. Ostatnia warstwa OCR (jak w compare): model obrazowy, gdy Tesseract nie … |
| `OLLAMA_ALLOW_REMOTE` | bool | ma bezpieczny domyślny (`false`) | **nie** | AI-006: `false` = `OLLAMA_URL` tylko wewnętrzny (nazwa usługi Dockera, localhost, `*.internal`/`*.local`/`*.lan`, adres prywatny); inny host albo schemat inny niż http(s) = AI wyłączone + ostrzeżenie przy starcie. `true` = świadoma zgoda na zdalną Ollamę (skany faktur opuszczają serwer; po HTTP dodatkowe ostrzeżenie) |
| `OLLAMA_TIMEOUT` | float | ma bezpieczny domyślny | **nie** | CPU: strona to minuty |
| `OCR_VISION_MODEL` | str | ma bezpieczny domyślny | **nie** |  |
| `ASSISTANT_MODEL` | str | ma bezpieczny domyślny | **nie** | asystent wiedzy: ~1.2 GB RAM |
| `ML_MODEL_DIR` | str | puste = katalog `ml` obok `UPLOADS_DIR` (np. `/data/ml`) | **nie** | ML (scikit-learn): sugestie REF + klasyfikator typu dokumentu. Modele (joblib = pickle) poza wolumenem uploadów, z podpisem HMAC (`.sig`, klucz z `SECRET_KEY`) sprawdzanym przed wczytaniem (AI-007). `/data/ml` nie jest wolumenem — po redeployu modele dotrenują się przy pierwszym zatwierdzeniu lub „Trenuj modele”; trwale: wolumen na `/data/ml` albo `ML_MODEL_DIR` na trwałej ścieżce spoza uploadów |
| `ML_AUTO_APPLY_THRESHOLD` | float | ma bezpieczny domyślny | **nie** | pewna sugestia = matched |
| `ML_DOCKIND_THRESHOLD` | float | ma bezpieczny domyślny | **nie** |  |
| `ML_MIN_EXAMPLES` | int | ma bezpieczny domyślny | **nie** | mniej = klasyfikator typu nie trenuje |
| `ML_AUTO_TRAIN` | bool | ma bezpieczny domyślny | **nie** | dotrenuj po każdym zatwierdzeniu |
| `ML_TRAIN_IN_BACKGROUND` | bool | ma bezpieczny domyślny | **nie** | False = synchronicznie (testy) |

## Pliki i kopie

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `UPLOADS_DIR` | str | ma bezpieczny domyślny | tak |  |
| `HOST_PROC_DIR` | str | ma bezpieczny domyślny | **nie** | /proc hosta zamontowany read-only (monitor: lista procesów całego serwera); brak = sam kontener |
| `MAX_UPLOAD_MB` | int | ma bezpieczny domyślny | **nie** |  |

## Progi biznesowe

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `DEMURRAGE_ALERT_DAYS` | int | ma bezpieczny domyślny | **nie** |  |
| `DEMURRAGE_DEFAULT_FREE_DAYS` | int | ma bezpieczny domyślny | **nie** | puste `demurrage_free_days` nie może wyciszać tematu — liczymy wg tej wartości |
| `CUSTOMS_ALERT_DAYS` | int | ma bezpieczny domyślny | **nie** | alert, gdy odprawa (ZLECONA/REWIZJA) trwa dłużej niż tyle dni od zlecenia |
| `COMPLAINT_AUTO_DRAFT_DAYS` | int | ma bezpieczny domyślny | **nie** | W11 #67: auto-szkic reklamacji, gdy kontener jest >= tyle dni po ETA bez dostawy |
| `COMPLAINT_DEADLINE_CARRIER_DAYS` | int | ma bezpieczny domyślny | **nie** | W11 #69: terminy przedawnienia (dni od utworzenia reklamacji) per typ adresata |
| `COMPLAINT_DEADLINE_INSURER_DAYS` | int | ma bezpieczny domyślny | **nie** |  |
| `COMPLAINT_DEADLINE_SUPPLIER_DAYS` | int | ma bezpieczny domyślny | **nie** |  |
| `COMPLAINT_DEADLINE_ALERT_DAYS` | int | ma bezpieczny domyślny | **nie** | alert tyle dni przed upływem terminu przedawnienia |

## Poczta

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `SMTP_HOST` | str | puste = funkcja wyłączona / auto | tak |  |
| `SMTP_PORT` | int | ma bezpieczny domyślny | tak |  |
| `SMTP_USER` | str | puste = funkcja wyłączona / auto | tak |  |
| `SMTP_PASSWORD` | str | SEKRET (ustaw w Coolify, nigdy w repo) | tak |  |
| `SMTP_FROM` | str | ma bezpieczny domyślny | tak |  |
| `INVITE_SMTP_HOST` | str | puste = funkcja wyłączona / auto | **nie** | osobny kanał SMTP tylko dla zaproszeń użytkowników (np. skrzynka example.com). Puste = użyj głównego SMTP (Resend). Pozwala wysyłać zaproszenia z innego adresu … |
| `INVITE_SMTP_PORT` | int | ma bezpieczny domyślny | **nie** |  |
| `INVITE_SMTP_USER` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `INVITE_SMTP_PASSWORD` | str | SEKRET (ustaw w Coolify, nigdy w repo) | **nie** |  |
| `INVITE_SMTP_FROM` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `MAIL_BACKEND` | str | puste = funkcja wyłączona / auto | tak | --- Awizacja dwuetapowa (maile do spedycji) --- graph = Microsoft Graph sendMail (M365, client credentials) / smtp / console (log). Puste = smtp, gdy ustawio… |
| `MS_TENANT_ID` | str | puste = funkcja wyłączona / auto | tak |  |
| `MS_CLIENT_ID` | str | puste = funkcja wyłączona / auto | tak |  |
| `MS_CLIENT_SECRET` | str | SEKRET (ustaw w Coolify, nigdy w repo) | tak |  |
| `MAIL_SENDER` | str | puste = funkcja wyłączona / auto | tak | skrzynka nadawcy w M365 (ograniczona Application Access Policy) |

## SharePoint

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `SHAREPOINT_TENANT_ID` | str | puste = funkcja wyłączona / auto | tak | --- SharePoint → sync kolejki (Graph app-only, Sites.Selected read); docs/SHAREPOINT-SYNC.md Włączone tylko, gdy wszystkie pola (poza interwałem) niepuste — … |
| `SHAREPOINT_CLIENT_ID` | str | puste = funkcja wyłączona / auto | tak |  |
| `SHAREPOINT_CLIENT_SECRET` | str | SEKRET (ustaw w Coolify, nigdy w repo) | tak |  |
| `SHAREPOINT_SITE` | str | puste = funkcja wyłączona / auto | tak | np. acme.sharepoint.com:/sites/Transport |
| `SHAREPOINT_QUEUE_PATH` | str | puste = funkcja wyłączona / auto | tak | np. Shared Documents/Kolejka/kolejka.xlsx |
| `SHAREPOINT_QUEUE_COMPANY` | str | puste = funkcja wyłączona / auto | tak | kod spółki (Company.code), do której idzie kolejka |
| `SHAREPOINT_QUEUE_INTERVAL_MINUTES` | float | ma bezpieczny domyślny | tak |  |
| `SHAREPOINT_AUTO_SYNC` | bool | ma bezpieczny domyślny | **nie** | okres przejściowy Excel ↔ aplikacja (decyzja 2026-09-28): domyślnie sync tylko ręcznie (przycisk); `true` = automat co N minut |

## Awizacja / RODO

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `AVIZO_STAGE1_DAYS` | int | ma bezpieczny domyślny | tak | ważność linku etapu 1 (dostawy) |
| `AVIZO_STAGE2_DAYS` | int | ma bezpieczny domyślny | tak | ważność linku etapu 2 (kierowcy) |
| `DRIVER_DATA_RETENTION_DAYS` | int | ma bezpieczny domyślny | tak | RODO: po zamknięciu zlecenia |

## Powiadomienia

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `TEAMS_WEBHOOK_URL` | str | puste = funkcja wyłączona / auto | tak |  |
| `DIGEST_HOUR` | int | ma bezpieczny domyślny | **nie** | godzina porannego digestu logistyki (czas polski, Europe/Warsaw) |

## Automatyzacje (n8n)

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `AUTOMATION_API_TOKEN` | str | SEKRET (ustaw w Coolify, nigdy w repo) | tak | --- Automatyzacje (n8n) --- Statyczny token serwisowy dla n8n: nagłówek X-Automation-Token zamiast logowania hasłem i odświeżania JWT. PUSTY = integracja WYŁ… |
| `AUTOMATION_API_TOKEN_PREVIOUS` | str | SEKRET; puste = tylko bieżący token | **nie** | ACL-005: poprzedni token n8n akceptowany obok nowego na czas rotacji (procedura: `docs/N8N.md` §4); po przełączeniu credentiala w n8n wyczyść |
| `AUTOMATION_TOKEN_EXPIRES` | str (RRRR-MM-DD) | puste = bez terminu | **nie** | ACL-005: po tej dacie token n8n (także poprzedni) nie działa (401); błędny format = token odrzucony |
| `AUTOMATION_ALLOWED_CIDRS` | str (CSV CIDR) | puste = z każdej sieci | **nie** | ACL-005: token n8n działa tylko z tych sieci (np. sieć Dockera `timporye-apps`); IP wg `TRUSTED_PROXY_*` |
| `AUTOMATION_ACTOR_LOGIN` | str | ma bezpieczny domyślny | tak | Login konta, na które podpisują się zmiany z n8n (atrybucja w audycie). Uprawnienia bierze z ROLI tego konta — n8n nie ma własnej, osobnej ścieżki autoryzacji. |
| `AUTOMATION_WEBHOOK_URL` | str | puste = funkcja wyłączona / auto | tak | Webhook automatyzacji dla zdarzeń wychodzących (Production URL triggera w n8n). Puste = wyłączone. Nazwa celowo NIE brzmi N8N_WEBHOOK_URL — tak nazywa się zm… |
| `AUTOMATION_WEBHOOK_SECRET` | str | SEKRET (ustaw w Coolify, nigdy w repo) | tak | Sekret podpisu HMAC-SHA256 ciała żądania (nagłówek X-Timporye-Signature). Puste = bez podpisu (wtedy webhook n8n musi być chroniony inaczej, np. header auth). |

## Rdzeń i baza

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `FRONTEND_DIST` | str | puste = funkcja wyłączona / auto | **nie** | ścieżka do builda panelu; puste = ../frontend/dist |

## Progi biznesowe

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `STALE_IMPORT_DAYS` | int | ma bezpieczny domyślny | **nie** | alert „stęchły import" master data: starszy niż N dni (0 nie ma sensu — min. 1) |

## Power BI / wywołania DLT

| Zmienna | Typ | Kategoria domyślnej | W compose | Przeznaczenie (z komentarza w kodzie) |
|---|---|---|---|---|
| `POWERBI_PROVIDER` | str | ma bezpieczny domyślny | **nie** | --- Wywołania-DLT / Power BI (SAP BW) --- off / mock / real |
| `POWERBI_WORKSPACE_ID` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `POWERBI_DATASET_STOCK` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `POWERBI_TABLE_STOCK` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `POWERBI_DATASET_VBBA` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `POWERBI_TABLE_VBBA` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `POWERBI_DATASET_ORDERS` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `POWERBI_TABLE_ORDERS` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `POWERBI_DATASET_USAGE` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `POWERBI_TABLE_USAGE` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `POWERBI_MERGE_KEY` | str | ma bezpieczny domyślny | **nie** | wspólna kolumna łączenia źródeł |
| `VBBA_OPEN_STATUSES` | str | ma bezpieczny domyślny | **nie** |  |
| `POWERBI_ORDERS_CONFIRMED_FIELD` | str | ma bezpieczny domyślny | **nie** | zlecenia sprzedaży (vbbe+likp): kolumny ilości potwierdzonej i niepotwierdzonej. Niepotwierdzone wchodzą w projekcję stanu (jak w arkuszu W). |
| `POWERBI_ORDERS_UNCONFIRMED_FIELD` | str | ma bezpieczny domyślny | **nie** |  |
| `POWERBI_LOCATION_FIELD` | str | ma bezpieczny domyślny | **nie** |  |
| `POWERBI_DLT_LOCATIONS` | str | puste = funkcja wyłączona / auto | **nie** | wartości/prefiksy lokalizacji = DLT (reszta = magazyn) |
| `PALLET_TARGET_DAYS` | int | ma bezpieczny domyślny | **nie** | kalibracja: docelowy zapas w dniach |
| `PALLET_URGENT_THRESHOLD` | float | ma bezpieczny domyślny | **nie** | kalibracja: próg palet „pilne” |
| `POWERBI_TENANT_ID` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `POWERBI_CLIENT_ID` | str | puste = funkcja wyłączona / auto | **nie** |  |
| `POWERBI_CLIENT_SECRET` | str | SEKRET (ustaw w Coolify, nigdy w repo) | **nie** |  |
| `POWERBI_ACCESS_TOKEN` | str | SEKRET (ustaw w Coolify, nigdy w repo) | **nie** | wklejony token (dev/ad-hoc) |
| `POWERBI_CA_BUNDLE` | str | puste = funkcja wyłączona / auto | **nie** | ścieżka CA bundle (proxy re-sygnujące TLS) |
| `POWERBI_SSL_VERIFY` | bool | ma bezpieczny domyślny | **nie** | False tylko dla dev |
| `POWERBI_CACHE_TTL_MIN` | int | ma bezpieczny domyślny | **nie** |  |
| `DLT_EMAIL` | str | puste = funkcja wyłączona / auto | **nie** | adresat wywołań palet |
| `DLT_CALL_EMAILS` | str | puste = funkcja wyłączona / auto | **nie** | lista adresów DLT (CSV) — fallback gdy magazyn DLT bez e-maila |
| `POWERBI_COLUMN_MAP` | str | puste = funkcja wyłączona / auto | **nie** | JSON {nasza_nazwa: nazwa_w_kostce} — remap kolumn |
| `PALLET_ALERT_INTERVAL_HOURS` | float | ma bezpieczny domyślny | **nie** | cykl alertów „pilne” |
| `PALLET_FORECAST_HORIZON_DAYS` | int | ma bezpieczny domyślny | **nie** | horyzont prognozy zapotrzebowania |
| `STAFFING_PALLETS_PER_PERSON` | int | ma bezpieczny domyślny | **nie** | predykcja obsady rozładunków: ile palet rozładowuje jedna osoba na zmianę |

## Dodane 2026-09-28 (poprawki z audytu)

| Zmienna | Typ | Domyślnie | Opis |
|---|---|---|---|
| `ALLOW_INSECURE_HTTP` | bool | `false` | instancja bez certyfikatu (tylko HTTP): zwalnia tylko wymóg SECURE_COOKIES (SEC-003) |
| `LOG_FILE` | str | puste | plik logów w wolumenie `/data/logs`, rotacja 10×10 MB (OBS-007) |
| `AUDIT_AUTH_RETENTION_DAYS` | int | `90` | retencja wpisów logowań w audit_log (GDPR-004) |
| `TOKEN_RETENTION_DAYS` | int | `30` | usuwanie wygasłych refresh/reset tokenów po N dniach od wygaśnięcia (OBS-011) |
| `SMS_RETENTION_DAYS` | int | `90` | retencja historii SMS (GDPR-007) |
| `CLIENT_ERROR_RETENTION_DAYS` | int | `30` | retencja błędów JS z przeglądarek (OBS-011) |
| `BACKUP_MAX_AGE_HOURS` | int | `194` | najstarsza kopia akceptowana przez cotygodniową weryfikację (backup w soboty) |
| `NOTIFICATION_RETENTION_DAYS` | int | `90` | usuwanie przeczytanych powiadomień (OBS-011); 90 dni = decyzja Aktualności 2026-10-01 (wcześniej domyślnie 180) |
| `LLM_MAX_CONCURRENCY` | int | `1` | ile równoległych wywołań lokalnego LLM (AI-002) |
| `LLM_WAIT_S` | float | `2` | ile czekać na wolny slot LLM przed odpowiedzią „zajęty” (AI-002) |
| `LLM_TIMEOUT_S` | int | `120` | limit czasu odpowiedzi asystenta (AI-002) |
| `ASSISTANT_RATE_LIMIT_PER_MINUTE` | int | `10` | limit pytań asystenta na użytkownika na minutę (AI-002) |

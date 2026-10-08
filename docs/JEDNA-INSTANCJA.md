# Kontrakt „jedna instancja” (ARCH-003)

TIMPORYE domyślnie działa jako **jeden proces uvicorna** (`Dockerfile.coolify`, bez
`--workers`, `WEB_CONCURRENCY` nieustawione = 1). Część stanu siedzi tylko w pamięci procesu.
Ten dokument mówi, co się dzieje, gdy pojawi się drugi proces: `WEB_CONCURRENCY=2` (uvicorn
sam czyta tę zmienną jako liczbę workerów) albo druga instancja na wspólnej bazie.

Zanim podniesiesz liczbę workerów lub instancji, przejdź przez tabelę. Każdy wiersz ze
statusem **psuje się** wymaga decyzji albo poprawki.

## Blokady, które już działają

| Blokada | Gdzie | Co robi |
|---|---|---|
| Start z wieloma workerami | `backend/app/rate_limit.py` `assert_worker_config()`, wołane w `main.validate_settings()` | `WEB_CONCURRENCY>1` dozwolone tylko na PostgreSQL (BUILD-003); na SQLite aplikacja odmawia startu. Na PG loguje budżet połączeń (workery × (`DB_POOL_SIZE`+`DB_MAX_OVERFLOW`+2)). Zakres 1–16 (walidacja `Settings`). |
| Lider pętli tła | `backend/app/leader.py` `Leadership`, `leader_loop()` (z `main.lifespan`) | Pętle tła i kolektor AIS startuje tylko proces trzymający sesyjny `pg_try_advisory_lock(crc32("timporye.job:__leader__"))` na własnym połączeniu (poza pulą). Pozostałe workery co 30 s próbują przejąć rolę — koniec procesu lidera albo zerwane połączenie zwalnia lock i następny worker startuje pętle. `monitor_sample` i zrzut applog biegną w każdym procesie. SQLite: zawsze lider. |
| Pętle tła | `backend/app/jobs.py` `job_lock()` / `_run()` | Każdy przebieg zadania bierze `pg_try_advisory_lock(crc32("timporye.job:<nazwa>"))` na własnym połączeniu. Zajęty = przebieg pominięty (log „pominięte — trwa w innym procesie”). Zwolnienie w `finally`, także przy wyjątku. Zerwane połączenie = serwer PG sam zwalnia lock. SQLite: no-op. |
| Kolektor AIS | `backend/app/tracking/ais.py` `ais_loop()` | Każda sesja websocket biega pod `job_lock("ais")`. Drugi proces czeka jak po pustej sesji (do 60 s) i próbuje znowu. Na bazie jest więc jedno połączenie z kluczem aisstream. |
| Instancja wtórna | `RUN_BACKGROUND_JOBS=false` (`main.lifespan`) | Instancja nie uruchamia pętli tła ani AIS. Nadal zalecane dla drugiego serwera. |

**Granica advisory locka:** chroni przed przebiegiem **równoczesnym**. Przy kilku workerach
jednej instancji pętle i tak prowadzi tylko lider (`leader.py`); dwa procesy mogą wykonać to
samo zadanie jeden po drugim tylko przy dwóch instancjach bez `RUN_BACKGROUND_JOBS=false`
albo w krótkim oknie przejęcia roli lidera. Przed
powtórną wysyłką chroni dedup w samych funkcjach, oparty na rekordach w bazie: SMS-y
(`SmsMessage`), digesty (per użytkownik i dzień) oraz powiadomienia. Wyjątek to
`verify_backup`: pamięta dzień przebiegu w pamięci procesu, więc przy dwóch procesach
weryfikacja kopii może się wykonać dwa razy w tym samym dniu. Jest to nieszkodliwe
(odczyt), ale zużywa CPU.

`monitor_sample` celowo **nie** bierze locka. Próbkuje CPU/RAM własnego procesu i zapisuje
je do jego pamięci, więc każdy proces musi robić to sam.

## Stan w pamięci procesu: co się psuje przy 2 procesach

| Mechanizm | Miejsce | Przy 2 workerach / instancjach | Status |
|---|---|---|---|
| Limiter nieudanych logowań (para IP+login 5, IP 20 / 15 min; konto ze wszystkich IP — progresywna przerwa od 10) | `backend/app/rate_limit.py` `LoginRateLimiter`, tabela `login_failures` (migracja `loginlim001`) | Stan w bazie: wszystkie procesy i instancje liczą razem, restart nie zeruje liczników | **zabezpieczone** (ARCH-003/SEC-012) |
| Limiter API per IP | `backend/app/rate_limit.py` `ApiRateLimiter`, `api_limiter` | Limit ×N (każdy worker liczy swoje połączenia) | akceptowalne (to ochrona przed zalaniem, nie przed zgadywaniem hasła); przy N workerach efektywnie do N × `API_RATE_LIMIT_PER_MINUTE` |
| Pętle tła (alerty, SMS „jutro”, digesty, reklamacje, awizacje, retencja, SharePoint, kongestia) | `backend/app/jobs.py`, `backend/app/leader.py`, `main.lifespan` | Bez locka każdy proces wysyłał SMS-y, e-maile i Teams | **zabezpieczone**: pętle tylko w procesie-liderze + advisory lock per przebieg (patrz wyżej) |
| Kolektor AIS (websocket) | `backend/app/tracking/ais.py` `ais_loop` | Dwa połączenia z jednym kluczem (limit dostawcy) i podwójne zapisy pozycji | **zabezpieczone** przez `job_lock("ais")` |
| Trening ML po zatwierdzeniu faktury | `backend/app/invoices/ml.py` `_train_worker` (wątek) | Dwa treningi naraz. Zapis `*.joblib` jest atomowy, ale każdy proces trzyma w pamięci inny model | psuje się łagodnie (niespójne podpowiedzi do restartu) |
| Device flow Power BI | `backend/app/routers/pallets.py` (wątek `complete_device_flow`) | Logowanie zaczęte w procesie A i sprawdzane w B daje „brak przepływu” | **psuje się**. Ponów próbę albo użyj sticky sessions. |
| Cache OCR (512 stron) | `backend/app/invoices/ocr.py` `_cache` | Podwójna praca (OCR 1–3 s na stronę) | akceptowalne |
| Cache packera wypełnienia | `backend/app/routers/containers_contents.py` `_PACKING_CACHE` | Podwójne liczenie | akceptowalne |
| Cache pogody i kursów NBP | `backend/app/tracking/weather.py` `_cache`, `backend/app/nbp.py` `_cache` | Podwójne zapytania do zewnętrznych API | akceptowalne |
| Bufor dziennika żądań i zadań | `backend/app/applog.py` `_requests`, `_jobs` | Każdy proces zrzuca własny bufor (`applog_loop` działa na każdej instancji) | działa |
| Monitor CPU/RAM (24 h) | `backend/app/monitoring.py` `HISTORY` | Panel admina pokazuje proces, który obsłużył żądanie | psuje się łagodnie (dane jednego procesu) |
| Ostatni błąd Teams | `backend/app/teams.py` `_last` | Jak wyżej | psuje się łagodnie |
| Tydzień weryfikacji backupu | `backend/app/jobs.py` `_verify_backup_fn` (`last_run_day`) | Możliwa druga weryfikacja tego samego dnia | akceptowalne (odczyt) |

## Warunki przed `WEB_CONCURRENCY=2` (N-22)

1. ~~Przenieś limiter logowań do bazy~~ — zrobione (`login_failures`, `loginlim001`).
2. ~~Pętle tła tylko w jednym workerze~~ — zrobione (lider, `leader.py`); `assert_worker_config()`
   przepuszcza `WEB_CONCURRENCY>1` na PostgreSQL.
3. Zaakceptuj albo napraw wiersze **psuje się** w tabeli (Power BI device flow — ponów próbę).
4. Sprawdź, że liczba workerów × (`DB_POOL_SIZE` + `DB_MAX_OVERFLOW` + 2) mieści się w
   `max_connections` Postgresa (domyślnie 100: przy puli 10+20 to najwyżej 3 workery — przy
   więcej workerach zmniejsz pulę, np. `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=10`). Aplikacja
   wypisuje ten budżet w logu przy starcie.
5. RAM: ~260 MB na worker (pomiar PERF-008) — limit pamięci kontenera ustaw z zapasem.

## Jak włączyć kilka workerów (BUILD-003)

Bez zmian w obrazie ani compose: ustaw w Coolify (Environment Variables aplikacji)
`WEB_CONCURRENCY=2` i zrób redeploy. `Dockerfile.coolify` uruchamia `uvicorn` bez
`--workers`, więc uvicorn sam bierze liczbę workerów z tej zmiennej; migracje (`alembic
upgrade head`) biegną raz, przed startem workerów. Po starcie w logu: jeden worker pisze
„Ten proces prowadzi pętle tła (lider)”, każdy — linię z budżetem połączeń. Powrót do
jednego procesu: usuń zmienną albo ustaw `WEB_CONCURRENCY=1`. Instancja wtórna (drugi
serwer) nadal może mieć `RUN_BACKGROUND_JOBS=false`, ale nie musi — lider jest jeden na bazę.

Uwaga: komentarz nad `CMD` w `Dockerfile.coolify` („aplikacja odmawia startu przy
WEB_CONCURRENCY>1, póki limiter logowań jest w pamięci”) jest nieaktualny od BUILD-003 —
do poprawienia przy najbliższej zmianie Dockerfile.

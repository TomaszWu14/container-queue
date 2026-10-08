# Monitor serwera — część 2: dziennik żądań, zadań tła i błędów

Data: 2026-09-24. Status: zaakceptowany projekt.

## Cel

Dziś żądania, wyjątki i przebiegi zadań tła idą tylko do stdout kontenera (Redeploy je kasuje).
Admin ma widzieć w aplikacji: błędne i wolne żądania, ruch w czasie, stan zadań tła i błędy frontu,
oraz dostać dzwonek, gdy coś się sypie.

## Decyzje

- Zapisujemy żądania z błędem (status ≥ 400) albo wolne (> 1000 ms); pozostałe tylko w licznikach minutowych.
- Pomijamy szum: `/api/health`, ścieżki spoza `/api/` (statyczne), 401 z `GET /api/auth/me`.
- Retencja 30 dni (czyszczenie raz na dobę).
- Alert: dzwonek dla aktywnych adminów (`notify`, kind `system-error`) przy nowym 5xx lub nieudanym
  zadaniu tła — max 1 na godzinę na rodzaj (`request` / `job`).
- Architektura: bufor w pamięci procesu → zapis do bazy co 30 s (osobna pętla w lifespan, działa też
  przy `RUN_BACKGROUND_JOBS=false`, bo każda instancja ma własne żądania). Utrata ≤ 30 s przy awarii — akceptowalna.

## Dane (migracja od `avatar001`)

- `request_logs`: id, at, method, path (maskowane `redact_tokens`), status, duration_ms, user_id (NULL),
  ip, request_id, error (Text, traceback 5xx przycięty do 4000). Indeks na `at`, `status`.
- `request_counters`: minute (DateTime, unikalny), total, c4xx, c5xx, dur_ms_sum.
- `job_runs`: id, job, fn, started_at, duration_ms, ok, detail (Text, wynik lub traceback, 2000 zn.). Indeks na `started_at`, `job`.

## API (admin)

- `GET /api/admin/logs/requests` — filtry: `status` (`4xx`/`5xx`/`slow`/kod), `q` (fragment ścieżki), `user_id`,
  `date_from`, `date_to`, `page`, `per_page` (≤ 200); zwraca `{total, items}` od najnowszych, z loginem użytkownika.
- `GET /api/admin/logs/traffic?hours=24` (≤ 168) — liczniki minutowe zagregowane do 5 min.
- `GET /api/admin/logs/jobs` — ostatni przebieg każdej pary job/fn + ostatnie 200 przebiegów.
- `GET /api/admin/logs/client-errors` — ostatnie 200 błędów frontu (istniejąca tabela `client_errors`).

## UI

Monitor serwera (zakładka System) dostaje podzakładki: **Zasoby** (obecny panel), **Żądania**
(wykres ruchu + tabela z filtrami, rozwijany wiersz z błędem i request-id), **Zadania tła**
(kafelki ostatniego przebiegu: OK/błąd, ile temu, czas; pod spodem historia), **Błędy frontu**.
Teksty: `i18n/features/monitor-logi.ts`.

## Poza zakresem

Alerty mailowe, eksport logów, logi dostępu uvicorn, metryki per endpoint (p95).

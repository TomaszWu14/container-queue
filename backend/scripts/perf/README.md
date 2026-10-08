# Skrypty pomiarowe audytu wydajności (staging)

Uruchamiasz **Ty** na stagingu z kopią schematu (reprezentatywny wolumen).
Agent nie ma i nie powinien mieć `DATABASE_URL` — zerowa ekspozycja danych.
Wynik wklej z powrotem do wątku, dołączę „przed/po" do odpowiednich PR-ów.

## 0. Włącz pg_stat_statements (raz)

Wymaga restartu PostgreSQL — rozszerzenie ładuje się przy starcie serwera.

```sql
-- w postgresql.conf (albo ALTER SYSTEM):
--   shared_preload_libraries = 'pg_stat_statements'
--   pg_stat_statements.track = 'top'
-- następnie RESTART serwera, potem:
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

W Coolify (Postgres jako usługa): dodaj `-c shared_preload_libraries=pg_stat_statements`
do polecenia/args kontenera bazy albo ustaw w konfiguracji, zrestartuj usługę `db`,
potem odpal `CREATE EXTENSION`.

## 1. Baseline PRZED #129 (przed `alembic upgrade head`)

```bash
psql "$DATABASE_URL" -f explain_index_audit.sql        > before_explain.txt
psql "$DATABASE_URL" -f index_and_statement_stats.sql  > before_stats.txt
```

## 2. Zastosuj #129 i zmierz PO

```bash
alembic upgrade head
psql "$DATABASE_URL" -f explain_index_audit.sql        > after_explain.txt
psql "$DATABASE_URL" -f index_and_statement_stats.sql  > after_stats.txt
```

Wklej `before_explain.txt` / `after_explain.txt` — porównamy `Seq Scan` → `Index Scan`
oraz `Buffers`/`actual time`. `*_stats.txt` służą do decyzji o nieużywanych indeksach
(A7) i do namierzenia najcięższych zapytań pod blok B.

## Uwaga o parametrach

`explain_index_audit.sql` używa zmiennych `psql` (`\set`). Podmień na realne ID z Twojej
bazy (albo zostaw — zapytania i tak pokażą wybór planu; liczności najlepiej realne).
Skrypty są **tylko do odczytu** (SELECT/EXPLAIN) — niczego nie zmieniają.

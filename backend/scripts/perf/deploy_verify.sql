-- deploy_verify.sql — weryfikacja stanu bazy dla deployu PR #126–#140.
-- Tylko odczyt. Uruchom DWA razy:
--   1) PRZED deployem  → zapisz jako baseline (oczekiwana wersja migracji: b2c4d6e8f0a1),
--   2) PO deployu      → weryfikacja (oczekiwana wersja migracji: d1e2f3a4b5c6).
-- Każda sekcja zwraca kolumnę `result` = PASS / FAIL / INFO, żeby dało się odhaczyć.
--
-- Użycie:  psql "$DATABASE_URL" -f backend/scripts/perf/deploy_verify.sql
-- (albo w kontenerze prod:  psql -U <user> -d <db> -f deploy_verify.sql)

\pset border 2
\echo ''
\echo '==================== 1. Wersja migracji Alembic ===================='
-- PASS jeśli baza jest na jednej ze znanych wersji: b2c4d6e8f0a1 (pre) lub d1e2f3a4b5c6 (post).
-- Interpretacja: PRZED deployem oczekuj b2c4d6e8f0a1, PO deployu oczekuj d1e2f3a4b5c6.
SELECT
  version_num,
  CASE version_num
    WHEN 'd1e2f3a4b5c6' THEN 'PASS (po deployu: missing_indexes zaaplikowane)'
    WHEN 'b2c4d6e8f0a1' THEN 'PASS (przed deployem: baseline, migracja jeszcze nie ruszyła)'
    ELSE 'FAIL — nieoczekiwana wersja, HALT deploy, nie improwizuj'
  END AS result
FROM alembic_version;

\echo ''
\echo '==================== 2. Indeksy INVALID (nieudany CONCURRENTLY) ===================='
-- Punkt 3 checklisty: żaden indeks nie może być INVALID. Nieudany CREATE INDEX CONCURRENTLY
-- zostawia indeks z indisvalid=false, który if_not_exists=True potem cicho pomija.
-- PASS = brak wierszy z FAIL. PRZED deployem to baseline (spodziewane 0),
-- PO deployu potwierdza, że migracja nie zostawiła kalekiego indeksu.
SELECT
  n.nspname            AS schema,
  c.relname            AS index_name,
  t.relname            AS table_name,
  'FAIL — indeks INVALID, ręcznie DROP INDEX i odtwórz (patrz runbook rollback)' AS result
FROM pg_index i
JOIN pg_class c ON c.oid = i.indexrelid
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT i.indisvalid
  AND n.nspname NOT IN ('pg_catalog', 'information_schema');

\echo '(brak wierszy powyżej = PASS: żaden indeks nie jest INVALID)'

\echo ''
\echo '==================== 3. Indeksy z PR #129 — istnieją i są VALID ===================='
-- Punkt 4 checklisty: 5 indeksów z migracji missing_indexes musi istnieć i być valid.
-- PRZED deployem oczekuj 5x MISSING (baseline), PO deployu oczekuj 5x PASS.
WITH expected(index_name, table_name) AS (
  VALUES
    ('ix_containers_order_id',       'containers'),
    ('ix_containers_forwarder_id',   'containers'),
    ('ix_containers_customs_status', 'containers'),
    ('ix_containers_wh_notify',      'containers'),
    ('ix_audit_entity',              'audit_log')
)
SELECT
  e.index_name,
  e.table_name,
  CASE
    WHEN c.oid IS NULL              THEN 'MISSING (OK przed deployem / FAIL po deployu)'
    WHEN NOT i.indisvalid          THEN 'FAIL — istnieje ale INVALID'
    ELSE 'PASS — istnieje i VALID'
  END AS result
FROM expected e
LEFT JOIN pg_class c   ON c.relname = e.index_name AND c.relkind = 'i'
LEFT JOIN pg_index i   ON i.indexrelid = c.oid
ORDER BY e.table_name, e.index_name;

\echo ''
\echo '==================== 4. Połączenia vs max_connections ===================='
-- Punkt 6 checklisty: pula #126 (pool_size=10 + max_overflow=20 = do 30/instancję) nie może
-- wysycić serwera. PASS jeśli aktualne użycie < 80% max_connections (zapas na reserved + peaki).
-- PRZED deployem = baseline liczby połączeń; PO deployu porównaj, czy nie skoczyła nienormalnie.
SELECT
  (SELECT count(*) FROM pg_stat_activity)                              AS used,
  current_setting('max_connections')::int                             AS max_conn,
  current_setting('superuser_reserved_connections')                   AS reserved,
  round(100.0 * (SELECT count(*) FROM pg_stat_activity)
        / current_setting('max_connections')::int, 1)                 AS pct_used,
  CASE
    WHEN (SELECT count(*) FROM pg_stat_activity)
         < 0.80 * current_setting('max_connections')::int
      THEN 'PASS — poniżej 80% limitu'
    ELSE 'FAIL — powyżej 80% limitu, ryzyko wysycenia puli, sprawdź liczbę instancji x 30'
  END AS result;

\echo ''
\echo '==================== 4b. Rozkład połączeń wg stanu (diagnostyka) ===================='
-- INFO: pomaga odróżnić zdrowy ruch od wycieku (dużo "idle in transaction" = problem z #126/#132).
SELECT state, count(*) AS conns, 'INFO' AS result
FROM pg_stat_activity
WHERE state IS NOT NULL
GROUP BY state
ORDER BY conns DESC;

\echo ''
\echo '==================== Koniec. Odhacz: 1 wersja / 2 brak INVALID / 3 5x indeks / 4 <80% ===================='

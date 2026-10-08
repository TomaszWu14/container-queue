-- Statystyki indeksów i zapytań. Tylko odczyt.
-- (A7) nieużywane indeksy: idx_scan = 0 po okresie realnego ruchu = kandydaci do usunięcia.
-- (blok B) najcięższe zapytania: wejście do optymalizacji N+1/agregacji.

\echo === Uzycie indeksow (idx_scan rosnaco) — kandydaci do usuniecia na dole/gorze listy ===
SELECT
  s.relname                                   AS tabela,
  s.indexrelname                              AS indeks,
  s.idx_scan                                  AS skany,
  s.idx_tup_read                              AS krotki_odczyt,
  pg_size_pretty(pg_relation_size(s.indexrelid)) AS rozmiar,
  i.indisunique                               AS unikalny
FROM pg_stat_user_indexes s
JOIN pg_index i ON i.indexrelid = s.indexrelid
WHERE s.schemaname = 'public'
ORDER BY s.idx_scan ASC, pg_relation_size(s.indexrelid) DESC;

\echo
\echo === Seq scan vs index scan na tabelach (wysoki seq_scan przy duzej tabeli = brak indeksu) ===
SELECT
  relname                 AS tabela,
  seq_scan                AS seq_skany,
  seq_tup_read            AS seq_krotki,
  idx_scan                AS idx_skany,
  n_live_tup              AS wiersze
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY seq_tup_read DESC;

\echo
\echo === Najciezsze zapytania (pg_stat_statements wg total_exec_time) — wejscie do bloku B ===
-- Wymaga wlaczonego pg_stat_statements (patrz README). Jesli brak rozszerzenia, pominie sie z bledem.
SELECT
  calls,
  round(total_exec_time::numeric, 1)  AS total_ms,
  round(mean_exec_time::numeric, 2)   AS mean_ms,
  rows,
  left(regexp_replace(query, '\s+', ' ', 'g'), 200) AS zapytanie
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 30;

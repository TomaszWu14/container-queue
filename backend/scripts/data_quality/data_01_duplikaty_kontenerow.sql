-- DATA-01. Cel: duplikaty numeru kontenera.
--   (a) ten sam numer w >1 AKTYWNYM rekordzie (status <> ZREALIZOWANY) — prawie na pewno błąd
--       importu/ręcznego wpisu (dwa rekordy tego samego fizycznego kontenera w kolejce);
--   (b) ten sam numer w historii — informacyjnie (fizyczny kontener wraca po miesiącach — to legalne).
-- Kolumna containers.container_no ma tylko indeks (bez UNIQUE) — baza nie pilnuje unikalności.
-- Oczekiwany wynik: (a) 0 wierszy; (b) tylko pary odległe w czasie (różnica notify_date > ~60 dni).
-- Tylko SELECT; można uruchamiać wielokrotnie.
SELECT 'a_aktywne' AS rodzaj, upper(replace(container_no, ' ', '')) AS numer,
       count(*) AS ile, array_agg(id ORDER BY id) AS id_rekordow,
       array_agg(DISTINCT company_id) AS spolki
FROM containers
WHERE status <> 'ZREALIZOWANY'
GROUP BY 2
HAVING count(*) > 1
UNION ALL
SELECT 'b_historia', upper(replace(container_no, ' ', '')), count(*),
       array_agg(id ORDER BY id), array_agg(DISTINCT company_id)
FROM containers
GROUP BY 2
HAVING count(*) > 1 AND max(notify_date) - min(notify_date) < 60
ORDER BY 1, 3 DESC;

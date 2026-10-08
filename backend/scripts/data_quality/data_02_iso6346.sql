-- DATA-02. Cel: numery kontenerów niezgodne z ISO 6346 (format 4 litery + 7 cyfr i cyfra kontrolna).
-- Reguła jak w backend/app/iso6346.py: A=10, kolejne litery +1 z pominięciem 11/22/33;
-- suma wartość*2^pozycja (pozycje 0..9) mod 11; reszta 10 = numer nieprawidłowy (reguła aplikacji;
-- norma dopuszcza 10→0 — patrz DATA ustalenie o regule).
-- Oczekiwany wynik: 0 wierszy (poza świadomie wpisanymi numerami tymczasowymi / lotniczymi AWB —
-- sprawdzić transport_type).
WITH letters(ch, val) AS (
  SELECT chr(64 + i),
         10 + (i - 1) + ((10 + (i - 1)) >= 11)::int + ((10 + (i - 1)) >= 21)::int
                     + ((10 + (i - 1)) >= 31)::int
  FROM generate_series(1, 26) AS i
), norm AS (
  SELECT id, company_id, status, transport_type::text AS transport,
         upper(replace(container_no, ' ', '')) AS n
  FROM containers
), calc AS (
  SELECT n.*,
         CASE WHEN n.n ~ '^[A-Z]{4}[0-9]{7}$' THEN (
           SELECT sum(CASE WHEN p <= 4 THEN l.val ELSE substr(n.n, p, 1)::int END
                      * (2 ^ (p - 1))::bigint) % 11
           FROM generate_series(1, 10) AS p
           LEFT JOIN letters l ON p <= 4 AND l.ch = substr(n.n, p, 1))
         END AS reszta
  FROM norm n
)
SELECT id, company_id, status, transport, n AS numer,
       CASE WHEN reszta IS NULL THEN 'zly_format'
            WHEN reszta = 10 THEN 'reszta_10'
            ELSE 'zla_cyfra_kontrolna (oczekiwana ' || reszta || ')' END AS problem
FROM calc
WHERE reszta IS NULL OR reszta = 10 OR reszta <> substr(n, 11, 1)::int
ORDER BY problem, id;

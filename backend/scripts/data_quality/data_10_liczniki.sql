-- DATA-10. Cel: liczniki/denormalizacje vs rzeczywiste rekordy.
--   orders.container_count (deklarowana liczba kontenerów zlecenia) vs kontenery z order_id;
--   supplier_doc_variants.docs_count/ok_count vs próbki (supplier_doc_samples.variant_id) — w kodzie
--     brak miejsca, które te liczniki aktualizuje (grep: tylko definicja w models/supplier_catalog.py);
--   pola tekstowe dublujące FK (customs_agency vs customs_agency_id, supplier_raw vs supplier_id,
--     order_numbers vs order_id) — rozjazd = dwie „prawdy" w UI/eksporcie;
--   transport_id: numeracja max+1 (routers/containers_common.py:75-95) — luki per prefiks.
-- Oczekiwany wynik: 0 w pierwszej części (poza świadomymi różnicami nazw z importu); luki — informacyjnie.
-- Tylko SELECT; można uruchamiać wielokrotnie.
SELECT 'orders.container_count <> liczba kontenerów z order_id' AS regula, count(*) AS ile
FROM orders o
WHERE EXISTS (SELECT 1 FROM containers c WHERE c.order_id = o.id)
  AND o.container_count <> (SELECT count(*) FROM containers c WHERE c.order_id = o.id)
UNION ALL
SELECT 'supplier_doc_variants.docs_count <> liczba próbek', count(*)
FROM supplier_doc_variants v
WHERE v.docs_count <> (SELECT count(*) FROM supplier_doc_samples s WHERE s.variant_id = v.id)
UNION ALL
SELECT 'containers.customs_agency (tekst) <> nazwa ze słownika', count(*)
FROM containers c JOIN customs_agencies a ON a.id = c.customs_agency_id
WHERE c.customs_agency <> '' AND upper(trim(c.customs_agency)) <> upper(trim(a.name))
UNION ALL
SELECT 'containers.supplier_raw <> nazwa dostawcy (supplier_id)', count(*)
FROM containers c JOIN suppliers s ON s.id = c.supplier_id
WHERE c.supplier_raw <> '' AND upper(trim(c.supplier_raw)) <> upper(trim(s.name))
UNION ALL
SELECT 'containers.order_numbers nie zawiera orders.number (order_id)', count(*)
FROM containers c JOIN orders o ON o.id = c.order_id
WHERE position(o.number IN c.order_numbers) = 0;

-- Luki w numeracji transport_id per prefiks (np. AT-2026-): max numer vs liczba rekordów.
SELECT regexp_replace(transport_id, '[0-9]+$', '') AS prefiks, count(*) AS rekordow,
       max(substring(transport_id FROM '([0-9]+)$')::int) AS max_numer,
       max(substring(transport_id FROM '([0-9]+)$')::int) - count(*) AS luk
FROM containers WHERE transport_id ~ '-[0-9]+$'
GROUP BY 1 ORDER BY 1;

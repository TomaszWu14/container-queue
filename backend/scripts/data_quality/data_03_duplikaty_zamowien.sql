-- DATA-03. Cel: duplikaty numerów zamówień „po normalizacji" (UNIQUE w bazie łapie tylko identyczny
-- tekst w spółce; spacje, wielkość liter, wiodące zera czy sufiksy przechodzą).
-- Tabele: orders(number), purchase_orders(order_no), sap_orders(order_number) — per spółka.
-- Oczekiwany wynik: 0 wierszy.
SELECT 'orders' AS tabela, company_id, upper(regexp_replace(number, '[^0-9A-Za-z]', '', 'g')) AS klucz,
       count(*) AS ile, array_agg(number ORDER BY id) AS warianty
FROM orders GROUP BY 1, 2, 3 HAVING count(*) > 1
UNION ALL
SELECT 'purchase_orders', company_id, upper(regexp_replace(order_no, '[^0-9A-Za-z]', '', 'g')),
       count(*), array_agg(order_no ORDER BY id)
FROM purchase_orders GROUP BY 1, 2, 3 HAVING count(*) > 1
UNION ALL
SELECT 'sap_orders', company_id, upper(regexp_replace(order_number, '[^0-9A-Za-z]', '', 'g')),
       count(*), array_agg(order_number ORDER BY id)
FROM sap_orders GROUP BY 1, 2, 3 HAVING count(*) > 1
ORDER BY 1, 4 DESC;

-- Ten sam numer PO przypięty w order_numbers wielu AKTYWNYCH kontenerów tej samej spółki
-- (legalne przy PO na kilka kontenerów — informacyjnie, do przeglądu przy dużych liczbach).
SELECT c.company_id, t.po, count(*) AS kontenerow, array_agg(c.container_no ORDER BY c.id) AS kontenery
FROM containers c
CROSS JOIN LATERAL regexp_split_to_table(c.order_numbers, '[^0-9A-Za-z-]+') AS t(po)
WHERE c.status <> 'ZREALIZOWANY' AND t.po <> ''
GROUP BY 1, 2 HAVING count(*) > 3
ORDER BY 3 DESC LIMIT 50;

-- DATA-08. Cel: „sieroty" w relacjach trzymanych jako tekst/int BEZ klucza obcego.
--   audit_log.entity_id -> containers (brak FK: historia usuniętych kontenerów — oczekiwane, liczymy);
--   order_items (EKPO, klucz tekstowy order_number) bez kontenera, który ma ten numer w order_numbers;
--   sap_orders (EKKO) bez pozycji order_items i odwrotnie;
--   goods_receipt_lines bez odpowiadającej pozycji order_items (klucz spółka+zamówienie+pozycja);
--   tokeny containers.order_numbers bez żadnej pozycji SAP (kontener „bez zawartości");
--   powiązania wskazujące kontener/zamówienie INNEJ spółki (FK nie pilnuje spójności spółki).
-- Oczekiwany wynik: przyjęcia bez pozycji = 0; „innej spółki" = 0; pozostałe — liczby do
-- monitorowania trendu (rosnące = rozjazd importów SAP <-> kolejka).
-- Tylko SELECT; można uruchamiać wielokrotnie.
WITH tokens AS (
  SELECT c.id, c.company_id, t.po
  FROM containers c
  CROSS JOIN LATERAL regexp_split_to_table(c.order_numbers, '[^0-9A-Za-z-]+') AS t(po)
  WHERE t.po <> ''
)
SELECT 'audit_log(containers) -> nieistniejący kontener' AS relacja, count(*) AS ile
FROM audit_log a WHERE a.entity_type = 'containers'
  AND NOT EXISTS (SELECT 1 FROM containers c WHERE c.id = a.entity_id)
UNION ALL
SELECT 'order_items: zamówienie bez kontenera w kolejce', count(DISTINCT (oi.company_id, oi.order_number))
FROM order_items oi
WHERE NOT EXISTS (SELECT 1 FROM tokens t WHERE t.company_id = oi.company_id AND t.po = oi.order_number)
UNION ALL
SELECT 'sap_orders (EKKO) bez pozycji order_items', count(*)
FROM sap_orders s WHERE NOT EXISTS (SELECT 1 FROM order_items oi
  WHERE oi.company_id = s.company_id AND oi.order_number = s.order_number)
UNION ALL
SELECT 'order_items bez nagłówka EKKO', count(DISTINCT (oi.company_id, oi.order_number))
FROM order_items oi WHERE NOT EXISTS (SELECT 1 FROM sap_orders s
  WHERE s.company_id = oi.company_id AND s.order_number = oi.order_number)
UNION ALL
SELECT 'goods_receipt_lines bez pozycji order_items', count(*)
FROM goods_receipt_lines g WHERE NOT EXISTS (SELECT 1 FROM order_items oi
  WHERE oi.company_id = g.company_id AND oi.order_number = g.order_number AND oi.position = g.position)
UNION ALL
SELECT 'aktywny kontener: numer PO bez pozycji SAP', count(DISTINCT t.id)
FROM tokens t JOIN containers c ON c.id = t.id AND c.status <> 'ZREALIZOWANY'
WHERE NOT EXISTS (SELECT 1 FROM order_items oi WHERE oi.company_id = t.company_id AND oi.order_number = t.po)
UNION ALL
SELECT 'sap_orders.container_id -> kontener innej spółki', count(*)
FROM sap_orders s JOIN containers c ON c.id = s.container_id WHERE c.company_id <> s.company_id
UNION ALL
SELECT 'purchase_orders.container_id -> kontener innej spółki', count(*)
FROM purchase_orders p JOIN containers c ON c.id = p.container_id WHERE c.company_id <> p.company_id
UNION ALL
SELECT 'containers.order_id -> zamówienie innej spółki', count(*)
FROM containers c JOIN orders o ON o.id = c.order_id WHERE o.company_id <> c.company_id
UNION ALL
SELECT 'material_units: materiał nieużywany w order_items', count(DISTINCT m.material_no)
FROM material_units m WHERE NOT EXISTS (SELECT 1 FROM order_items oi WHERE oi.material = m.material_no);

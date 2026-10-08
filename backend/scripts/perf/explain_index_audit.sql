-- EXPLAIN (ANALYZE, BUFFERS) dla zapytań, które pokrywają indeksy z PR #129 (A1/A2/A6).
-- Tylko odczyt. Uruchom PRZED i PO `alembic upgrade head`, porównaj plany
-- (Seq Scan -> Index Scan) oraz actual time / Buffers.
--
-- Podmień poniższe ID/daty na realne z Twojej bazy (albo zostaw przykładowe).
\set fwd_id      1
\set wh_id       1
\set order_no    '\'ZAM/2026/0001\''
\set date_from   '\'2026-06-01\''
\set date_to     '\'2026-07-31\''
\set audit_id    1

\echo === A1: scope roli spedytora (ix_containers_forwarder_id) ===
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM containers
WHERE forwarder_id = :fwd_id
ORDER BY notify_date ASC NULLS LAST, id;

\echo === A1+A6: scope magazynu + zakres kalendarza (ix_containers_wh_notify) ===
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM containers
WHERE warehouse_id = :wh_id
  AND notify_date >= :date_from
  AND notify_date <= :date_to
ORDER BY notify_date, id;

\echo === A1: sam scope magazynu, rownosc (kolumna wiodaca ix_containers_wh_notify) ===
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM containers WHERE warehouse_id = :wh_id;

\echo === A2: JOIN Order po numerze zamowienia (ix_containers_order_id) ===
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.* FROM containers c
LEFT JOIN orders o ON o.id = c.order_id
WHERE o.number = :order_no;

\echo === A6: filtr statusu celnego (ix_containers_customs_status) ===
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM containers
WHERE customs_status IN ('ZLECONA', 'REWIZJA');

\echo === A6: historia audytu encji (ix_audit_entity) ===
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM audit_log
WHERE entity_type = 'container' AND entity_id = :audit_id
ORDER BY created_at DESC;

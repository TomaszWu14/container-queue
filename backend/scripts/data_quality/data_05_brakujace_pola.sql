-- DATA-05. Cel: pola wymagane przez logikę, a puste (baza ich nie wymusza — brak CHECK).
-- Reguły wyprowadzone z kodu: Container.is_delayed/delayed_clause (ETA/notify_date), kolejka
-- (notify_date = klucz kolejki), limit dzienny magazynu (warehouse_id), transport_id (nadawany
-- automatycznie — unikalny), awizacja (planning_status POTWIERDZONE ⇒ planning_confirmed_at).
-- Oczekiwany wynik: 0 w każdej regule (poza świadomymi wyjątkami opisanymi w komentarzu reguły).
SELECT reguła, count(*) AS ile, (array_agg(id ORDER BY id))[1:20] AS przyklady_id
FROM (
  SELECT id, 'W_TRANSPORCIE/W_PORCIE bez ETA' AS reguła FROM containers
   WHERE status IN ('W_TRANSPORCIE', 'W_PORCIE') AND eta IS NULL
  UNION ALL SELECT id, 'AWIZOWANY/W_DOSTAWIE bez daty awizacji' FROM containers
   WHERE status IN ('AWIZOWANY', 'W_DOSTAWIE') AND notify_date IS NULL
  UNION ALL SELECT id, 'AWIZOWANY/W_DOSTAWIE/DOSTARCZONY bez magazynu (nie tranzyt)' FROM containers
   WHERE status IN ('AWIZOWANY', 'W_DOSTAWIE', 'DOSTARCZONY') AND warehouse_id IS NULL AND NOT is_transit
  UNION ALL SELECT id, 'aktywny bez transport_id' FROM containers
   WHERE transport_id IS NULL AND status <> 'ZREALIZOWANY'
  UNION ALL SELECT id, 'ODPRAWA, a status celny BRAK' FROM containers
   WHERE status = 'ODPRAWA' AND customs_status = 'BRAK'
  UNION ALL SELECT id, 'agencja celna tylko tekstem (bez customs_agency_id)' FROM containers
   WHERE customs_agency <> '' AND customs_agency_id IS NULL
  UNION ALL SELECT id, 'dostawca tylko tekstem (supplier_raw bez supplier_id)' FROM containers
   WHERE supplier_raw <> '' AND supplier_id IS NULL
  UNION ALL SELECT id, 'planning POTWIERDZONE bez planning_confirmed_at' FROM containers
   WHERE planning_status = 'POTWIERDZONE' AND planning_confirmed_at IS NULL
  UNION ALL SELECT id, 'planning WYSLANE bez planning_sent_at' FROM containers
   WHERE planning_status = 'WYSLANE' AND planning_sent_at IS NULL
  UNION ALL SELECT id, 'powód „specjalny" bez flagi is_special' FROM containers
   WHERE special_reason IS NOT NULL AND NOT is_special
  UNION ALL SELECT id, 'dostawca bez nazwy' FROM suppliers WHERE trim(name) = ''
) x
GROUP BY reguła
ORDER BY ile DESC;

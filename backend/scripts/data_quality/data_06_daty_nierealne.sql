-- DATA-06. Cel: daty nierealne / sprzeczne (brak CHECK w bazie; import Excela/SAP i ręczne wpisy).
--   ETA < ETD, notify_date < ETD, ATD przed ETD, rok poza 2020–2030, rozładunek stop < start,
--   completed_at przed created_at, EKKO: data dokumentu po planowanej wysyłce.
-- Oczekiwany wynik: 0 w każdej regule; zakres lat dostosuj parametrem (tu 2020–2030).
SELECT reguła, count(*) AS ile, (array_agg(id ORDER BY id))[1:20] AS przyklady_id
FROM (
  SELECT id, 'ETA < ETD' AS reguła FROM containers WHERE eta < etd
  UNION ALL SELECT id, 'awizacja przed ETD' FROM containers WHERE notify_date < etd
  UNION ALL SELECT id, 'ATD przed ETD' FROM containers WHERE atd < etd
  UNION ALL SELECT id, 'rok ETA/ETD/awizacji/ATD poza 2020-2030' FROM containers
   WHERE extract(year FROM eta) NOT BETWEEN 2020 AND 2030
      OR extract(year FROM etd) NOT BETWEEN 2020 AND 2030
      OR extract(year FROM notify_date) NOT BETWEEN 2020 AND 2030
      OR extract(year FROM atd) NOT BETWEEN 2020 AND 2030
  UNION ALL SELECT id, 'tranzyt > 120 dni (ETA - ETD)' FROM containers WHERE eta - etd > 120
  UNION ALL SELECT id, 'rozładunek: koniec przed startem' FROM containers
   WHERE unload_finished_at < unload_started_at
  UNION ALL SELECT id, 'rozładunek dłuższy niż 24 h' FROM containers
   WHERE unload_finished_at - unload_started_at > interval '24 hours'
  UNION ALL SELECT id, 'completed_at przed created_at' FROM containers WHERE completed_at < created_at
  UNION ALL SELECT id, 'updated_at przed created_at' FROM containers WHERE updated_at < created_at
  UNION ALL SELECT id, 'created_at w przyszłości (UTC)' FROM containers
   WHERE created_at > (now() AT TIME ZONE 'UTC') + interval '1 hour'
  UNION ALL SELECT id, 'EKKO: data dokumentu po planowanej wysyłce' FROM sap_orders
   WHERE doc_date > planned_ship_date
  UNION ALL SELECT id, 'EKKO: rok daty dokumentu poza 2020-2030' FROM sap_orders
   WHERE extract(year FROM doc_date) NOT BETWEEN 2020 AND 2030
) x
GROUP BY reguła
ORDER BY ile DESC;

-- Daty zapisane jako TEKST (purchase_orders.ready_date / oem_sample_date — String(60)):
-- ile wartości nie parsuje się jako data w typowych formatach (DD.MM.YYYY / YYYY-MM-DD).
SELECT 'purchase_orders.ready_date' AS pole, count(*) FILTER (WHERE ready_date <> '') AS wypelnione,
       count(*) FILTER (WHERE ready_date <> ''
         AND ready_date !~ '^\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})\s*$') AS nie_data
FROM purchase_orders
UNION ALL
SELECT 'purchase_orders.oem_sample_date', count(*) FILTER (WHERE oem_sample_date <> ''),
       count(*) FILTER (WHERE oem_sample_date <> ''
         AND oem_sample_date !~ '^\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})\s*$')
FROM purchase_orders;

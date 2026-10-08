-- DATA-07. Cel: sprzeczność status ↔ daty/znaczniki kontenera.
-- Reguły z kodu: completed_at ustawiane przy przejściu na ZREALIZOWANY i czyszczone przy cofnięciu
-- (routers/containers_write.py:199); ATD „uzupełniana po dostawie" (models/container.py);
-- is_delayed nie dotyczy statusów końcowych; etap rampy (ramp_stage) tylko w W_DOSTAWIE/DOSTARCZONY.
-- Oczekiwany wynik: 0 w regułach twardych (oznaczonych !), reszta — sygnał do przeglądu.
SELECT reguła, count(*) AS ile, (array_agg(id ORDER BY id))[1:20] AS przyklady_id
FROM (
  SELECT id, '! ZREALIZOWANY bez completed_at' AS reguła FROM containers
   WHERE status = 'ZREALIZOWANY' AND completed_at IS NULL
  UNION ALL SELECT id, '! completed_at przy statusie innym niż ZREALIZOWANY' FROM containers
   WHERE status <> 'ZREALIZOWANY' AND completed_at IS NOT NULL
  UNION ALL SELECT id, 'DOSTARCZONY/ZREALIZOWANY bez ATD' FROM containers
   WHERE status IN ('DOSTARCZONY', 'ZREALIZOWANY') AND atd IS NULL
  UNION ALL SELECT id, 'ATD w przyszłości' FROM containers
   WHERE atd > (now() AT TIME ZONE 'Europe/Warsaw')::date
  UNION ALL SELECT id, 'status przed przypłynięciem, a ETA > 30 dni temu' FROM containers
   WHERE status IN ('ZAPOWIEDZIANY', 'W_PRODUKCJI', 'TRANSPORT_WSTEPNY', 'W_TRANSPORCIE')
     AND eta < (now() AT TIME ZONE 'Europe/Warsaw')::date - 30
  UNION ALL SELECT id, 'aktywny, awizacja > 60 dni temu (zapomniany w kolejce)' FROM containers
   WHERE status NOT IN ('DOSTARCZONY', 'ZREALIZOWANY')
     AND notify_date < (now() AT TIME ZONE 'Europe/Warsaw')::date - 60
  UNION ALL SELECT id, 'status celny ODPRAWIONY/ROZLICZONY bez customs_date' FROM containers
   WHERE customs_status::text IN ('ODPRAWIONY', 'ROZLICZONY') AND customs_date IS NULL
  UNION ALL SELECT id, 'rozładunek rozpoczęty, status sprzed dostawy' FROM containers
   WHERE unload_started_at IS NOT NULL
     AND status IN ('ZAPOWIEDZIANY', 'W_PRODUKCJI', 'TRANSPORT_WSTEPNY', 'W_TRANSPORCIE', 'W_PORCIE')
  UNION ALL SELECT id, 'etap rampy przy statusie sprzed dostawy' FROM containers
   WHERE ramp_stage IS NOT NULL
     AND status NOT IN ('AWIZOWANY', 'W_DOSTAWIE', 'DOSTARCZONY', 'ZREALIZOWANY')
  UNION ALL SELECT id, 'faktura frachtowa ZAAKCEPTOWANA bez approved_at' FROM freight_invoices
   WHERE status = 'ZAAKCEPTOWANA' AND approved_at IS NULL
) x
GROUP BY reguła
ORDER BY ile DESC;

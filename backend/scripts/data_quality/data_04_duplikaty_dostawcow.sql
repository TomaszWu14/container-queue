-- DATA-04. Cel: duplikaty w kartotece dostawców (suppliers).
--   (a) ten sam kod SAP (LIFNR) na >1 rekordzie kartoteki globalnej — import LFA1 bierze pierwszy
--       (build_plan: by_code.setdefault), drugi „wisi"; UNIQUE planowany (kartoteka002) — brak w bazie;
--   (b) ta sama nazwa po normalizacji (bez interpunkcji, form prawnych) w tym samym zakresie;
--   (c) ten sam NIP/VAT na >1 rekordzie.
-- Oczekiwany wynik: 0 wierszy w (a) i (c); (b) do przeglądu (aliasy / scalenie w panelu słowników).
SELECT 'a_sap_code' AS rodzaj, coalesce(client_company_id, 0) AS zakres, sap_code AS klucz,
       count(*) AS ile, array_agg(id ORDER BY id) AS id_rekordow
FROM suppliers WHERE sap_code <> '' GROUP BY 2, 3 HAVING count(*) > 1
UNION ALL
SELECT 'b_nazwa', coalesce(client_company_id, 0),
       regexp_replace(upper(name), '[^A-Z0-9]|CO|LTD|LIMITED|COMPANY|SP ?Z ?O ?O|GMBH', '', 'g'),
       count(*), array_agg(id ORDER BY id)
FROM suppliers GROUP BY 2, 3 HAVING count(*) > 1
UNION ALL
SELECT 'c_vat', coalesce(client_company_id, 0), upper(regexp_replace(vat, '[^0-9A-Za-z]', '', 'g')),
       count(*), array_agg(id ORDER BY id)
FROM suppliers WHERE vat <> '' GROUP BY 2, 3 HAVING count(*) > 1
ORDER BY 1, 4 DESC;

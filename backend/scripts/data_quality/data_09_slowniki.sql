-- DATA-09. Cel: wartości spoza słowników w kolumnach tekstowych (VARCHAR bez CHECK — poza natywnymi
-- ENUM-ami baza nie pilnuje wartości). Dozwolone wartości z kodu: ConsolidationStatus, CartStatus,
-- OnCarriage (models/enums.py), Container.RAMP_STAGES (models/container.py), SPECIAL_REASONS
-- (schemas/containers.py), Supplier.sap_status (importers/lfa1.py), FreightInvoice.status
-- (models/transport.py: NOWA/DO_AKCEPTACJI/ZAAKCEPTOWANA/ODRZUCONA), slot_time HH:MM.
-- Ilości w order_items trzymane jako TEKST — sprawdzamy, czy parsują się do liczby.
-- Oczekiwany wynik: 0 wierszy (poza ostatnią sekcją rozkładu container_size — do przeglądu).
-- Tylko SELECT; można uruchamiać wielokrotnie.
SELECT 'containers.consolidation_status' AS kolumna, consolidation_status AS wartosc, count(*) AS ile
FROM containers WHERE consolidation_status NOT IN ('otwarty', 'wypelniony', 'zamkniety') GROUP BY 2
UNION ALL
SELECT 'containers.ramp_stage', ramp_stage, count(*) FROM containers
WHERE ramp_stage IS NOT NULL AND ramp_stage NOT IN ('PODSTAWIONY', 'ROZLADOWANY', 'PRZYJETY') GROUP BY 2
UNION ALL
SELECT 'containers.special_reason', special_reason, count(*) FROM containers
WHERE special_reason IS NOT NULL AND special_reason NOT IN
  ('zlecenie_klienta', 'pilne', 'kontrola_jakosci', 'nowe_produkty', 'nowy_producent') GROUP BY 2
UNION ALL
SELECT 'containers.slot_time', slot_time, count(*) FROM containers
WHERE slot_time <> '' AND slot_time !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' GROUP BY 2
UNION ALL
SELECT 'containers.on_carriage', on_carriage, count(*) FROM containers
WHERE on_carriage IS NOT NULL AND on_carriage NOT IN ('drogowo', 'intermodal') GROUP BY 2
UNION ALL
SELECT 'suppliers.sap_status', sap_status, count(*) FROM suppliers
WHERE sap_status NOT IN ('active', 'blocked', 'inactive_in_sap') GROUP BY 2
UNION ALL
SELECT 'suppliers.country', country, count(*) FROM suppliers
WHERE country <> '' AND country !~ '^[A-Z]{2}$' GROUP BY 2
UNION ALL
SELECT 'freight_invoices.status', status, count(*) FROM freight_invoices
WHERE status NOT IN ('NOWA', 'DO_AKCEPTACJI', 'ZAAKCEPTOWANA', 'ODRZUCONA') GROUP BY 2
UNION ALL
SELECT 'freight_invoices.currency', currency, count(*) FROM freight_invoices
WHERE currency !~ '^[A-Z]{3}$' GROUP BY 2
UNION ALL
SELECT 'purchase_orders.cart_status', cart_status, count(*) FROM purchase_orders
WHERE cart_status NOT IN ('w_koszyku', 'zwolnione', 'przypisane', 'zablokowane') GROUP BY 2
UNION ALL
SELECT 'order_items.quantity (nie liczba)', left(quantity, 20), count(*) FROM order_items
WHERE quantity <> '' AND replace(replace(quantity, ' ', ''), ',', '.') !~ '^-?[0-9]+(\.[0-9]+)?$'
GROUP BY 2
UNION ALL
SELECT 'order_items.quantity (separator tysięcy: 1.234,000 / 1,234.00)', left(quantity, 20), count(*)
FROM order_items WHERE quantity ~ '[0-9][.,][0-9]{3}[.,]' GROUP BY 2
ORDER BY 1, 3 DESC;

-- Rozkład container_size (literówki typu 40HC / 40'HC / 40 HC) — do przeglądu, nie błąd twardy.
SELECT container_size, count(*) AS ile FROM containers GROUP BY 1 ORDER BY 2 DESC LIMIT 30;

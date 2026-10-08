# Profil dostawcy — etap 3: jednostki, wagi netto, kontrole — plan

Spec: `docs/superpowers/specs/2026-09-24-profil-dostawcy-ci-pl-agencja-design.md` (przepływ, kroki 5–7).
Poprzednio: etap 2 `2026-09-25-profil-dostawcy-2-ekstrakcja.md`.

**Cel:** wynik kontroli dokumentu faktury w API (`GET /api/invoice-jobs/{id}/checks`). Bez UI
(widok przy dokumencie = etap 4, razem z kreatorem).

## Decyzje

- Kontrole liczone **przy odczycie** z bieżących pozycji (edycja w weryfikacji od razu zmienia
  wynik). Z ekstrakcji zapisujemy tylko to, czego pozycje nie niosą: kolumna
  `invoice_jobs.check_data` JSON = `{doc_total, pl_qty: {REF: ilość}}` (migracja `kontrole001`).
- Tolerancja: `|a − b| / |b| ≤ tol %` (jak `apply_supplier_rules` w compare); granica wlicza się.
  Tolerancje z profilu dostawcy (także `draft`); bez profilu 0,5 % / 0 %.
- Jednostka podstawowa: `UomConversion` (import master/MARM) przez istniejące `uom.get_factor`
  (port `compare/uom.py` był już w repo); pusta jednostka na fakturze = jednostka podstawowa.
  Jednostka uzupełniająca: `Material.suppl_unit/suppl_factor`. Cena = kwota / ilość podstawowa.
- Waga netto per REF: z faktury, uzupełniona z PL (istniejące `_fill_weight`). MARM w repo ma tylko
  wagę brutto (BRGEW) — brak wagi netto = flaga `missing: weight`, bez zapasu z master data.
- CI↔PL po znormalizowanym REF z dokumentów (ta sama jednostka dostawcy); CI↔SAP po naszym REF
  w jednostce podstawowej: pozycje `OrderItem` zamówień `SapOrder.container_id = kontener`.

## Zadania

1. `packing_list.qty_map_from_items`; `pipeline.pl_maps_for` (wagi + ilości, ta sama selekcja PL;
   `weight_map_for` jako wrapper); `process_job` zapisuje `check_data`.
2. `models/invoices.py` `InvoiceJob.check_data` + migracja `kontrole001` (od `log001`).
3. `invoices/checks.py`: `diff_pct`, `within`, `order_qty`, `job_checks` → `{profile, tol_*,
   amount, refs[{ref, qty, qty_base, base_uom, qty_suppl, suppl_unit, price_base, weight_net,
   ci_pl, ci_order, missing}], ok}`.
4. `routers/invoice_checks.py` (osobny plik — `invoices.py` blisko limitu 500 linii).
5. Testy `tests/test_invoices_checks.py`: kartony → szt. → pary, cena za szt., waga z PL,
   suma OK, CI≠PL poza tolerancją 0 %, w tolerancji 2 %, CI↔SAP OK, braki CN/nazwy/wagi,
   granice tolerancji.

## Poza zakresem

- Ostrzeżenie „słowa kluczowe ≠ dostawca kontenera”; pasek „Profil · CI str. … · PL str. …”
  i prezentacja wyników w UI (etap 4). Eksport „Kartoteka symboli” (etap 5).

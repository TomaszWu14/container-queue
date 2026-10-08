# Profil dostawcy — etap 2: ekstrakcja wg profilu — plan

Spec: `docs/superpowers/specs/2026-09-24-profil-dostawcy-ci-pl-agencja-design.md` (przepływ, kroki 1–4).
Etap 1 (model `SupplierDocProfile` + API): `2026-09-24-profil-dostawcy-1-model.md`.

**Cel:** pipeline faktur (`backend/app/invoices/`) czyta profil dostawcy: mapy kolumn CI/PL,
znacznik stron PL, rodzaj REF i słowa kluczowe. Bez migracji, bez UI.

## Zasady

- Mapa CI: **aktywny** profil (`ci_map`) → stare `Supplier.column_map` → auto-detekcja nagłówków.
  Profil `draft` nie działa automatycznie. Mapa PL: aktywny `pl_map` → auto.
- Role kolumn = `extractor.COLUMN_ROLES`; nazwy z compare mapowane przez `extractor.ROLE_ALIASES`
  (`description→desc`, `quantity→qty`, `amount→net`, `net_weight→weight_net`,
  `gross_weight→weight_gross`, `packages→cartons`; `skip` = pomijane). Istniejące mapy bez zmian.
- Rozpoznanie dostawcy po `keywords` tylko gdy kontener/formularz nie wskazują dostawcy; tylko
  aktywne profile spółki kontenera; remis/brak trafień → brak dostawcy (operator wybiera).
- `ref_kind=supplier`: REF z faktury tłumaczony wyłącznie przez `SupplierMaterialMap`; bez mapy =
  „do przypisania”; ML auto tylko z historii zatwierdzeń.

## Zadania

1. `extractor.py`: `ROLE_ALIASES`; `apply_column_map` przyjmuje rolę → nagłówek **lub lista aliasów**
   (wygrywa najlepiej pasujący); `parse_column_map` ujednolica nazwy ról; słowa `szt`, `kwota`
   z `_auto_detect_column_roles` compare dopisane do reguł auto-detekcji.
2. Nowy `invoices/profiles.py`: `DocProfile`, `normalize_role_map`, `resolve(supplier)`,
   `keyword_hits`, `detect_supplier(db, text, company_id)` (port `compare.supplier_profiles.detect_supplier`,
   granice słów przez lookaround zamiast `\b`, remis = None).
3. `splitter.py`: `marker_in` (znacznik z profilu, spacje/wielkość liter, tolerancja literówek OCR
   ≥ 0,85 na oknie słów); `split_pdf(path, pl_marker="", texts=None)` — znacznik profilu = strona PL.
4. `pipeline.process_job(db, job, profile, …)`: CI wg `profile.ci_map`, PL (wagi) wg `pl_map`,
   `build_items(..., ref_kind=)`.
5. `matching.match/suggest/build_items`: parametr `ref_kind`.
6. `routers/invoices.py`: tekst stron czytany raz (rozpoznanie dostawcy + cięcie), profil
   z `profiles.resolve`, także przy ponowieniu dokumentu.
7. `schemas/supplier_profiles.py` i `scripts/import_compare_db.py`: te same aliasy ról.
8. Testy `tests/test_invoices_profile.py` (syntetyczne PDF/teksty): aktywny > column_map,
   draft → column_map, kolejność resolve, znacznik dzieli CI/PL (+ literówka OCR), słowa
   kluczowe (jednoznaczne / remis / brak / inna spółka / draft), upload bez dostawcy kontenera,
   `ref_kind=supplier`.

## Poza zakresem (następne etapy)

- Etap 3: ostrzeżenie „słowa kluczowe ≠ dostawca kontenera”, jednostki, wagi netto z PL,
  kontrole z tolerancjami, pasek „Profil · CI str. … · PL str. …” przy dokumencie.
- Etap 4: kreator/karta dostawcy (próbki, test). Etap 5: eksport „Kartoteka symboli”.

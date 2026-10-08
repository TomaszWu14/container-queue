# Profil dostawcy (CI + packing list) i eksport do agencji celnej — design

Data: 2026-09-24 · Status: do przeglądu · Autor: brainstorming z użytkownikiem

## Cel

Aplikacja ma **niezawodnie czytać faktury handlowe (CI) i packing listy (PL) każdego dostawcy**,
kontrolować je i wysyłać agencji celnej (Delta Brokers) dane w formacie, który agencja importuje do
swojego systemu. Profil dostawcy budujemy z ~10 przykładowych faktur na dostawcę.

## Zakres

W zakresie:
- profil dokumentów dostawcy: słowa kluczowe, waluta, język, mapowanie kolumn CI i PL, reguła
  podziału PDF na CI/PL, tolerancje, próbki z testem;
- przepływ dokumentu niezależny od źródła (przy kontenerze, wsad; SharePoint później);
- kontrole: suma pozycji ↔ suma faktury, ilości CI ↔ PL per REF, ilości CI ↔ pozycje zamówienia SAP;
- przeliczenie ilości na jednostkę podstawową i jednostkę uzupełniającą (np. pary);
- eksport „Kartoteka symboli” (wzór Delta Brokers, 44 kolumny) + format eksportu per agencja.

Poza zakresem (osobne etapy): PI (proforma), PO, SAD i porównania z nimi; łącznik SharePoint
(czeka na dostęp IT i układ folderów); wiele układów faktury na jednego dostawcę; plik faktury
z pozycjami w formacie agencji (czeka na wzór od agencji — patrz „Sprawy otwarte").

## Model danych (jedna migracja)

`supplier_doc_profiles` (1 na dostawcę, per spółka dostawcy):
- `supplier_id` (FK, unikalny), `currency`, `doc_language`, `status` (`draft` | `active`);
- `keywords` — lista słów do rozpoznania dostawcy w tekście PDF;
- `ci_map`, `pl_map` — rola kolumny → lista aliasów nagłówka (JSON). Role CI: `ref_ours`,
  `supplier_code`, `desc`, `qty`, `unit`, `price`, `amount`, `weight_net`, `weight_gross`,
  `cartons`, `no`; PL: `ref_ours` | `supplier_code`, `qty`, `unit`, `cartons`, `weight_net`,
  `weight_gross`;
- `split_rule` — jak rozpoznać strony PL (domyślnie istniejący klasyfikator treści; opcjonalnie
  słowo-znacznik np. „PACKING LIST");
- `tol_amount_pct` (domyślnie 0,5), `tol_qty_pct` (domyślnie 0).

`supplier_doc_samples`: `profile_id`, plik PDF (uploads), `created_at`, `last_test` (JSON: pozycje
CI/PL, suma wyliczona vs suma faktury, CI↔PL, błędy), `last_test_at`.

Master data materiału (`Material`) — nowe pola: `suppl_unit` (np. „pary"), `suppl_factor`
(przelicznik jednostki podstawowej → uzupełniającej).

Agencja celna (`CustomsAgency`) — nowe pola: `export_format` (`standard` | `symbols`),
`export_params` (JSON, np. `{"IDZestawu": 106}`).

Migracja danych: istniejące `Supplier.column_map` → `ci_map` profilu (status `draft`); stare pole
czytane zapasowo do czasu usunięcia w kolejnym PR.

## Przepływ dokumentu

1. **Rozpoznanie dostawcy.** Przy kontenerze: dostawca kontenera, słowa kluczowe tylko kontrolują
   (ostrzeżenie przy rozbieżności). Wsad (i później SharePoint): dopasowanie słów kluczowych
   aktywnych profili; przy niejednoznaczności lub braku — operator wybiera dostawcę.
2. **Podział PDF** na części CI i PL wg `split_rule` (bez profilu: obecny klasyfikator).
   Oznaczenie w dokumencie: „CI: str. 1–2 · PL: str. 3".
3. **Ekstrakcja** tabel CI i PL wg `ci_map`/`pl_map` (bez profilu: obecna auto-detekcja).
4. **Symbol = nasz REF.** Kolumna `ref_ours` wprost albo `supplier_code` → `SupplierMaterialMap`
   (kod dostawcy → REF). Brak mapowania = pozycja „do przypisania" (jak dziś).
5. **Jednostki.** Ilość z faktury przeliczana na jednostkę podstawową materiału przelicznikami
   z master data (`UomConversion`, MARM `UMREZ/UMREN`), np. 155 kart. → 15 500 szt. Cena =
   kwota / ilość w jednostce podstawowej. Jednostka uzupełniająca z `Material.suppl_unit/factor`.
6. **Waga netto per REF.** Z PL (waga netto pozycji); zapasowo z master data (MARM).
7. **Kontrole** (✓ / ⚠ z różnicą): suma pozycji vs suma na fakturze (`tol_amount_pct`);
   ilość CI vs PL per REF (`tol_qty_pct`); ilość CI vs pozycje zamówienia SAP (import REF/EKKO) per
   REF (`tol_qty_pct`); REF bez wagi / CN / nazwy PL.
8. Dalej istniejąca ścieżka: dopasowanie, zatwierdzenie pozycji, eksport, szkic maila (.eml).

## Ekrany

**Karta dostawcy** (Master data → Dostawcy → Profil): kraj · kod · nazwa · waluta · status;
plakietki pokrycia (CI n pól ✓, PL n pól ✓, CI↔PL, CI↔Zamówienie SAP); chipy słów kluczowych
i aliasów; tolerancje; wynik testu „10/10 próbek OK".

**Kreator (4 kroki):**
1. *Dane dostawcy* — wybór istniejącego dostawcy, waluta, język, słowa kluczowe (chipy, Enter).
2. *Próbki* — do 10 PDF; aplikacja proponuje słowa kluczowe (tekst wspólny próbek), podział CI/PL
   per plik i aliasy nagłówków.
3. *Mapowanie CI i PL* — zakładki; tabela z wybranej próbki, klik w nagłówek → rola kolumny;
   wymagane role oznaczone; przełącznik próbek.
4. *Tolerancje i test* — tolerancje; „Testuj na wszystkich próbkach" (wynik per plik);
   „Aktywuj profil" gdy wszystkie przechodzą albo po jawnym potwierdzeniu.

**Dokument w kontenerze:** pasek „Profil: <dostawca> · CI str. … · PL str. …" i wyniki kontroli,
np. „REF 145851: CI 15 500 szt, PL 15 300 szt (−1,3%)".

## Eksport do agencji

Format wg `CustomsAgency.export_format`:
- `standard` — obecny Excel pozycji (bez zmian);
- `symbols` — **Kartoteka symboli** (wzór `SymboleAcme_EXCEL.xlsx`): jeden wiersz na unikalny REF
  z zatwierdzonych pozycji kontenera, 44 kolumny w kolejności wzoru (Symbol … SaWazneInfWIT).
  Mapowanie: `Symbol` = REF; `KodPCN` = CN 8 cyfr; `KodTaric` = cyfry 9–10 kodu celnego, brak →
  `00`; `NazwaPolska` = nazwa PL; `NazwaObca` = opis z faktury (zapasowo nazwa EN);
  `KodKrajuPoch` = `KodKrajuPrefPoch` = kraj dostawcy; `Waga` = waga netto na jednostkę podstawową;
  `NazwaJednMiar` = jednostka podstawowa; `NazwaJednMiarUzup`/`PrzelicznikDoUzupJM` = jednostka
  uzupełniająca; `Niepochodzacy`/`Militarny`/`PokazUwagi` = `N`; `IDZestawu` = `export_params`
  (domyślnie 106); `OstatniModyfikujacy` = login eksportującego; `DataOstModyfikacji` = data
  eksportu (komórka daty). Pozostałe kolumny puste. Tekst zapisany przez `exports.append_row`
  (ochrona przed formułami).
- Braki (CN, nazwa PL, waga) nie blokują: przed wygenerowaniem lista braków per REF + potwierdzenie.
- Szkic maila (.eml) do agencji dołącza plik w formacie agencji + PDF-y faktur.

## Błędy

- PDF bez tekstu → komunikat + OCR (istniejący); wynik OCR przechodzi te same kontrole.
- Nierozpoznany dostawca → wybór ręczny. Tabela niezgodna z mapowaniem → status „do sprawdzenia",
  dane zachowane. Profil `draft` nie jest używany automatycznie we wsadzie.

## Testy

- ekstrakcja z mapowaniem CI/PL na przykładowych PDF (2–3 próbki w repo, zanonimizowane);
- podział stron CI/PL; rozpoznanie dostawcy (jednoznaczne, niejednoznaczne, brak);
- przeliczenie jednostek (kartony → szt., jednostka uzupełniająca) i cena za jednostkę podstawową;
- kontrole i tolerancje (w granicy, na granicy, poza);
- eksport symboli: 44 kolumny w kolejności wzoru, TARIC z kodu celnego / `00`, stałe `N`,
  IDZestawu z ustawień agencji;
- aktywacja profilu uruchamia test na próbkach.

## Kolejność wdrożenia (osobne PR)

1. Model + migracja (profil, próbki, pola materiału i agencji) + przeniesienie `column_map`.
2. Ekstrakcja wg profilu + podział CI/PL + rozpoznanie dostawcy.
3. Jednostki, wagi netto, kontrole i tolerancje (+ widok przy dokumencie).
4. Kreator profilu + karta dostawcy + test na próbkach.
5. Eksport „Kartoteka symboli" + format per agencja w mailu.

## Sprawy otwarte

- Znaczenie `IDZestawu` (106) — potwierdzić z Delta Brokers (konfigurowalne, bez zmian w kodzie).
- Który numer z faktury Pulp House jest Symbolem (Job Number 145851 vs Reference 71787/A) —
  ustawiane w profilu dostawcy; do potwierdzenia z agencją.
- Wzór pliku **faktury z pozycjami** w formacie agencji (XML/Excel) — poprosić Delta Brokers.
- Próbki: ~10 faktur na dostawcę od użytkownika.

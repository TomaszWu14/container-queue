# Kartoteka dostawców — profil, indeksy, zamówienia, dokumenty (design)

Data: 2026-09-25 · Status: zatwierdzony w brainstormingu (6 części) · Następny krok: plan wdrożenia.
Zastępuje zakres „etap 4/5” z `2026-09-24-profil-dostawcy-ci-pl-agencja-design.md` w części UI profilu;
ekstrakcja (etap 2, #617) i kontrole (etap 3, #625) zostają i są podpięte pod warianty.

## 1. Kontekst i decyzje

- **Podmioty w aplikacji:** Acme = właściciel dostawców i materiałów; Iberia = spółka zależna,
  kontenery z materiałami Acme; DLT = magazyn zewnętrzny (podwykonawca, nie kupuje); Borealis,
  Cobalt Sport = klienci, dla których prowadzimy przepływ kontenerów (bez materiałów).
- **Jedna globalna kartoteka dostawców** (dostawcy Acme). Nadawcy kontenerów klientów (Borealis,
  Cobalt Sport) zostają tekstem na kontenerze (`supplier_raw`), bez kartoteki.
- **SAP = jedyne źródło** danych dostawcy i indeksów dostawcy. Dostawców nie zakłada się ręcznie —
  przychodzą z Excela SE16N (LFA1, EINA). Aplikacja tylko wzbogaca rekord o dane, których SAP nie ma.
- **Kod SAP (LIFNR) obowiązkowy i unikalny.**
- Masowe wgrywanie historycznych dokumentów służy **tylko nauce formatu** (warianty układu);
  nie tworzy faktur ani powiązań z kontenerami.
- Bez zdjęć fabryk/produktów. Zamiast tego monogram, mapa i kontakty.
- Wybrane podejście: **przebudowa istniejącej tabeli `suppliers`** na globalną + migracja scalająca duble.

## 2. Model danych

### Własność pól

| Dane | Źródło | Edycja w aplikacji |
|---|---|---|
| kod SAP, nazwa, kraj, ulica, miasto, kod pocztowy, VAT, status/blokada (LFA1) | SAP | nie (kłódka „zmień w SAP”) |
| indeks dostawcy: dostawca+materiał, kod dostawcy, status, kraj pochodzenia, CN (EINA) | SAP | nie |
| czas realizacji per indeks dostawcy (dni) | aplikacja | tak |
| kontakty, pinezka mapy (korekta), port wysyłki, notatka | aplikacja | tak |
| profil dokumentów + warianty układu | aplikacja | tak |

### Tabele

- **`suppliers`** (przebudowa): usunięte `company_id` i `column_map`; `sap_code` UNIQUE NOT NULL;
  nowe: `street`, `city`, `zip`, `vat`, `sap_status` (active|blocked|inactive_in_sap), `lat`, `lng`,
  `geo_source` (geocode|manual|none), `shipping_port_id` FK ports (null), `note`. `address` zostaje jako
  sklejka do wyświetlenia.
- **`supplier_contacts`** (rozbudowa): `full_name`, `role` (sales|logistics|quality|other), `email`,
  `phone`, `messenger` (np. „WeChat: xxx”), `is_primary`; UNIQUE(`supplier_id`, lower(`email`)) gdy email niepusty.
- **`supplier_materials`** (nowa): `supplier_id`, `material_id`, `supplier_code`, `sap_status`,
  `origin_country`, `tariff_cn`, `lead_days` (aplikacja, null); UNIQUE(`supplier_id`,`material_id`);
  INDEX(`supplier_id`,`supplier_code`). Zastępuje `SupplierMaterialMap` (per spółka, ręczna) — migracja
  przenosi wpisy ze znacznikiem `unconfirmed=true` do czasu importu EINA.
- **`supplier_doc_profiles`** (jest): zostaje waluta, język, słowa kluczowe, tolerancje, `ref_kind`;
  mapy `ci_map`/`pl_map` przechodzą do wariantów.
- **`supplier_doc_variants`** (nowa): `profile_id`, `doc_type` (ci|pl), `fingerprint` (JSON: znormalizowane
  nagłówki kolumn + słowa nagłówka dokumentu), `column_map`, `status` (proposed|approved|rejected),
  `docs_count`, `ok_count`, `ref_hit_pct`, `approved_by`, `approved_at`.
- **`supplier_doc_samples`** (rozbudowa): `sha256` UNIQUE per dostawca, `doc_type`, `variant_id` (null),
  `pages`, `result` (JSON), `status` (queued|ok|review|rejected|duplicate), `reason`.
- **Import SAP:** tabela `sap_imports` (kto, kiedy, plik, rodzaj, liczniki, raport błędów).
- **Audyt:** każda zmiana pola (także z importu, `user` = „import SAP <plik>”) w istniejącym `audit`.

### Widoczność

Dostawcy widoczni dla ról/spółek pracujących na materiałach Acme (admin, logistyka, zakupy Acme
i Iberia). Borealis, Cobalt Sport, DLT, magazyn, spedytor, agencja — brak dostępu do kartoteki.
Reguła w `deps.py` (jedno miejsce, jak `scope_*`), nie w routerach.

## 3. Import z SAP (Master data → Importy, tylko admin)

1. **Dostawcy (LFA1)**, 2. **Indeksy dostawców (EINA; status/pochodzenie/CN z EINA/EINE/MARC — ustalić
   przy pierwszym prawdziwym pliku)**, 3. Materiały (bez zmian).
- Rozpoznanie kolumn po polskich nagłówkach SE16N (jak `_map_headers`). Brak kolumny obowiązkowej →
  komunikat „brak kolumny: …”, zero zmian.
- **Podgląd (dry-run)** w 4 zakładkach z licznikami: Nowi · Zmienieni (pole po polu stara→nowa) ·
  Zniknęli z SAP (→ `inactive_in_sap`, nigdy kasowani) · Błędy (wiersze pomijane).
- „Zatwierdź” = jedna transakcja. Podsumowanie + wpis w `sap_imports` + raport błędów xlsx.
- Klucz: `sap_code` (indeksy: `sap_code`+materiał). Import idempotentny; nie dotyka danych aplikacji.
- Kod SAP powtórzony w pliku = błąd wiersza.

### Migracja startowa (osobny PR, najpierw na kopii bazy)

Obecne rekordy per spółka → dopasowanie do pierwszego pliku LFA1 po `sap_code`, potem po znormalizowanej
nazwie. Scalenie przez istniejące `dictionaries_merge` (przepina kontenery, zamówienia, paczki faktur,
profile, próbki). Niedopasowani → ekran „Do rozstrzygnięcia”: scal z dostawcą SAP / nieaktywny /
usuń (tylko bez powiązań). Na prod: kopia bazy przed migracją, lista scaleń do przejrzenia.
Znikają: `column_map` (po przeniesieniu do wariantu), panel „Wyczyść słownik dostawców”.

## 4. Profil dostawcy (układ B: wizytówka po lewej)

**Lista** (Master data → Dostawcy): szukanie po nazwie / kodzie SAP / kodzie dostawcy; kolumny nazwa,
SAP, kraj, indeksy, kontenery 12 m, profil dok., status SAP; filtry: aktywni, nieaktywni, bez profilu
dok., bez kontaktów. Zamiast „+ Nowy” — „Import z SAP”.

**Wizytówka (sticky, lewa kolumna):** monogram (inicjały, kolor z hasha nazwy), nazwa, SAP, status;
znacznik „SAP” przy polach z SAP; mapa z pinezką (klik → pełny ekran; admin może przesunąć pinezkę —
zapis `geo_source=manual`); adres, kraj z flagą, port wysyłki, **bieżąca godzina u dostawcy** (strefa z
kraju/miasta); **kontakty** (rola, mailto, tel, „kopiuj ID” komunikatora, + Dodaj, edycja w miejscu).

**Zakładki (prawa kolumna):**
1. **Przegląd:** kafelki — indeksy, kontenery 12 m, % na czas, średni transit, **zamówienia w realizacji
   + najbliższa wysyłka**; ostatnie kontenery; stan profilu dokumentów.
2. **Indeksy:** tabela z SAP (nasz indeks, nazwa PL, kod dostawcy, status, pochodzenie, CN, czas
   realizacji — edytowalny); plakietka „N dostawców” przy indeksie wielodostawczym; eksport xlsx.
3. **Zamówienia:** nr, data zamówienia, planowana wysyłka, data dostawy, ilość łącznie (jm podstawowa),
   w kontenerach, pozostało, kontenery (linki); rozwinięcie = pozycje; po terminie czerwone, ≤7 dni
   bursztynowe; filtry w realizacji / zrealizowane / wszystkie; eksport xlsx.
   **„W realizacji”** = dopóki cała zamówiona ilość nie jest w kontenerach o statusie DOSTARCZONY lub
   ZREALIZOWANY; pasek postępu „% w drodze · % dostarczone”.
4. **Dokumenty:** profil dokumentów, warianty, wgrywanie (sekcja 6).
5. **Kontenery:** kontenery dostawcy z filtrem okresu.
6. **Historia:** audyt (kto/import, pole, stara→nowa).

**Mapa:** geokodowanie raz przy imporcie (OpenStreetMap Nominatim, z limitem 1 req/s i cache w bazie);
render Leaflet. Bez internetu na serwerze → `geo_source=none`, admin wstawia pinezkę ręcznie; tło mapy z
kafelków w repo (`frontend/public/globe/tiles`).

**Wygląd:** design system aplikacji (tokeny, IBM Plex, lucide), stonowane plakietki, jedyny akcent —
kolor monogramu. Tryb ciemny i kontrast ≥4.5:1 (test tokenów).

## 5. Indeksy dostawcy

- Karta materiału (Master data → Materiały) dostaje sekcję „Dostawcy tego indeksu” (dostawca, kod
  dostawcy, status, pochodzenie, CN).
- Ekstrakcja faktur tłumaczy kod dostawcy → nasz indeks przez `supplier_materials` w obrębie dostawcy
  kontenera lub rozpoznanego z dokumentu (ten sam kod u dwóch dostawców nie myli indeksów).
- Kod spoza SAP → pozycja „kod nieznany w SAP” (bez auto-dopisywania); lista takich kodów na profilu.
- Jakość danych: indeks bez dostawcy; dostawca bez indeksów; ten sam kod dostawcy → dwa indeksy u
  jednego dostawcy; podobna nazwa przy różnym kodzie SAP („możliwy dubel w SAP” — scalanie w SAP).

## 6. Dokumenty dostawcy — masowe wgrywanie i warianty układu

- Zakładka Dokumenty (admin, logistyka): przeciągnięcie dziesiątek/setek PDF (≤25 MB/plik) → kolejka
  zadań w tle (istniejący mechanizm jobów), postęp „143/380”, można zamknąć stronę.
- Deduplikacja po `sha256` (status `duplicate`).
- Podział stron: faktura / packing lista / proforma / inne (istniejący splitter + OCR).
- **Grupowanie po odcisku układu** (`fingerprint`) → warianty „Faktura · układ 1 · 212 dok.”.
- Dla wariantu: auto-propozycja mapy kolumn (istniejące `identify_columns`) + test na **wszystkich**
  dokumentach grupy („206/212, REF 97%”).
- Zatwierdzanie: podgląd dokumentu | odczytana tabela; role kolumn (kreator z #623 rozszerzony o
  warianty); „Zatwierdź wariant” / „Scal z układem N” / „Odrzuć”.
- „Do sprawdzenia”: podgląd + powód (brak tabeli, nieczytelny skan, kod spoza SAP); ręczne przypisanie
  do wariantu lub odrzucenie.
- Nowa faktura: dostawca → wariant po odcisku → mapa wariantu → kontrole z etapu 3; przy dokumencie
  pasek „Profil X · Faktura układ 2 · CI str. 1–2 · PL str. 3”.
- Pliki historyczne nie tworzą faktur ani powiązań z kontenerami.

## 7. Duble, edycja, usuwanie, uprawnienia

- Unikalności w bazie: `suppliers.sap_code`; (`supplier_id`,`material_id`); (`supplier_id`,`sha256`);
  (`supplier_id`, lower(email)) kontaktu.
- Pola z SAP nieedytowalne (kłódka). Dane aplikacji — edycja w miejscu, potwierdzenie przy usuwaniu.
- Dostawca z powiązaniami — tylko nieaktywny; bez powiązań — admin może usunąć (lista skutków +
  wpisanie kodu SAP).

| Rola | Uprawnienia |
|---|---|
| admin | wszystko (import SAP, usuwanie, zatwierdzanie wariantów) |
| logistyka | podgląd, kontakty, pinezka, notatki, czas realizacji, wgrywanie dokumentów |
| zakupy | podgląd + kontakty |
| magazyn / spedytor / agencja / Borealis / Cobalt Sport | brak dostępu do kartoteki |

## 8. Testy

- Backend: import (nowy, zmieniony, zniknięty, błąd, ponowny bez zmian, powtórzony kod); migracja
  scalająca na kopii danych; unikalności; uprawnienia per rola i widoczność spółek; odcisk układu i
  grupowanie (syntetyczne PDF w 2 układach); rozpoznanie wariantu przy nowej fakturze; „zamówienie w
  realizacji” (częściowo w drodze / dostarczone); geokodowanie z mockiem i bez internetu.
- Frontend: profil (wizytówka, zakładki, kłódki), podgląd importu, zatwierdzanie wariantu, kontakty
  (dodaj/edytuj/usuń), tabela zamówień (kolory terminów).
- Wizualnie: profil 1920 / 1366 / tryb ciemny.

## 9. Kolejność wdrożenia (1 PR = 1 temat)

1. Model danych + migracja scalająca (+ ekran „Do rozstrzygnięcia”).
2. Import dostawców i indeksów z SAP z podglądem.
3. Profil: wizytówka + zakładki Przegląd, Indeksy, Zamówienia, Kontenery, Historia.
4. Kontakty + mapa (geokodowanie, pinezka ręczna).
5. Masowe dokumenty + warianty układu (+ podpięcie ekstrakcji i kontroli).
6. Jakość danych (duble, braki).

## 10. Poza zakresem

Ceny i waluty per indeks (zostają w SAP); zdjęcia fabryk/produktów; archiwum i statystyki z
historycznych dokumentów; kartoteka nadawców klientów (Borealis, Cobalt Sport); edycja danych SAP w
aplikacji.

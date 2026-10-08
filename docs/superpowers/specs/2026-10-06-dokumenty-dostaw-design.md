# Dokumenty dostaw — jedno wejście, poczekalnia, bramki (2026-10-06)

Źródła: brainstorming z userem (30 decyzji, poniżej), audyt procesu
(37 luk, w większości naprawione PR #990–#1002) i przegląd kodu „dołączanie plików do dostaw” (50 błędów, §4).

**Kolejność (decyzja 20):** najpierw naprawy z §4 małymi PR-ami, potem nowy proces z §2–§3.

## 1. Decyzje usera

| # | Temat | Decyzja |
|---|---|---|
| 1 | Wejście | **Jedno „Dodaj dokumenty”** (plik / wiele / folder / ZIP / mail) wszędzie tak samo; pozostałe przyciski wgrywania znikają |
| 2 | Typ | Automat rozpoznaje, **podsumowanie stron z typami + „Potwierdź”** (zmiana typu możliwa); przypisanie dopiero po potwierdzeniu |
| 3 | Inny kontener | **Blokada + „Przenieś do X”** jednym klikiem |
| 4 | Ten sam plik w innym kontenerze | **Wpuść z informacją** „jest też w X”; dubel w tym samym kontenerze = blokada |
| 5 | Po wysłaniu do agencji / po odprawie | **Tylko „Podmień” z powodem**; wcześniej usuń/podmień swobodnie |
| 6 | Poprzednia wersja | **Archiwum wersji** (zastąpiona / usunięta) |
| 7 | Pliki partnerów | **Wpadają od razu, oznaczone** „od spedytora/agencji” + powiadomienie logistyki; ta sama bramka |
| 8 | .eml / .msg | **Rozpakować jak ZIP**; mail zostaje jako „korespondencja” |
| 9 | Braki przy zmianie statusu (ZWOLNIONY/ODPRAWIONY/DOSTARCZONY) | **Ostrzeżenie z powodem** w historii |
| 10 | Powiadomienia | **Zbiorczo na porcję**; osobno tylko ważne (odrzucenie bramką, podmiana po wysłaniu, plik od partnera) |
| 11 | Podejście | **A: poczekalnia na serwerze** (nic nie trafia do dostawy przed „Potwierdź”) |
| 12 | Niepotwierdzone | **Czekają bez limitu**; pasek „N dokumentów czeka na potwierdzenie” |
| 13 | Kilka kontenerów w jednym wgraniu | **Rozdziel po numerach** z treści; „Potwierdź” zapisuje do właściwych kontenerów naraz |
| 14 | Dokument bez numeru kontenera | **Dopasuj po PO / numerze faktury**; brak trafienia = bieżący kontener, plakietka „niepewny” |
| 15 | Rozpoznawane typy | Handlowe **PI, CI, PL, PO**; transportowe **BL, CMR, awizo**; celne **SAD draft/PZ/PW, świadectwo pochodzenia** (FORM A, EUR.1); jakość **CoA, certyfikaty, QC** |
| 16 | Wymagane dokumenty | **Konfigurowalne per dostawca** (domyślny zestaw jak dziś) |
| 17 | Certyfikaty jakości | **Jeden dokument „Certyfikaty jakości”** na zestaw |
| 18 | Puste strony | **Dołączane do poprzedniego dokumentu**, w podsumowaniu „pusta” |
| 19 | Zdjęcia JPG/HEIC | **Konwersja do PDF + OCR** (bramka i rozpoznanie jak dla skanu) |
| 20 | Nazwy | **Schemat `KONTENER_TYP_numer.pdf`**, oryginalna nazwa w szczegółach i historii |
| 21 | Archiwum | widzi/pobiera **logistyka i admin** |
| 22 | Podmiana po wysłaniu | **szkic .eml „Korekta dokumentu…” + powiadomienie** kont agencji |
| 23 | Przeniesienie między kontenerami | **każdy, kto wgrywa, z powodem**; po wysłaniu tylko logistyka/admin |
| 24 | Dokument zbiorczy | **Jeden plik powiązany z kilkoma kontenerami** („wspólny z X”; podmiana działa wszędzie) |
| 25 | Widoczność | **agencja: wszystkie dokumenty swoich kontenerów; magazyn: tylko PL, CMR, BL, awizo** (bez cen/faktur/SAD) |
| 26 | Odbiorcy (klienci) | **nie mają kont, podglądów ani dostępu** → dokumenty nigdy nie są udostępniane odbiorcom: usunąć flagę „dla klienta” i pobieranie plików w portalu (los publicznego linku śledzenia — do potwierdzenia) |
| 27 | Poczta (n8n) | **wszystkie dokumenty do poczekalni**, dopasowanie po numerze kontenera/PO |
| 28 | Kolejka | **mini-kafelki PI·CI·PL·BL·SAD w wierszu + filtry „braki” i „czeka w poczekalni”** |
| 29 | Bramka „inny kontener” | 5 pierwszych stron, **przy konflikcie cały dokument** zanim odmowa |
| 30 | Kolejność | **najpierw 50 błędów (§4), potem poczekalnia** |

Wcześniej (2026-10-06): usuwa każdy, kto może wgrywać — doprecyzowane przez 5, 21, 23.

## 2. Architektura docelowa (podejście A)

```
„Dodaj dokumenty” (plik / wiele / folder / ZIP / .eml / .msg / JPG)
        │  POST /api/intake  (kontener kontekstu)
        ▼
  Rozpakowanie (ZIP, mail) → konwersja (JPG→PDF) → cięcie stron (splitter)
        → typ strony (markery + ML, bez vision) → kontener docelowy (nr kontenera / PO / faktura)
        → bramki: czytelność, dubel (sha256), inny kontener (5 stron → całość), puste strony
        ▼
  POCZEKALNIA: intake_items (część, typ, kontener docelowy, status bramki, ostrzeżenia)
        │  okno „Sprawdź i potwierdź” (zmiana typu / kontenera, odrzuć część)
        ▼  POST /api/intake/{id}/confirm
  Zapis: CI/PI/PL → paczka faktur (OCR/ekstrakcja w tle) · reszta → dokumenty z typem (kafelki)
        → wspólny after_documents_added: statusy, audyt, JEDNO zbiorcze powiadomienie
```

- **Poczekalnia** — tabele `intake_batches` (kto, kiedy, źródło: ręcznie/poczta) i `intake_items`
  (plik części, sha256, typ, kontener docelowy, wynik bramki, decyzja). Bez limitu czasu (12).
- **sha256** na `attachments` i `invoice_jobs` (źródło) + unikalność per kontener — koniec porównań
  bajt-po-bajcie i wyścigów (§4 pkt 14–17, 40).
- **Wersje** — `attachments.replaced_by_id`, `deleted_at`, `delete_reason`; lista pokazuje aktualne,
  archiwum dla logistyki/admina (6, 21). Podmiana atomowa po stronie serwera (`replaces_id`).
- **Wspólny plik** dla kilku kontenerów — tabela łącząca `attachment_containers` (24).
- **Wymagane dokumenty per dostawca** — rozszerzenie profilu dostawcy (16); kafelki i ostrzeżenie
  przy zmianie statusu (9) czytają z jednego miejsca.

## 3. Ekrany

- **Jedno „Dodaj dokumenty”** na karcie kontenera i w szufladzie (+ przeciągnij i upuść); kafelki
  pokazują stan i otwierają plik, nie wgrywają.
- **Okno „Sprawdź i potwierdź”**: tabela części — miniatura strony, zakres stron, typ ▾, kontener ▾,
  wynik bramki (✓ / dubel / inny kontener → „Przenieś do X” / niepewny), „Odrzuć”; przycisk Potwierdź.
- **Pasek** „N dokumentów czeka na potwierdzenie” na karcie, w szufladzie i filtr w kolejce (28).
- **Historia pliku**: wersje, kto, kiedy, powód; pobranie starej wersji (logistyka/admin).

## 4. Błędy do naprawy najpierw (przegląd kodu 2026-10-06, origin/main @ 0e26db46)

### Wysoka
1. Agencja (customs) może usunąć KAŻDY załącznik kontenera (zawężenie tylko dla spedytora) — `forwarding_files.py:195`.
2. Usunięcie po wysyłce do agencji (WYSLANE/.eml) bez blokady i bez powiadomienia — `forwarding_files.py:189-213`.
3. „Podmień” = upload + DELETE z frontu; gdy DELETE padnie (409/403) zostają oba pliki — `AttachmentActions.tsx:27-31`.
4. Magazyn widzi na kafelkach numery faktur CI/PI, nazwy plików i stan draftów SAD — `document_tiles.py:73-97`.
5. ZIP z hasłem / deflate64 / złym CRC → 500 (wyjątki przy odczycie poza try) — `archive_upload.py:33-37,63-64`.
6. Obejście bramki PDF przez ZIP dla ról bez faktur (spedytor, agencja) — `archive_upload.py:93-94,107-112`.
7. Usunięcie paczki faktur kasuje kaskadą drafty SAD i potwierdzenie agencji — `routers/invoices.py:220-235`.

### Średnia
8. `document_status` / `customs_status` nie cofają się po usunięciu dokumentu (ZALACZONE, SAD-PZ/PW).
9. Efekty uboczne (BRAK→ZALACZONE, automat SAD, powiadomienia) tylko w zwykłym uploadzie — nie w ZIP, propozycjach, draftach SAD.
10. Brak wpisu w audycie przy wgraniu (jest tylko przy usunięciu).
11. Propozycje OCR wskazują własny kontener paczki → dubel faktury — `suggestions.py:42-55`.
12. Akceptacja propozycji bez kontroli dubla — `documents.py:264-275`.
13. Usunięcie pliku z przyjętej propozycji zostawia ją „accepted” bez pliku (nie da się przyjąć ponownie).
14. Dubel między kanałami: załącznik vs paczka faktur sprawdzane osobno.
15. Dubel w jednym żądaniu (dwa identyczne PDF w uploadzie faktur / w ZIP).
16. Upload faktur kończy się 409 na pierwszym dublu — folder zamówienia przerywa resztę.
17. Duble po przeniesieniu/kopii faktury niewykrywane (`source_name=""`) — `relocate.py:45,69`.
18. Przeniesienie faktury bez sprawdzenia, czy cel już ją ma, i w trakcie przetwarzania.
19. Ręczny draft SAD bez walidacji PDF i zgodności kontenera (inbox to sprawdza) — `sad_drafts.py:41-45`.
20. Draft SAD z poczty bez powiadomienia logistyki.
21. Inbox SAD dobiera paczkę po samym numerze kontenera (dwie spółki) — do potwierdzenia.
22. Zwykły upload z typem SAD_DRAFT omija obieg wersji draftu.
23. Mail do agencji zabiera wszystkie BL z kafelka (stary i nowy); pomija CI/PL wgrane jako zwykłe pliki.
24. Szkic .eml nie zostawia śladu wysłanych plików (id) ani statusu WYSŁANE.
25. Flaga „dla klienta” możliwa na fakturach, Excelu, SAD (ceny) — **wg decyzji 26: flaga do usunięcia**.
26. Podmiana gubi `client_visible` i nie pokazuje ostrzeżenia bramki.
27. Wiele plików naraz dostaje jeden wybrany typ (np. wszystkie jako CMR).
28. Upload przez kafelek przerywa się na pierwszym błędzie i ignoruje ostrzeżenie bramki.
29. Panel plików nie odświeża statusów kontenera i kafelków po wgraniu/usunięciu.
30. CONFLICT bez obejścia, gdy nasz numer jest dalej niż na 5. stronie — **wg decyzji 29: czytać całość**.
31. Faktury frachtowe bez kontroli dubli (plik / numer faktury + BL).

### Niska
32–36. Zapis/kasowanie plików poza transakcją (propozycje, faktury frachtowe, usunięcie paczki, ponowny eksport Excela, kopia faktury) → sieroty / wiersze bez pliku.
37. Brak sprzątacza osieroconych plików w uploads.
38. Faktura frachtowa przyjmuje .zip (wspólna allowlista).
39. Content-Type od klienta trafia do .eml — zgadywać z rozszerzenia.
40. Wyścig dubli przy równoległym uploadzie (brak ograniczenia w bazie) — sha256 + unique.
41. Podwójne `get_container_checked` w uploadzie.
42. Powiadomienie z ZIP-a do magazynu o plikach, których nie widzi.
43. ZIP po cichu pomija pliki `.`/`~$` (nie w `skipped`).
44. Jeden zły PDF (za długi/nieczytelny) odrzuca cały ZIP.
45. Kafelek BL liczy też pominięty dokument z paczki.
46. Spedytor widzi stan kafelka BL bez plików.
47. Akcje Podmień/Usuń widoczne bez uprawnień (backend 403/409) — `can_delete` w API.
48. Rola sales widzi „Wgraj”, a błąd listy jest połykany.
49. Przyciski wgrywania nieosiągalne z klawiatury (`label` + ukryty input).
50. Automat SAD-PZ/PW pomijany bez komunikatu dla spedytora/zakupów.

## 5. Plan PR-ów

**Faza 1 — naprawy (§4), jeden temat na PR:**
1. Uprawnienia usuwania: agencja tylko własne, blokada po wysłaniu (tylko Podmień z powodem), `can_delete` w API — 1, 2, 47
2. Podmiana atomowa po stronie serwera (`replaces_id`, przeniesienie typu) + archiwum wersji — 3, 26 (decyzje 5, 6, 21)
3. Widoczność: magazyn tylko PL/CMR/BL/awizo, kafelki BL — 4, 45, 46 (decyzja 25)
4. ZIP: odporność, bramka PDF dla wszystkich ról, duble w archiwum, `skipped` dla wszystkiego — 5, 6, 15, 42, 43, 44
5. Wspólny `after_documents_added` / `after_document_removed`: statusy w obie strony, audyt, zbiorcze powiadomienia — 8, 9, 10, 50 (decyzja 10)
6. sha256 + unikalność + duble między kanałami, pomijanie per plik — 14, 15, 16, 17, 40 (decyzja 4)
7. Propozycje OCR — 11, 12, 13, 32
8. Przenieś/kopiuj faktury — 18, 36
9. Drafty SAD — 7, 19, 20, 21, 22
10. Mail do agencji: najnowszy BL, CI/PL spoza paczki, ślad wysłanych plików — 23, 24, 39
11. Odbiorcy bez dostępu: usunięcie flagi „dla klienta” i plików w portalu — 25 (decyzja 26)
12. Atomowość plików + sprzątacz sierot — 33, 34, 35, 37
13. Faktury frachtowe — 31, 38
14. FE: typ per plik przy wielu plikach, kafelki przez wspólny upload, odświeżanie — 27, 28, 29
15. FE: dostępność i role — 48, 49
16. Bramka: cały dokument przy konflikcie — 30, 41 (decyzja 29)

**Faza 2 — nowy proces (§2–§3):** poczekalnia (tabele + intake + okno Potwierdź) → jedno wejście
w UI (zniknięcie starych przycisków) → .eml/.msg i JPG → rozdział na kilka kontenerów i dopasowanie
po PO → wspólny plik dla kilku kontenerów → wymagane dokumenty per dostawca + ostrzeżenie przy
zmianie statusu → mini-kafelki i filtry w kolejce → poczta (n8n) do poczekalni.

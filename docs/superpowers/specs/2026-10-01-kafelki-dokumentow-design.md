# Kafelki dokumentów dostawy (design)

Data: 2026-10-01 · Status: zatwierdzony w pytaniach (10+1) · Wzór: compare `templates/dostawa_detail.html:721-890`, `delivery_workflow.py`

## Cel
Na kontenerze od razu widać, które dokumenty są, których brakuje i w jakim są stanie — jak panel
„Dokumenty” w compare. Bez wgrywania czegokolwiek drugi raz.

## Kafelki
`PI` · `CI ⇄ PL` · `BL` · `SAD-DRAFT → SAD-PZ → SAD-PW` (bez PO i artworków).
- SAD-PZ = SAD po odprawie (przyjęte zgłoszenie, PZC); SAD-PW = zwolnienie towaru.

## Źródła (wszystkie trzy)
| Kafelek | Skąd |
|---|---|
| PI / CI / PL | paczki faktur (`InvoiceJob.doc_kind` proforma / invoice / packing_list, bez `ignored`) **lub** załącznik z typem o kodzie PI / CI / PL |
| BL / SAD-PZ / SAD-PW | załącznik (`Attachment`) z typem dokumentu o kodzie BL / SAD_PZ / SAD_PW |
| SAD-DRAFT | `SadDraft` paczek faktur kontenera (najnowsza wersja) **lub** załącznik z kodem SAD_DRAFT |

Powiązanie typu z kafelkiem: **stały kod** `DocumentType.tile_code` (PI, CI, PL, BL, SAD_DRAFT,
SAD_PZ, SAD_PW). Migracja tworzy brakujące typy BL / SAD-PZ / SAD-PW i nadaje kod istniejącemu
„Draft SAD”; admin może przypiąć kod do istniejącego typu (np. „Konosament”). Zmiana nazwy
niczego nie psuje.

## Stan (kolor kropki)
- szary — brak;
- niebieski — jest;
- zielony — sprawdzony: CI/PI zatwierdzona i zgodna z kontenerem (bramka 2026-10-01),
  SAD-DRAFT zaakceptowany;
- żółty — niepewny / czeka: faktura niepewna lub niezatwierdzona, draft do oceny;
- czerwony — sprzeczny (bramka) / draft SAD do poprawy.

## Wymagane — zależnie od etapu kontenera
Pusty kafelek przed swoim etapem jest szary, ale nie trafia do „brakuje: …”.
- PI — od W_PRODUKCJI;
- CI, PL, BL — od W_TRANSPORCIE (przed odprawą);
- SAD-DRAFT — od wysłania faktur do agencji (status odprawy ≥ DRAFT_WYSLANY);
- SAD-PZ — od statusu odprawy ODPRAWIONY; SAD-PW — od ZWOLNIONY.
Tylko kontenery w obiegu celnym (jak dzisiejsze braki dokumentów) mają wymagane SAD-*.

## Interakcja
- Klik w kafelek z plikiem → podgląd (najnowszy plik); bez pliku → wgranie z ustawionym typem
  (CI / PI / PL → paczka faktur, reszta → załącznik z typem). Upuszczenie pliku na kafelek tak samo.
- „Zarządzaj” → lista wszystkich plików tego kafelka.

## Miejsca
- Karta kontenera — góra zakładki Dokumenty (pełne kafelki, nagłówek „N/M · brakuje: …”).
- Szuflada kolejki — kompakt: małe kolorowe kwadraciki ze skrótem (CI, PI, PL, BL, SD, PZ, PW).

## Role
Jak dziś załączniki: widzi, kto widzi dokumenty kontenera; wgrywa, kto dziś wgrywa załącznik /
paczkę faktur (agencja celna — SAD na swoich kontenerach).

## Automat
- Wgranie SAD-PZ → status odprawy **ODPRAWIONY** (jeśli niższy).
- Wgranie SAD-PW → nowy status odprawy **ZWOLNIONY** (między ODPRAWIONY a ROZLICZONY).
- Bez cofania przy usunięciu pliku; wpis w historii kontenera.

## Plan PR-ów
1. Status odprawy ZWOLNIONY (enum + migracja + listy/filtry/tłumaczenia).
2. `DocumentType.tile_code` + migracja typów + `GET /api/containers/{id}/document-tiles`.
3. Kafelki na karcie kontenera (podgląd, wgranie, upuszczenie, zarządzaj).
4. Kompakt w szufladzie kolejki.
5. Automat SAD-PZ → ODPRAWIONY, SAD-PW → ZWOLNIONY.

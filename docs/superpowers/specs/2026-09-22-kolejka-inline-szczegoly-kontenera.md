# Spec: rozwijany panel szczegółów kontenera w kolejce

Data: 2026-09-22 · Status: zatwierdzony do implementacji

## Cel
Zamiast wchodzić na osobny ekran karty kontenera (`/kontenery/:id`), użytkownik rozwija
szczegóły **inline na głównym ekranie kolejki** — akordeon pod wierszem kontenera z drogą
kontenera, statusami, dokumentami/zawartością i kontaktem. Trzyma kontekst kolejki, skraca
drogę „kliknij → wróć".

## Decyzje (z wywiadu 10+1)
1. **Inline + link do pełnej karty.** Rozwijany panel jest domyślny; w środku przycisk
   „Otwórz pełną kartę" do głębokiej edycji i rzeczy ciężkich.
2. **Sekcje panelu:** droga kontenera (oś czasu), statusy + historia zmian,
   dokumenty + pozycje/zawartość, kontakt.
3. **Jeden naraz (akordeon).** Rozwinięcie kontenera zamyka poprzedni.
4. **Wiersz na całą szerokość pod kontenerem** (spycha resztę w dół).
5. **Wyzwalacz:** przycisk na wierszu „Szczegóły" → „Rozwiń" (toggle). Zero kolizji z
   zaznaczaniem/drag/menu prawym.
6. **Podgląd + kluczowe akcje:** read-only dane, ale zostają zmiana statusu i zmiana daty
   awizacji (są już na wierszu). Reszta edycji na pełnej karcie.
7. **Kontakt:** mail do spedytora · telefon `tel:` klik-to-call (gdy numer w master data) ·
   wewnętrzny wpis/notatka.
8. **Role:** te same ograniczenia widoczności co `ContainerPage` (np. % wypełnienia i
   pozycje ukryte dla magazynu/agencji).
9. **Dane:** lazy-load po rozwinięciu + cache; „droga" jako lekka oś czasu, ciężka
   mapa/globus tylko na pełnej karcie. Podstawy (status/ETA/kontakt) z danych kolejki od razu.
10. **Trwałość:** ulotne — zmiana filtra/sortu/odświeżenie zwija; mobile = ten sam akordeon.
11. **Stara szuflada „podgląd" (prawa) zastąpiona** — usuwamy `preview` drawer w QueuePage.

## Do doprecyzowania przy implementacji
- „Wewnętrzny wpis/notatka" — sprawdzić, czy istnieje mechanizm komentarzy/notatek na
  kontenerze; jeśli nie, najtaniej podpiąć pod Wiedzę kontekstową (może wymagać drobnego
  backendu). [[knowledge-panel-topbar]]
- Endpointy osi czasu / dokumentów / pozycji / historii — reużyć te z `ContainerPage`.
- Telefony spedytora/dostawcy — sprawdzić, czy są w master data (warunek klik-to-call).

## Uwagi techniczne
- QueuePage ~2100+ linii; renderowanie 4 sekcji inline dla 400+ wierszy → akordeon
  single-open + lazy-load to warunek wydajności.
- Panel jako pełnoszerokościowy wiersz w strukturze kafli (grid `--tile-cols`) — musi
  spanować wszystkie kolumny (grid-column: 1 / -1) i działać w trybach GRUPUJ WG
  (Magazyn/Status) tak samo jak w Tydzień+dzień.
- To osobny, większy plaster — po domknięciu PR #444 (topbar/zaznaczenie/pasek) i #445
  (rowspan tygodnia + GRUPUJ WG).

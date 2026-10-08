# Kolejka (widok tygodniowy) — UI polish: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 19 usprawnień UX widoku kolejki (QueuePage) z przeglądu designu 2026-09-03 — jeden PR, 4 zadania.

**Architecture:** Wyłącznie frontend (`frontend/src`): `QueuePage.tsx`, `QueueSummaryBar.tsx`, `queueRows.ts`, `styles.css`, `i18n.ts`. Zero zmian API. Preferuj CSS nad przebudową komponentów. Każda nowa etykieta w i18n ×3 (pl/en/pt).

**Decyzje (z interview — WIĄŻĄCE):**
1. Badge „OPÓŹN." **inline za datą** (data + odstęp + badge) — koniec nachodzenia na tekst.
2. Przyciski akcji (Rozwiń/Zwiń wszystko, Analiza): **ikony z tooltipem**; przy wąskim ekranie zawijanie.
3. Sekcja „PER MAGAZYN" ukryta, gdy w zakresie jest **<2 magazynów**.
4. Zakładki firm: bez zmian (równorzędne, także z 0).
5. Dni bez dostaw: **cienki, zbity wiersz** (sama data, niska wysokość); ich pełne ukrycie = istniejący toggle.
6. Nagłówki kolumn: **poszerzyć** (min-width mieszczący etykietę + ikonę filtra) — koniec „MAGAZY…".
7. Filtr zakresu dat w nagłówku: **jeden przycisk „📅 od–do"**, dwa pola rozwijane po kliknięciu.
8. „● 67 opóźnione" w pasku sumarycznym: **klikalne**, włącza/wyłącza filtr „Tylko opóźnione", widoczny stan aktywny.
9. Licznik „0/19 rozwiniętych": **usunąć**.
10. „Odblokuj wiersze" → przełącznik stanu „**Edycja: wyłączona/włączona**" z kłódką jako ikoną stanu.
11. Tła dni: przyciszyć; weekend = delikatnie szarszy; kolor zarezerwowany dla statusów.
12. „Wysokość wiersza" przenieść do menu „▦ Kolumny" → wspólne menu „Widok" (kolumny + gęstość).
13. Jeden pasek okresu: `‹ Sierpień 2026 ›` + segmenty Wszystko/Miesiąc/Tydzień/Zakres + „Dziś"/„Od dziś" w jednej linii.
14. Wypełniony filtr kolumnowy: **mini-etykieta nad polem** (lub chip z wartością) — koniec placeholder-as-label.
15. **Pasek aktywnych filtrów** (chipy z ×, „Wyczyść wszystkie"), widoczny tylko gdy coś filtruje.
16. **Sticky**: kolumna NR KONTENERA przy scrollu poziomym; nagłówek kolumn + wiersz dnia przy pionowym.
17. „Eksport Excel" eksportuje **bieżący widok** (filtry+zakres+firma); menu ze strzałką → „cała kolejka".
18. Mobile (wąskie ekrany): dzień jako **lista kart kontenerów** zamiast tabeli z poziomym scrollem.
19. Zaznaczenie wierszy → **pływający pasek akcji masowych** u dołu (licznik + akcje), znika po odznaczeniu.

## Global Constraints
- i18n: każdy nowy tekst w pl/en/pt (`frontend/src/i18n.ts`), Polish-first.
- Stan filtrów pozostaje w query string (linkowalność) — nie przenosić do lokalnego stanu.
- Testy: `npx vitest run` + `npx tsc --noEmit` z `frontend/` (foreground). Istniejące 134 testy muszą przejść.
- Nie zmieniać kontraktu API ani `queueRows.ts` splitByPlanning semantycznie.
- Style przez istniejące klasy/zmienne w `styles.css` — bez nowych bibliotek.

---

### Task 1: Toolbar + nagłówek (decyzje 2, 3, 6, 7, 9, 10, 12, 13)
**Files:** Modify `frontend/src/pages/QueuePage.tsx`, `frontend/src/pages/QueueSummaryBar.tsx`, `frontend/src/styles.css`, `frontend/src/i18n.ts`. Test: rozszerz `frontend/src/queue.week.dom.test.tsx` lub nowy `queue.toolbar.dom.test.tsx`.
Kroki TDD: (a) test — brak licznika „rozwiniętych", obecność przełącznika „Edycja:", menu „Widok" zawiera gęstość, per-magazyn niewidoczny przy 1 magazynie; FAIL → implementacja → PASS → commit `feat(kolejka): porządki toolbara — pasek okresu, menu Widok, edycja jako stan`.

### Task 2: Wiersze i tabela (decyzje 1, 5, 11, 16)
**Files:** Modify `QueuePage.tsx`, `styles.css`, ewent. `queueRows.ts` (tylko flaga „pusty dzień"). Test: przypadki — badge inline w tekście nagłówka dnia (brak absolute), pusty dzień ma klasę `day-empty` (niska wysokość), weekend klasa `day-weekend` (stonowana). Sticky przez CSS (`position: sticky`) dla th/td pierwszej kolumny i nagłówków. Commit `feat(kolejka): czytelne wiersze dni — badge inline, zbite puste dni, sticky nr kontenera`.

### Task 3: Filtry (decyzje 8, 14, 15, 17)
**Files:** Modify `QueuePage.tsx`, `ColumnFilter.tsx` (mini-etykieta przy wypełnieniu), `styles.css`, `i18n.ts`. Test: klik w „opóźnione" ustawia filtr w query string; wypełniony filtr pokazuje etykietę; pasek chipów pojawia się przy aktywnym filtrze i „Wyczyść wszystkie" czyści query string; eksport ma menu z dwiema opcjami (widok/cała kolejka — parametry istniejącego endpointu eksportu). Commit `feat(kolejka): filtry widoczne — chipy, etykiety, klikalne opóźnione, zakres eksportu`.

### Task 4: Mobile + akcje masowe (decyzje 18, 19)
**Files:** Modify `QueuePage.tsx`, `styles.css`, `i18n.ts`. Media query (<768px): dzień renderuje karty (`.cont-card`: nr, dostawca, statusy, data) zamiast siatki kolumn; pasek akcji masowych `position: fixed; bottom` pokazywany gdy `selected.size > 0` (akcje: przenieś datę = istniejący mechanizm pendingMove, eksport zaznaczonych jeśli endpoint wspiera — inaczej tylko przenieś + wyczyść zaznaczenie). Test DOM: pasek widoczny po zaznaczeniu, znika po odznaczeniu. Commit `feat(kolejka): widok kart na mobile + pasek akcji masowych`.

## Poza zakresem
Decyzja 4 (zakładki bez zmian). Backend eksportu „cała kolejka" jeśli wymaga nowego parametru — wtedy zostawić TYLKO eksport widoku i odnotować w raporcie.

# Prompt: audyt UX/UI całej aplikacji

Gotowy prompt do wklejenia w nowej sesji Claude Code na tym repo albo w issue z `@claude`
(`.github/workflows/claude.yml`). Fazy A i B nie zmieniają kodu — kończą się raportem
`docs/AUDYT-UX-<data>.md` do akceptacji. Hipotezy startowe (ścieżki plików) są aktualne na 2026-09-28;
prompt każe je zweryfikować.

---

## 0. Rola i cel
Jesteś starszym projektantem UX/UI i inżynierem frontendu (React + TypeScript + czysty CSS) z doświadczeniem
w aplikacjach operacyjnych (logistyka, kolejki, tabele z dużą liczbą danych). Twoim zadaniem jest
**kompletny audyt UX i UI aplikacji TIMPORYE** (repo `TomaszWu14/container-queue`, frontend `frontend/src`,
backend FastAPI `backend/app`) i przygotowanie **priorytetyzowanego planu poprawek**, a następnie —
dopiero po moim zatwierdzeniu — wdrożenie ich małymi PR-ami. Audyt ma objąć każdy widok, każdą rolę,
oba motywy (jasny i ciemny) i trzy szerokości ekranu. Nie interesują mnie ogólniki („warto poprawić
kontrast") — każde ustalenie musi mieć: widok, rolę, kroki odtworzenia, dowód (zrzut ekranu / pomiar /
fragment kodu z `plik:linia`), przyczynę w kodzie i konkretną propozycję zmiany.

Użytkownicy to pracownicy logistyki, zakupów, magazynu, agencji celnej, spedytorzy i admini. Pracują
wiele godzin dziennie na kolejce kontenerów (`/kolejka`), często na laptopach 1366×768 i monitorach
1920×1080, część na tablecie przy rampie. Liczy się: szybkość skanowania wzrokiem, zero niespodzianek,
pewność „czy moja akcja się zapisała", brak mrugania i skakania treści.

## 1. Zasady projektu (obowiązkowe — przeczytaj przed czymkolwiek)
1. Przeczytaj `CLAUDE.md`, `graphify-out/wiki/index.md`, `UX_AUDIT.md` (historyczny, decyzja D16 — nie
   duplikuj już wdrożonych ustaleń), `docs/audyt-nielsen-kolejka.md`
   (sekcje §1, §3, §4 — numery linii mogą być nieaktualne, zweryfikuj).
2. Limit **500 linii** na plik `.py`/`.ts`/`.tsx`/`.css` (`scripts/check_file_lengths.py`). Dodając kod —
   wydzielaj moduły, nie podnoś progów.
3. Nowe teksty UI **tylko** w `frontend/src/i18n/features/<funkcja>.ts` (`defineFeature({ pl, en, pt })`),
   nigdy na końcu `*.base.ts` / `*.modules.ts`. Każdy klucz musi być użyty (`i18n.unused.test.ts`).
4. Izolacja danych per spółka/zasób jest w `backend/app/deps.py` (`get_scoped`, `scope_containers`) —
   nie duplikuj reguł dostępu w routerach.
5. 1 PR = 1 temat, mały, szybko scalany. Przed pushem `git merge origin/main`, testy, lint.
6. Nie formatuj masowo plików, których nie zmieniasz.

## 2. Tryb pracy (trzy fazy — nie przeskakuj)
**Faza A — rozpoznanie i pomiary (tylko odczyt).** Uruchom aplikację lokalnie (backend + frontend, seed
danych testowych z wieloma kontenerami w różnych statusach, co najmniej 2 spółkami, dostawcami,
awizacjami, reklamacjami). Użyj Playwright (Chromium jest preinstalowany, `executablePath:
'/opt/pw-browsers/chromium'` w chmurze; lokalnie `npx playwright` z `frontend/`, izolowany backend :8010 + vite :5181 — nie ruszaj instancji użytkownika) do przejścia każdego widoku jako każda rola: `admin`, `logistics`,
`purchasing`, `warehouse`, `customs`, viewer bez prawa edycji, oraz strony publiczne z tokenem
(`/avizo/:token`, `/dostawa/:token`, `/dlt/:token`, `/k/:token`, `/portal/:token`). Dla każdego widoku:
zrzut ekranu w motywie jasnym i ciemnym, szerokości 1366, 1920 i 390 px, stan pusty, stan z dużą
ilością danych (≥300 kontenerów), stan błędu (zablokuj API w Playwright), stan wolnej sieci
(throttling „Slow 3G"). Nagraj trace/wideo przewijania kolejki.

**Faza B — raport.** Zapisz `docs/AUDYT-UX-<data>.md` w formacie z sekcji 6. Nie wprowadzaj zmian w kodzie.
Zatrzymaj się i poproś o akceptację listy P0/P1.

**Faza C — poprawki.** Po akceptacji: seria małych PR-ów, każdy z testem (Vitest DOM / Playwright /
pytest) i zrzutem „przed/po" w opisie PR.

## 3. Obszary audytu — checklisty (przejdź KAŻDY punkt w KAŻDYM widoku)

### 3.1 Mruganie i niestabilność wizualna
- Czy treść znika/przygasa przy odświeżaniu danych? Sprawdź wzorzec `setLoading(true)` przy każdym
  `load()` i klasę `.reloading` (`opacity: .55; pointer-events: none`) — potwierdzone: `pages/QueuePage.tsx`
  l.349 (`<div className={loading ? 'reloading' : undefined}>`), CSS `styles/02-queue-toolbar-rows.css` ok. l.76–77. Cała lista przygasa po każdym
  zapisie/przeniesieniu/wyczyszczeniu. Oczekiwane: dane w tle („stale-while-revalidate"), wskaźnik
  postępu nieinwazyjny (cienki pasek u góry), bez blokowania kliknięć poza edytowanym elementem.
- Nieskończone animacje: `.tile.wh-none` z `wh-none-pulse` 2.4 s infinite (`02-…css` l.131) — kolejka jest już tabelą (`kq-*`), więc sprawdź, czy selektory `.tile*` nie są martwym CSS;
  zmierz, ile kafli pulsuje jednocześnie; oceń czy to nie jest źródło „mrugania". Uwzględnij
  `prefers-reduced-motion` (czy jest respektowane globalnie?).
- Inne animacje: `.tile.flash`, `deepTargetPulse`, `skeleton-shimmer`, `toast-in` — czy nie odpalają się
  przy każdym re-renderze.
- Polling: `NotificationsBell.tsx` (60 s), `GatePage.tsx` (60 s), `ChangesFeedPage.tsx` (60 s),
  `TrackingPage.tsx` (5 min), `ContainerTimeline.tsx` (60 s), `admin/MonitorPanel.tsx`, `clock.tsx` (1 s).
  Czy odświeżenie wywołuje remount, skok przewinięcia, utratę fokusu, zamknięcie otwartego menu,
  wyczyszczenie wpisywanego tekstu? Czy polling działa w ukrytej karcie (`document.hidden`)?
- Layout shift (CLS): obrazki/ikony bez wymiarów, fonty, wiersze zmieniające wysokość po dociągnięciu
  danych, banery wstawiane nad treścią. Zmierz CLS w Playwright (PerformanceObserver `layout-shift`).
- Klucze list: czy elementy nie remountują się przez zmienne `key` (indeks tablicy przy sortowaniu).

### 3.2 Przewijanie i przyklejone nagłówki
- **Stan wyjścia (2026-09-28):** kolejka to tabela Enterprise (`pages/queue/EnterpriseTable.tsx`,
  `EnterpriseGroup.tsx`, style `styles/11-kolejka-enterprise.css` … `14-kolejka-odchudzenie.css`); dawne kafle
  i `useStickyLayout.ts` usunięto. Przewijanie jest WEWNĄTRZ `.kq-scroll`: sticky nagłówek kolumn (26 px),
  sticky pasek dnia z sumami `.kq-ghead` (28 px, `top: 26px`), przyklejone kolumny zaznaczenia/numeru (`left`).
  Poprawka dodała `scroll-snap` (przyciąganie do pełnego wiersza, `scroll-padding-top: 54px`), mocniejsze tła
  magazynów i siatkę komórek — zweryfikuj na nagraniu, czy „nachodzenie sum na wiersze” i „skakanie” zniknęły,
  a nie zgłaszaj ich ponownie bez nowego dowodu.
- Sprawdź: odklejanie paska dnia na końcu grupy (sticky w obrębie `<tbody>`), zachowanie przy zmianie gęstości
  (`.dense`), przy zawijaniu paska narzędzi i chipów filtrów, przy otwartej szufladzie (`12-kolejka-szuflada.css`),
  z-indexy (nagłówek 3–4, pasek dnia 2, kolumny 1) vs dropdowny, modale, toasty, menu kontekstowe.
- Topbar globalny (`06-sidebar-nav.css`, `--topbar-h`) + pasek kolejki nad tabelą — czy razem nie zjadają
  wysokości na 1366×768.
- `overflow: clip` na szynach — czy nie ucina tooltipów/menu.
- Czy po akcji (zapis, zmiana filtra, powrót z karty kontenera) pozycja przewinięcia jest zachowana?
  Czy „Wstecz" przeglądarki przywraca listę w tym samym miejscu?
- Tabele w innych widokach (pulpit `05-status-pages.css` `th { sticky }`, kalendarz, analityka, master
  data) — spójność zachowania nagłówków.
- Brak wirtualizacji — zmierz czas renderu i przewijania przy 300/1000 kontenerach; zaproponuj próg,
  od którego wirtualizacja jest konieczna.
- Mobile/tablet: przewijanie w dwóch osiach, przyklejone elementy zjadające ekran przy 390 px.

### 3.3 Kolory, kontrast, motywy
- Zmierz kontrast (WCAG 2.2 AA: 4.5:1 tekst, 3:1 duży tekst i elementy interfejsu, obramowania pól,
  ikony-przyciski, focus ring) dla każdej pary tekst/tło w obu motywach. Użyj axe-core w Playwright +
  ręczny pomiar kolorów obliczonych (`getComputedStyle`).
- Tokeny są w `styles/01-tokens-base.css`, ale kolory statusów to twarde pary hex w
  `05-status-pages.css` (`.badge.st-*`, `.badge.cs-*`) **bez wariantów dark mode** — zweryfikuj i
  zaproponuj tokeny `--st-*`/`--cs-*` dla obu motywów. Zinwentaryzuj wszystkie twarde hexy w CSS i TSX
  (w tym Tailwind one-off w `DashboardPage`).
- Motywy spółek (`.mod-acme`, `.mod-dlt`, `.mod-cobalt`) nadpisują tylko akcent — sprawdź kontrast
  każdego akcentu na każdym tle i na przyciskach.
- Kolor jako jedyny nośnik informacji (tła magazynów `--wh-*`, statusy) — czy jest też tekst/ikona?
  Sprawdź symulację daltonizmu (deuteranopia, protanopia).
- Spójność semantyki: ten sam kolor = to samo znaczenie w całej aplikacji (np. czerwony tylko dla
  błędu/opóźnienia, nie dla „specjalny").

### 3.4 Kliknięcia i interakcje
- Każdy element klikalny: czy wygląda na klikalny, ma kursor, stan hover/active/focus/disabled, cel
  ≥44×44 px na dotyku (24×24 minimum WCAG 2.5.8). Wypisz elementy klikalne bez wizualnej afordancji
  i elementy wyglądające na klikalne, które nic nie robią.
- Podwójne kliknięcie i ponowienie: czy przyciski blokują się na czas żądania; czy akcje typu
  „przełącz" nie odwracają się przy podwójnym kliknięciu (patrz 3.6).
- Liczba kliknięć do najczęstszych zadań (zmierz i zaproponuj skrócenie): zmiana statusu kontenera,
  zmiana daty awizacji, dodanie dokumentu, dodanie do obserwowanych, znalezienie kontenera po numerze,
  przejście z powiadomienia do kontenera i z powrotem.
- Menu kontekstowe wiersza (`pages/queue/TileMenus.tsx`) vs przyciski w wierszu (`EnterpriseGroup.tsx`, `cells.tsx`) —
  czy te same akcje są dostępne w obu miejscach i czy uprawnienia są spójne.
- Skróty klawiaturowe i Esc (`useEscClose` w `components.tsx`) — czy każdy modal/panel/menu zamyka Esc,
  czy fokus wraca do elementu wywołującego, czy działa Tab/Shift+Tab w pułapce fokusu.
- Przeciąganie (drag & drop w kolejce, `useQueueMove.ts`) — czytelność celu upuszczenia, anulowanie,
  cofnięcie.

### 3.5 Informacja zwrotna i powiadomienia („chmurki")
- System toastów istnieje (`frontend/src/feedback.tsx`: `showToast(msg, 'success'|'error', action?)`,
  portal `.toast-stack`, `aria-live`). Zinwentaryzuj **każdą akcję zapisującą** w aplikacji i sprawdź,
  czy daje: toast sukcesu, toast błędu z treścią z API, opcję „Cofnij" tam, gdzie akcja jest
  odwracalna. Szukaj `.catch(() => {})` i pustych catch — każdy to cichy błąd do naprawy.
- Dzwonek (`NotificationsBell.tsx`) odpytuje licznik co 60 s, lista ładuje się dopiero po otwarciu,
  **nowe powiadomienie nie pokazuje żadnej chmurki**. Zaprojektuj: toast/„chmurka" przy wzroście
  licznika (z tytułem powiadomienia i linkiem do kontenera), limit (max 3 naraz, grupowanie),
  wyciszenie, respektowanie trybu „tylko obserwowane", brak chmurek dla akcji wykonanych przez
  samego użytkownika. Oceń, czy wystarczy polling, czy warto SSE.
- Stany ładowania/puste/błędu w każdym widoku: `Skeleton`, `LoadError` z przyciskiem „Spróbuj
  ponownie", sensowny tekst stanu pustego z podpowiedzią co zrobić.
- Wskaźnik świeżości danych (np. tracking: „dane z 14:32").
- Fałszywy sukces: np. „Sync" w `TrackingPage` raportuje sukces mimo błędu —
  znajdź wszystkie podobne przypadki.

### 3.6 Obserwowane kontenery — pełny przegląd i projekt docelowy
Stan obecny (zweryfikuj): tabela `watched_containers` (`backend/app/models/tracking.py`) ma tylko
`user_id` + `container_id`, bez powodu, źródła i daty. `POST /api/containers/{id}/watch`
(`backend/app/routers/containers_changes.py`) **przełącza** stan (podwójny klik = cofnięcie), `GET
/api/watch` zwraca gołą listę id. Frontend: stan w `pages/queue/useViewPrefs.ts` (ładowany raz na
mount, nie współdzielony między widokami), gwiazdka ☆/★ jako ikona w wierszu tabeli (`EnterpriseGroup.tsx` ~l.175, `kq-flag-btn star`); UWAGA: istnieją już `watchPrompt`/`confirmWatch`/`cancelWatch` w `useViewPrefs.ts` (pytanie o powód?) i `pages/watch/WatchersPanel.tsx` na karcie kontenera — zweryfikuj, co z opisu poniżej jest nadal prawdą,
widoczna tylko gdy `canEdit && !archive` (viewer i archiwum jej nie widzą, choć backend pozwala),
menu kafla (`TileMenus.tsx`) bez tego ograniczenia; brak gwiazdki na karcie kontenera `/kontenery/:id`
i w trackingu; lista obserwowanych to tylko filtr „★ Moje" w `QueueFilterBar.tsx`; brak toastu,
brak blokady, błędy połykane. Obserwowanie **nie dodaje** powiadomień — tylko zawęża przy włączonym
`watch_only_notifications` (`backend/app/notifications.py`); dla zakupów daje jedynie poniedziałkowy
digest. Istnieje też osobny, globalny „specjalny" (🚩, z `special_reason`) oraz role-based
`company_watchers` — trzy nakładające się pojęcia, dodatkowo `VesselCard.tsx` używa klasy `watch-star`
dla 🚩, a filtr „Specjalne" filtruje `customer_order`.

Oceń i zaprojektuj docelowo:
1. Model: `reason` (lista predefiniowana + „inne"), `note` (tekst), `source` (ręcznie / automatycznie —
   z jakiej reguły), `created_at`, `created_by` — migracja Alembic.
2. API idempotentne: `PUT /watch` (dodaj/aktualizuj powód), `DELETE /watch`; `GET /watch` zwraca
   obiekty z powodem i datą.
3. UI: przycisk z etykietą (nie sama ikona) na kaflu, karcie kontenera, w wynikach wyszukiwania;
   przy dodaniu mały popover „Dlaczego obserwujesz?" (opcjonalny, 1 klik żeby pominąć); tooltip i
   znacznik na kaflu pokazujący powód; osobny widok/zakładka „Obserwowane" z kolumnami: kontener,
   powód, od kiedy, ostatnie zdarzenie, akcje.
4. Toast „Dodano do obserwowanych — Cofnij", optymistyczna aktualizacja z wycofaniem przy błędzie,
   blokada na czas żądania, stan współdzielony w całej aplikacji (kontekst / cache zapytań).
5. Powiadomienia: jasno opisz w UI, co daje obserwowanie (np. „dostaniesz powiadomienia o zmianach
   ETA, statusu, dokumentów tego kontenera"), i zdecyduj, czy obserwowanie ma **dodawać** odbiorcę.
6. Rozdziel nazewniczo i wizualnie: „Obserwuję" (moje, prywatne) vs „Specjalna troska" (globalne, z
   powodem) — spójne ikony, klasy CSS i etykiety.

### 3.7 Nawigacja, zakładki, architektura informacji
- Zinwentaryzuj wszystkie trasy (`App.tsx`, przekierowania i uprawnienia w `routing.tsx`) i pozycje menu
  (`Sidebar.tsx`) per rola. Szukaj: widoków niedostępnych z menu, pozycji prowadzących do 403,
  zakładek, których nazwa nie mówi co zawierają, zakładek-duplikatów (ta sama treść w dwóch miejscach),
  zbyt głębokiego zagnieżdżenia.
- Czy aktywna zakładka/filtr jest w URL (odświeżenie i link zachowują stan)? Czy „Wstecz" działa
  przewidywalnie?
- Spójność nazw: ta sama rzecz ma jedną nazwę wszędzie (menu, nagłówek, breadcrumb, i18n).
- Brakujące wejścia: np. brak przycisku „Dodaj kontener"/„Import" w kolejce mimo istniejących modali
  (AUDYT §3) — znajdź wszystkie „martwe" funkcje.

### 3.8 Duble (UI i kod)
- Ten sam przycisk/akcja w kilku miejscach z różnym zachowaniem lub uprawnieniami.
- Zdublowane komponenty i logika: eksport CSV (4 kopie), mapy locale, `pl-PL` na sztywno, ręcznie
  pisane modale zamiast `Modal` z `components.tsx`, duplikaty formatowania dat/liczb, dwa sposoby
  pokazywania statusu. Zaproponuj wspólne helpery.
- Zdublowane dane na ekranie (ta sama wartość pokazana 2–3 razy w jednym widoku).
- Nieużywane klucze i18n i martwy CSS (selektory bez użycia).

### 3.9 Ukryte wartości i utracone informacje
- Tekst ucinany `text-overflow: ellipsis` bez tooltipa / bez możliwości podglądu pełnej wartości.
- Kolumny/pola ukryte na mniejszych szerokościach bez alternatywy.
- Wartości w `title=` dostępne tylko myszką (niedostępne na dotyku i dla czytnika).
- Pola pokazujące surowe enumy (`W_TRANSPORCIE`), `null`/`undefined`/`NaN`/`Invalid Date`, puste
  komórki bez „—".
- Dane obecne w API, ale niepokazywane nigdzie w UI (porównaj schematy odpowiedzi z renderowanymi
  polami) — oceń, które są przydatne.
- Filtry, które ukrywają elementy bez wyraźnego sygnału („pokazano 40 z 312, aktywne filtry: …").
- Zaznaczenie przetrwające zmianę filtra (AUDYT §1) — akcje masowe na niewidocznych elementach.

### 3.10 Formularze i format danych
- Przecinek dziesiętny (polski) akceptowany wszędzie (znany błąd w `quotes/forms.tsx`), daty w formacie
  lokalnym, strefa czasowa, walidacja inline z komunikatem przy polu, zachowanie wpisanych danych po
  błędzie, autofokus, Enter = zapisz, ostrzeżenie przy opuszczaniu niezapisanego formularza.

### 3.11 Dostępność
- axe-core na każdym widoku (0 błędów krytycznych i poważnych), `role="dialog"`/`aria-modal` w `Modal`,
  etykiety pól, nazwy przycisków-ikon (`aria-label`), kolejność fokusu, widoczny focus ring,
  obsługa tylko klawiaturą całej kolejki, powiększenie 200% bez utraty funkcji.

### 3.12 i18n
- Przełącz PL/EN/PT w każdym widoku: brakujące tłumaczenia, teksty na sztywno w JSX, ucinanie dłuższych
  tekstów (PT/EN), formaty dat/liczb, święta (`holidays.ts` ma tylko PL — kolejka PT).

### 3.13 Błędy logiczne i wyścigi
- Wyścigi odpowiedzi przy szybkiej zmianie filtra (`ContainerPage`, `ChangesFeedPage`, `ComplaintsPage`)
  — sprawdź wzorzec `loadSeq` i zastosuj wszędzie. Brak debounce w wyszukiwaniach (`AuthLogTab`).
- „Zaznacz wszystko" ignorujące filtry ★/🚩. Każdy błąd odtwórz testem, zanim go naprawisz.
- Błędy konsoli przeglądarki (React warnings, 4xx/5xx) w każdym widoku — zbierz w Playwright.

### 3.14 Wydajność odczuwalna
- Czas do interakcji każdego widoku, rozmiar paczek JS, re-rendery (React Profiler) przy wpisywaniu w
  filtr i przewijaniu, koszt renderu tabeli (brak wirtualizacji) i przewijania `.kq-scroll` ze scroll-snap.

## 4. Ważność
- **P0** — utrata/ukrycie danych, fałszywy sukces, akcja nie działa, blokada pracy, błąd bezpieczeństwa.
- **P1** — codzienny ból: mruganie, skaczące nagłówki, brak informacji zwrotnej, kontrast < AA w
  kluczowych miejscach, obserwowane.
- **P2** — spójność, duble, estetyka, drobne a11y.
- **P3** — pomysły i usprawnienia.

## 5. Zasady proponowanych zmian
- Najpierw wspólne mechanizmy (tokeny kolorów, hook do ładowania w tle, jeden helper toastów dla akcji,
  wspólny stan obserwowanych), potem poprawki per widok.
- Każda zmiana z testem regresji; dla bugów: najpierw test czerwony, potem poprawka.
- Nie zmieniaj reguł dostępu poza `deps.py`. Nie przekraczaj 500 linii na plik.

## 6. Format raportu `docs/AUDYT-UX-<data>.md`
1. Podsumowanie (maks. 15 linii): top 10 problemów i szacunek pracy.
2. Tabela ustaleń: `ID | Obszar (3.x) | Widok/trasa | Rola | Motyw/szerokość | Kroki | Oczekiwane |
   Faktyczne | Dowód (zrzut/pomiar) | Przyczyna plik:linia | Ważność | Propozycja | Koszt (S/M/L)`.
3. Mapa widoków × ról z oceną 1–5 dla: czytelność, stabilność, feedback, kontrast, nawigacja.
4. Wyniki pomiarów: axe, kontrasty (tabela par kolorów), CLS, FPS przewijania, czasy ładowania.
5. Projekt „Obserwowane" (3.6) — makiety tekstowe/ASCII, zmiany API i migracja.
6. Plan PR-ów w kolejności wdrażania (tytuł, zakres, pliki, test, zależności).
7. Lista rzeczy sprawdzonych i OK (żeby nie wracać do nich).

## 7. Definition of done
- Każdy punkt checklist 3.1–3.14 ma status: problem (z ID) / OK / nie dotyczy — w każdym widoku.
- Każde ustalenie P0/P1 ma dowód i wskazaną przyczynę w kodzie.
- Raport zatwierdzony przeze mnie przed jakąkolwiek zmianą kodu.
- Po wdrożeniu: 0 błędów axe krytycznych/poważnych, kontrast ≥ AA w obu motywach, brak przygasania
  listy przy zapisie, stabilne nagłówki przy przewijaniu (brak skoków w nagraniu), toast przy każdej
  akcji zapisującej, chmurka przy nowym powiadomieniu, obserwowane z powodem widocznym na kaflu i
  karcie kontenera, wszystkie testy i CI zielone.

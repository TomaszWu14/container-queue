# Audyt UX — TIMPORYE (10 heurystyk Nielsena)

> ## ⚠️ STATUS (re-audyt 2026-09-06) — ten raport jest w większości HISTORYCZNY
>
> **Dokument zamrożony (decyzja D16, 2026-09-24):** zostaje jako dziennik historyczny i nie
> jest już aktualizowany. Bieżące ustalenia są w `docs/` (audyty z datą) i w pamięci projektu.
>
> Ponowna weryfikacja kodu na `main` pokazała, że **większość znalezisk systemowych z tego
> raportu została już wdrożona**. Poniższa treść opisuje stan **sprzed** tych napraw —
> traktuj ją jako dziennik, nie listę TODO.
>
> **Zweryfikowane jako ZROBIONE:**
> - #1 daty ISO → `dd.mm.rrrr` (`dates.ts formatDate/formatDateTime`; ostatnie call-site'y,
>   m.in. podgląd ImportModal, domknięte)
> - #2 separator dziesiętny → przecinek (`dates.ts formatNum`, Intl `pl-PL`; FoundOrderModal)
> - #3 Modale zamykają się Esc (`Modal` + `useEscClose`); formularze admina owinięte w `<form>`
> - #4 ciche `.catch` słowników → toast: `useDicts`, `ComplaintsPanel` (już na main)
> - #5 role po angielsku → `roleName_*` w `UsersTab`
> - #6 podwójny submit w adminie → `disabled={busy}` (Companies/Warehouses/Problems/Users…)
> - #7 gołe loadery → `Skeleton`/`LoadError` (AnalysisTab, ForecastTab)
>
> **Realnie POZOSTAŁE (drobne):**
> - `ComplaintDetailPage:88` — nadal gołe `<p>{t('loading')}</p>` zamiast `Skeleton`
> - Ciche `.catch(()=>{})` na tłach list (collaboration, część zakładek admina, App counts) —
>   **świadomie zostawione**: to tła/liczniki, pusta lista nie myli tak jak w słownikach formularza
> - #8 twarde kolory poza tokenami (DashboardPage) — kosmetyczne, nieblokujące
>
> Pełny obraz stanu prac: pamięć `ux-audit-rollout`.

**Aplikacja:** TIMPORYE — moduł kolejki kontenerów.
**Stack:** FastAPI (backend) + React/TypeScript (frontend, Vite).
**Użytkownik / urządzenie:** desktop — dyspozytor / planista / spedytor (biuro). Wyjątki mobilne/tabletowe: `WarehouseQueuePage` i moduł reklamacji (tablet + aparat na hali), `AvizoFormPage` i `DriverPage` (publiczny telefon spedytora/kierowcy) — tam ważą [1][5][7][9].
**Metoda:** statyczna analiza kodu (read-only), 5 równoległych przejść (kolejka+kalendarz / kontener+spedycja+wyceny+celna / zamówienia+tracking+reklamacje+analityka / auth+admin+mobile publiczne / warstwy wspólne + backend). Bez zmian kodu.
**Stan:** po pierwszej rundzie napraw (audyt poprzedni — TOP 1-10 + tap-targety + tooltipy) wdrożonej na `main`. Ten raport ocenia **bieżący** stan i wskazuje **pozostałe** znaleziska.

Numery heurystyk: [1] widoczność stanu, [2] język użytkownika, [3] kontrola/cofanie, [4] spójność, [5] zapobieganie błędom, [6] rozpoznawanie>pamiętanie, [7] elastyczność/klawiatura, [8] estetyka/minimalizm, [9] komunikaty błędów, [10] pomoc.

---

## Tabela zbiorcza

| Widok / warstwa | Krytyczne | Ważne | Drobne | Ogólnie |
|---|---|---|---|---|
| **Warstwy wspólne** (dates/num/Modal/useDicts) | — | 4 ([2/4] daty ISO, [4] przecinek, [3/7] Modal bez Esc, [1/9] useDicts cichy catch) | 2 | fundament dobry, systemowe drobiazgi |
| QueuePage (+SummaryBar) | — | 3 ([1] „Śledź teraz"/eksport bez busy, [2/4] daty ISO, [9] ciche catch słowników) | 4 | wzorcowe filtry/anti-race |
| CalendarPage | — | 1 ([4] locale miesiąca) | 1 | OK po naprawach loaderów |
| ImportModal / FoundOrderModal / QueueEmailModal | — | 2 ([3/7] brak Esc/Enter, [9] cichy catch) | 3 ([2] „OK"/„REF"/ISO) | dry-run wzorcowy |
| ContainerPage (+collaboration, items) | — | 3 ([2/4] historia snake_case+ISO, [4] daty/liczby, [7] inputMode tel) | 2 | anti-race trackingu wzorcowy |
| ForwardingPage / CustomsPage | — | 2 ([1] status celny bez busy, [4] daty ISO) | 2 | confirm cofania OK |
| QuotesPage (+RequestModal) | — | 3 ([7] formularze bez `<form>`, [1] `act` bez busy, [2] `r.kind`/SCFI) | 2 | modal requestu wzorcowy |
| OrdersPage / TrackingPage | — | 1 ([4] daty ISO inline) | 2 ([4] legendy hover-only) | tracking a11y wzorcowy |
| DashboardPage | — | 1 ([4] Tailwind hexy = lokalny wariant DS) | 1 | statusy tłumaczone OK |
| ComplaintsPanel / ComplaintDetailPage | — | 2 ([9] redirect-on-error, [9] ciche catch — tablet!) | 1 | idempotentny submit wzorcowy |
| WarehouseQueuePage | — | — | 2 ([7] cel dotyk, sort dat) | Skeleton/LoadError OK |
| PalletCallsPage | — | 2 ([9] import PAZ bez raportu odrzuconych, [4] liczby/daty) | 1 ([5] PazSection add bez busy) | statusy `pcStatus_` OK |
| AnalitykaPage / AnalysisTab / ForecastTab | — | 3 ([1] gołe `<p>loading>`, [9] błąd bez retry, [4] heatmapa bez legendy) | 2 | import Analityki wzorcowy |
| LoginPage / AuthPages | — | — | 3 ([1] fałszywy „System online", [2] EN „Container Flow"/placeholder) | rozróżnienie 401/5xx wzorcowe |
| AvizoFormPage / DriverPage (publiczne mobile) | — | 2 ([8] 10-kol. tabela na telefonie, [2] daty ISO) | 1 ([3] brak cofnięcia driver) | 404/410 vs 5xx wzorcowe |
| AdminPage (Users/Named/Settings/słowniki) | — | 3 ([2] role EN, [5] ~9 add bez busy, [5] reminder_days bez walidacji) | 3 ([2] „✓ Zapisz", [3] merge bez confirm) | scoping serwerowy OK |

---

## Znaleziska systemowe (przekrojowe — grupowane)

1. **[2]/[4] Daty w formacie ISO `rrrr-mm-dd` zamiast `dd.mm.rrrr`** — `dates.ts:11 formatDateTime` zwraca ISO; użyte w ~18 miejscach + wiele pól renderuje surowe ISO bezpośrednio (QueuePage ETA/ETD/ATD, ContainerPage:244-246, ForwardingPage:334-335, CustomsPage:233, QuotesPage:258,327, OrdersPage:127-128, DashboardPage:76-77, TrackingPage:117,231, PalletCallsPage:187,237, ComplaintDetailPage, AvizoFormPage:178, DriverPage:65, QueueEmailModal:33). Build-stamp w `App.tsx:213` JEST w dd.mm.rrrr → niespójność wewnętrzna. **Root-cause: jeden helper `formatDate()`/`formatDateTime()`.**
2. **[4] Separator dziesiętny — kropka zamiast przecinka** — `toFixed()` w `ContainerItems.tsx:72-74` (wagi netto/brutto/objętość), `PalletCallsPage.tsx:31` (`num`, palety `5.0`), `QuotesPage.tsx:18` (`money`), oraz `toLocaleString()` bez jawnego locale (QuotesPage:129,192,683; FoundOrderModal:254; UsersTab:212; PalletCallsPage:187) — separator zależny od przeglądarki. **Root-cause: wspólny `formatNum` z `localeFor(lang)`.**
3. **[3]/[7] Modale bez Esc i formularze bez Enter=zapis** — konwencja suity „Enter=zapis, Esc=wyjście wszędzie". Żaden modal nie zamyka się Esc: wspólny `components.tsx:30 Modal` + własne backdropy (`ForwardingPage:78`, `CustomsPage:57`, `QuoteRequestModal:60`, `collaboration:353`, QueuePage pendingMove/whConfirm, ImportModal, FoundOrderModal, QueueEmailModal). Formularze wyceny używają `div`+`onClick` zamiast `<form onSubmit>` — Enter nic nie robi (`QuotesPage` 474/514/567/632, `QuoteRequestModal:59`). **Root-cause: `onKeyDown` Esc→onClose + `role="dialog"`/`aria-modal` w komponencie Modal; owinąć formy w `<form>`.** (~10 miejsc)
4. **[1]/[9] Ciche `.catch(()=>{})` na ładowaniu słowników/list** — `components.tsx:66 useDicts` (dostawcy/spedytorzy/magazyny/porty/armatorzy → puste selecty bez sygnału), `ComplaintsPanel:39,43` (reklamacje + typy problemów — tablet!), `PalletCallsPage:266` (PAZ), `DashboardPage:100` (rfq), `FoundOrderModal:54-65` + `QueuePage:415` (dostawcy). Pusta lista wygląda jak „brak danych", nie „błąd". (~8 miejsc)
5. **[2] Surowe enumy / snake_case / angielski w UI** — role po angielsku w `UsersTab.tsx:137-144,169-176,217` (`logistics/warehouse/forwarder/...`), historia zmian `ContainerPage.tsx:354-356` (`entry.field`=nazwa kolumny DB, surowe old/new), `QuotesPage.tsx:375` (`r.kind`), do sprawdzenia `sent_status`/`document_status` w QueuePage.
6. **[5] Podwójny submit w formularzach admina** — brak `busy`/`disabled` na „Dodaj/Zapisz" w ~9 miejscach: `CompaniesTab:34`, `WarehousesTab:60`, `CaseStatusesTab:47`, `ProblemsTab:46`, `DocumentTypesTab:55`, `CustomsAgenciesTab:46`, `NamedTab:93`, `UsersTab:157,192`; plus `PalletCallsPage:269` (PazSection add), `CustomsPage` (status w tabeli), `QuotesPage:70` (`act`). Ryzyko duplikatów wpisów/kont.
7. **[1] Gołe `<p>{t('loading')}</p>` zamiast Skeleton + błąd bez retry** — `ComplaintDetailPage:84`, `AnalysisTab:67-68`, `ForecastTab:39-40` (reszta apki ma już Skeleton/LoadError).
8. **[4] Twarde kolory poza tokenami** — `DashboardPage` (Tailwind arbitralne `bg-[#1c2639]`, `ring-[#3a4d70]` — lokalny wariant zamiast `.panel`+`var(--…)`) oraz ~60 hexów w `styles.css` mimo tokenów w `:root`. Utrudnia 4 warianty motywu per spółka. *Niespójność wizualna, nie blokujące.*

---

## Sekcja per widok (wybrane, z plik:linia i propozycją)

### QueuePage / QueueSummaryBar
- `QueuePage.tsx:1567-1576` [1/9] — „🛰️ Śledź teraz" strzela POST bez spinnera/disabled/toastu, błąd w pustym `catch{}`. → toast po 202 + toast błędu (JS, S).
- `QueuePage.tsx:610-632` [1/5] — `exportXlsx`/`exportXlsxAll` bez stanu busy → wielokrotny klik w trakcie pobierania. → `exporting` + disabled (JS, S).
- `QueuePage.tsx:168,807,831` [2] — `sent_status`/`document_status` renderowane wprost — do sprawdzenia czy backend nie zwraca enuma EN (ręcznie).
- **OK:** `loadSeq` anti-race, chipy filtrów + „Wyczyść wszystkie" + filtry w URL, ColumnFilter label-as-option, potwierdzenia przeniesienia dat/zmiany magazynu, busy w modalach kolejki.

### CalendarPage
- `CalendarPage.tsx:56` [4] — nazwa miesiąca przez `toLocaleDateString(undefined)` = locale przeglądarki, nie język apki. → `LOCALES[lang]` (JS, S).
- `:109,111` [2] — strzałki roku bez `title`/`aria-label`. → dodać (szablon, S).

### ImportModal / FoundOrderModal / QueueEmailModal
- `QueueEmailModal.tsx:31-33` [4] — wysyłka do spedytorów przez natywny `window.confirm` zamiast modalu DS; data jako surowe ISO. → modal DS + format daty (JS, M).
- `ImportModal.tsx:179` [2] — przycisk `'OK'` hardcoded; `:97-104` nagłówek „REF" i pola bez typu. → `t()` + otypowanie (JS, S).
- `FoundOrderModal.tsx:54-65` [9] — ładowanie słowników `.catch(setX([]))` bez komunikatu (patrz systemowe #4).

### ContainerPage / collaboration / ContainerItems
- `ContainerPage.tsx:354-356` [2/4] — historia zmian pokazuje nazwy kolumn DB i surowe wartości. → mapa `field`→PL + tłumaczenie wartości (JS+i18n, M).
- `ContainerItems.tsx:72-74` [4] — sumy wag `.toFixed(2)` z kropką (patrz #2).
- `collaboration.tsx:729`, `QuotesPage.tsx:525` [7] — telefon agenta celnego/spedycji bez `inputMode="tel"` (DriverPanel ma). → dodać (szablon, S).
- **OK:** guard `loadSeq`/`mounted` w refreshTracking, `item()` traktuje 0 jako wartość, ⚠ stale-tracking.

### ForwardingPage / CustomsPage
- `CustomsPage.tsx:141-171,242-245` [1/3/5] — zmiana statusu celnego selectem zapisuje natychmiast, bez busy; cofnięcie z ODPRAWIONY ma potwierdzenie, ruch „do przodu" nie. → busy + rozważyć toast „cofnij" (JS, M).
- daty pickup/delivery/eta surowe ISO (#1).
- **OK:** `BackwardStatusConfirm`, scoping `/board` serwerowy.

### QuotesPage / QuoteRequestModal
- `QuotesPage.tsx:70,294,338,346,392` [1] — `act` bez busy → wielokrotne send/choose/approve/reopen. → busy w `act` (JS, M).
- formularze bez `<form onSubmit>` (#3); `r.kind` surowy; SCFI/ETD/ETA bez tooltipa [10] → `HelpTip` (szablon, S).
- **OK:** QuoteRequestModal — podwójny guard e-maila spedytora, busy, wybór oferty przez modal (naprawione).

### OrdersPage / TrackingPage
- `OrdersPage.tsx:40,50-52` [4] — legenda paska postępu tylko w `title` (hover) → mini-legenda (widok, S).
- `TrackingPage.tsx:231` [4] — `occurred_at` formatowany inline, łamie dd.mm.rrrr (#1).
- **OK:** tracking — pinned tooltip dotyk/klawiatura, aria, legenda statusów, uczciwy „nie zdążył zsync" (wzorcowe po naprawie).

### DashboardPage
- `:40-48,59,122` [4] — kafle/tabele Tailwindem z arbitralnymi hexami zamiast DS suity (#8). → ujednolicić (widok, M).

### ComplaintsPanel / ComplaintDetailPage (tablet + aparat)
- `ComplaintDetailPage.tsx:24` [9] — `.catch(navigate('/reklamacje'))` — każdy błąd (też timeout) po cichu wyrzuca z ekranu. → `LoadError` z retry (widok, S). **Ryzyko utraty kontekstu na tablecie.**
- `:169,187` [2] — w trakcie wysyłki przycisk pokazuje „Ładowanie" zamiast „Wysyłanie…". → osobny label (i18n, S).
- `ComplaintsPanel:39,43` [9] — ciche catch; pusta lista typów problemów blokuje zgłoszenie bez wyjaśnienia (#4).
- **OK:** idempotentny submit (nie duplikuje zgłoszenia po błędzie uploadu), `capture="environment"`, busy.

### WarehouseQueuePage (tablet)
- `:38` [7] — „Pokaż szczegóły" `btn small` — cel dotyk może <44px (globalny `pointer:coarse` już wymusza 44px — do potwierdzenia że łapie ten przycisk).
- `:76-79` [—] — sort dat `localeCompare` na stringu — poprawny tylko dla ISO (do sprawdzenia ręcznie).

### PalletCallsPage
- `PazSection` import `:278-283` [9] — pokazuje tylko liczbę zaimportowanych, brak raportu odrzuconych wierszy (Analityka to ma — wzór). → zwrócić i pokazać odrzucone (backend+widok, M).
- `:269` [5] — PazSection `add()` bez busy (#6); `:31,187` liczby/daty (#1,#2).
- **OK:** confirm anulowania wywołania, anti-race analizy, statusy `pcStatus_` (naprawione).

### AnalitykaPage / AnalysisTab / ForecastTab
- gołe loadery + błąd bez retry (#7); `ForecastTab:49-55` [4] heatmapa fc-ok/warn/over bez legendy → dodać legendę (widok, S); `:94` [1] komórka z wieloma kontenerami otwiera tylko pierwszy bez sygnału.
- `AnalysisTab:87` [8] pusty `<th>` (martwy nagłówek).
- **OK:** import Analityki (preview→commit + pełny raport odrzuconych) — wzór dla PAZ; anti-race, zakres dat w URL.

### LoginPage / AuthPages
- `LoginPage.tsx:183` [1] — „• System online" zawsze zielone (dekoracja sugerująca status). → usunąć/odzwierciedlić realny stan (szablon, S).
- `:140,154` [2] — „Container Flow" (EN) i placeholder „np. m.kowalski" hardcoded. → i18n/branding (szablon, S).
- **OK:** 401 vs 5xx rozróżnione, busy, autoComplete/autoFocus, anty-enumeracja resetów.

### AvizoFormPage / DriverPage (publiczne mobile)
- `AvizoFormPage.tsx:149-198` [8] — 10-kolumnowa tabela z poziomym scrollem na telefonie. → układ kartowy per-kontener na wąskim viewporcie (szablon/CSS, L).
- `:178`, `DriverPage.tsx:65` [2] — `notify_date`/`delivery_date` surowe ISO (#1).
- `DriverPage.tsx:87-104` [3] — po „Przyjechałem/Spóźnię się" akcje znikają, brak cofnięcia pomyłki (do sprawdzenia: scenariusz zła godzina).
- **OK:** 404/410 „wygasło" vs 5xx retry, `inputMode=tel`, `autoCapitalize` na nr auta, pusty string→null.

### AdminPage / admin/*
- role EN (#5), ~9 add bez busy (#6).
- `SettingsTab.tsx:29-30` [5] — `reminder_days` wolny tekst bez walidacji („15;30"/„abc" → 422). → `pattern`/walidacja CSV + hint (JS, S).
- `SettingsTab.tsx:54` [2] — sukces pokazuje „✓ Zapisz" zamiast „Zapisano". → klucz `saved` (szablon, S).
- `NamedTab.tsx:151-155` [3/5] — „Scal" (merge, nieodwracalne) bez potwierdzenia. → `window.confirm` (JS, S).
- `UsersTab.tsx:65-84` [5] — `toggleActive`/`removeUser` bez busy (usuwanie ma confirm — OK).
- `shared.tsx:54` — mailto z długim body (hasło+link) bywa ucinany przez klienty poczty (do sprawdzenia ręcznie).
- **OK:** hasła zaproszeń losowane serwerowo, confirm na usuwaniu, `rolePayload` = jedna reguła.

---

## Ryzyka danych (pkt 5 i 9 — nie kosmetyka)

1. **`components.tsx:66 useDicts` cichy `.catch(()=>{})`** [9] — awaria API słowników daje puste selecty bez sygnału; user może zapisać kontener bez dostawcy/spedytora nieświadomy, że lista nie doszła. **Priorytet.** → flaga błędu + `LoadError`/toast (front, S).
2. **`ComplaintDetailPage.tsx:24` redirect-on-error** [9] — chwilowy timeout wyrzuca z ekranu bez komunikatu (tablet). → LoadError z retry (front, S).
3. **`ComplaintsPanel:43` cichy catch typów problemów** [9] — pusta lista blokuje zgłoszenie reklamacji bez wyjaśnienia (tablet magazynowy). → komunikat błędu (front, S).
4. **Admin: ~9 add-formularzy bez busy** [5] — podwójny klik tworzy duplikaty spółek/magazynów/słowników/kont. → busy+disabled (front, M).
5. **`SettingsTab reminder_days` bez walidacji** [5] — literówka leci na backend jako 422 bez wskazania pola. → walidacja CSV + hint (front, S).
6. **`PalletCallsPage` import PAZ bez raportu odrzuconych** [9] — user nie wie, które wiersze wpadły, a które nie. → raport jak w Analityce (backend+front, M).
7. **Format dat ISO / kropka dziesiętna** [5] — ryzyko błędnego odczytu wag/kwot/dat przez użytkownika (nie korupcja DB, ale błędna decyzja). → helpery formatujące (front, S/M).

**Backend — brak realnych ryzyk:** scoping/izolacja egzekwowane serwerowo i fail-closed (`deps.py`), zero `except: pass`/surowego traceback, komunikaty po polsku z „co dalej", import w savepointach z raportem odrzuconych, blokada podwójnej wysyłki reklamacji (409).

---

## Niespójności z suitą

- **Daty ISO `rrrr-mm-dd`** zamiast `dd.mm.rrrr` — systemowo (#1). Build-stamp już jest w dd.mm.rrrr → niespójność wewnętrzna.
- **Separator dziesiętny — kropka** zamiast przecinka (#2).
- **Enter/Esc** — modale nie zamykają się Esc, formularze wyceny nie zapisują Enterem (#3), wbrew „Enter=zapis, Esc=wyjście wszędzie".
- **Role po angielsku** (`logistics/warehouse/...`) w UsersTab zamiast PL — statusy/role mają być spójne między aplikacjami suity.
- **DashboardPage** stylowany Tailwindem z arbitralnymi hexami = lokalny wariant zamiast jednego design systemu suity (#8).
- **Angielskie stringi** hardcoded: „Container Flow" (LoginPage), „OK" (ImportModal), „REF"/SCFI bez opisu.
- **PAZ vs PAL** — konwencja zachowana (jednostka to PAZ; „pallet" w kodzie to tylko identyfikatory, nie UI). ✅

---

## Priorytety (maks. 10, wg wpływu/koszt)

| # | Poprawka | Heur. | Warstwa | Rozmiar |
|---|----------|-------|---------|---------|
| 1 | `useDicts` cichy catch → flaga błędu + komunikat (ryzyko niekompletnych danych) | [9] | JS | S |
| 2 | `ComplaintDetailPage` redirect-on-error → LoadError+retry; `ComplaintsPanel` ciche catch (tablet) | [9] | JS | S |
| 3 | `formatDate()`/`formatDateTime()` → `dd.mm.rrrr` w jednym helperze + użycie w polach dat | [2/4] | JS | M |
| 4 | Modal: `onKeyDown` Esc→onClose + `role/aria`; formularze wyceny w `<form onSubmit>` (Enter=zapis) | [3/7] | JS | S/M |
| 5 | Admin: `busy`+`disabled` na ~9 add-formularzach (duplikaty) | [5] | JS | M |
| 6 | Role EN → mapa enum→PL w UsersTab (select + tabela) | [2] | JS | M |
| 7 | Gołe `<p>loading>` ×3 → Skeleton; błąd bez retry → LoadError (Complaint/Analysis/Forecast) | [1/9] | JS | S |
| 8 | `formatNum` z przecinkiem (`toFixed`/`toLocaleString`) — wagi/kwoty/palety | [4] | JS | S |
| 9 | `SettingsTab reminder_days` walidacja CSV + hint; `QueueEmailModal` window.confirm→modal DS | [5/4] | JS | S |
| 10 | Import PAZ → raport odrzuconych wierszy (jak Analityka) | [9] | backend+JS | M |

---

## Sekcja „OK" — wzorce warte zachowania (nie zepsuć przy refaktorze)

- **Backend:** scoping fail-closed scentralizowany w `deps.py` (`_enforce_scope`/`get_scoped`/`scope_*`, nieznany kształt → 403); zero `except: pass`/surowego traceback; komunikaty po polsku z „co dalej"; import w `begin_nested()` (savepoint) z pełnym raportem odrzuconych; blokada podwójnej wysyłki reklamacji (409).
- **api.ts:** 401→refresh→retry współdzielony; tłumaczenie pydantic 422 na polski; jednolity `errorMessage`; 204-safe.
- **feedback.tsx:** jeden ToastProvider (portal, `aria-live`), Skeleton `role=status`, LoadError z retry — używane w większości widoków.
- **i18n:** pl/en/pt kompletne przez łańcuch fallbacków (`pt←en←pl`); konwencja PAZ zachowana.
- **Anti-race:** `loadSeq`/`mounted`/`ignore`-flag w QueuePage, CalendarPage, ContainerPage, OrdersPage, PalletCallsPage, AnalysisTab.
- **Kontrola/cofanie:** chipy filtrów + „Wyczyść wszystkie" + filtry w URL (deep-link, „wstecz"); potwierdzenia destrukcji i wysyłek zewnętrznych; `BackwardStatusConfirm` przy cofaniu statusu.
- **Reklamacje:** idempotentny submit (retry nie duplikuje zgłoszenia, dosyła tylko brakujące zdjęcia), `capture="environment"`.
- **Tracking:** pinned tooltip dla dotyku + fokus klawiaturą + aria + legenda (naprawione w tej iteracji).
- **Auth/mobile publiczne:** 401 vs 5xx rozróżnione, 404/410 „wygasło" vs 5xx retry, `inputMode=tel`, anty-enumeracja resetów.
- **Import Analityki:** dwuetapowy preview→commit z pełnym raportem odrzuconych — wzór dla importu PAZ.
- **Tap-targety:** globalny `@media (pointer: coarse)` wymusza ≥44px (naprawione w tej iteracji).

---

## Do sprawdzenia ręcznie
- Realne renderowanie `sent_status`/`document_status`/importowanych `eta` — czy backend zwraca enum EN / ISO (scenariusz: rekord z danym statusem/datą → porównaj z konwencją).
- Rozmiary celów dotykowych na breakpoincie tabletu (DevTools) — czy `pointer:coarse` łapie `btn small` w WarehouseQueue i chip-x/+N w kolejce.
- `type=number` a przecinek dziesiętny w locale PL (FoundOrderModal kwota/waga) — test w przeglądarce.
- Sort dat w WarehouseQueuePage (`localeCompare`) — czy backend daje ISO (poprawnie) czy dd.mm (sort się sypie).
- `shared.tsx` mailto z długim body (hasło+link) — czy dochodzi w webmailu.
- DriverPage — scenariusz „kierowca kliknął o złej godzinie" (brak cofnięcia).

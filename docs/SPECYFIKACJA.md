# TIMPORYE — System zarządzania kolejką kontenerów

Specyfikacja ustalona w wywiadzie projektowym (50 pytań, 02.07.2026).
Źródłem danych startowych jest plik `KOLEJKA_KONTENERÓW_2025_BOREALIS.xlsx`.

## 1. Użytkownicy i spółki

- **Spółki w systemie:** Borealis, Cobalt Sport, Iberia, Acme (+ możliwość dodawania kolejnych).
- **Separacja danych:** pełna — każda spółka widzi wyłącznie swoje kontenery.
  Wyjątek: **logistyka Acme oraz admin widzą wszystko** (flaga `view_all_companies`).
- **Logowanie:** login + hasło (konta lokalne, zakładane przez admina).
- **Role:**
  - `admin` — pełny dostęp: użytkownicy, wszystkie spółki, konfiguracja,
  - `logistics` (logistyka) — dodawanie/edycja kontenerów i statusów w ramach swojej spółki,
  - `warehouse` (magazyn) — potwierdzanie rozładunków, bez edycji danych kontenera,
  - `forwarder` (spedytor) — patrz niżej,
  - `customs` (agencja celna) — partner zewnętrzny z własnym loginem; widzi tylko kontenery,
    których odprawę jej zlecono,
  - `purchasing` (zakupy) — pracownik wewnętrzny zawężony do spółki,
  - `sales` (sprzedaż) — tylko odczyt (kolejka, kalendarz, śledzenie, Specjalna troska), bez kosztów.
- **Zawężenie do magazynów** (`deps.scope_containers`): logistyk z ustawioną listą
  `allowed_warehouse_ids` widzi tylko kontenery tych magazynów (pusta lista = wszystkie);
  konto magazynu (np. zewnętrzny DLT) widzi wyłącznie swój jeden magazyn — bez przypisanego
  magazynu nie ma dostępu.
- **Spedytorzy (SPEDALFA, SPEDBETA, Delta Brokers):** osobny moduł współpracy (Etap 3):
  zlecenia transportowe (pełny obieg: wystawienie → akceptacja/odrzucenie → realizacja → potwierdzenie),
  wymiana plików (dokumenty transportowe: CMR, zlecenia, awizacje, kwity),
  wątki wiadomości/zapytań przy kontenerze, wskazywanie agenta celnego.

## 2. Kontener i statusy

- **Cykl życia (10 statusów; `W_PRODUKCJI` i `TRANSPORT_WSTEPNY` dodane 2026-09-24):**
  `ZAPOWIEDZIANY → W_PRODUKCJI → TRANSPORT_WSTEPNY → W_TRANSPORCIE → W_PORCIE → ODPRAWA → AWIZOWANY → W_DOSTAWIE → DOSTARCZONY → ZREALIZOWANY`
- **Status odprawy celnej — osobne pole** (etap zgłoszenia `DRAFT_*` — §10.4; `ROZLICZONY` po odprawie):
  `BRAK → DOKUMENTY_KOMPLETNE → ZLECONA → DRAFT_WYSLANY → DRAFT_POTWIERDZONY → ODPRAWIONY → ZWOLNIONY → ROZLICZONY`, oraz `REWIZJA` (z datą i notatką — kontener widoczny jako wstrzymany). `ZWOLNIONY` = towar zwolniony (SAD-PW), można wydać.
- **Kto zmienia status odprawy** (`containers_common.check_customs_status_change`, jedno miejsce
  dla wszystkich ścieżek zapisu): agencja celna; logistyka/admin awaryjnie; spedytor nigdy.
  Cofnięcie z `ODPRAWIONY`/`ZWOLNIONY`/`ROZLICZONY` — tylko logistyka/admin, zawsze z notatką.
  `REWIZJA` — zawsze z notatką; brak daty = dzień wpisu.
- **Status kontenera wynika ze statusu odprawy** (`sync_status_from_customs`, tylko do przodu):
  odprawa w toku → `ODPRAWA`; odprawiony/zwolniony + data awizacji → `AWIZOWANY`.
  Wgrany dokument z kodem kafelka **SAD-PZ → `ODPRAWIONY`, SAD-PW → `ZWOLNIONY`** (automat działa
  tylko, gdy wgrywający sam może zmieniać status odprawy — plik od spedytora zapisuje się bez
  zmiany statusu).
- **Zmiana statusu:** komentarz opcjonalny przy ruchu do przodu.
  **Cofnięcie statusu** o jeden krok wymaga notatki z powodem; cofnięcie o więcej niż jeden krok
  może zrobić tylko admin (decyzja D2, `containers_common.check_status_transition`).
  Magazyn potwierdzający rozładunek kontenera, który nie był awizowany / w dostawie,
  musi podać notatkę (audyt BIZ-002, `containers_write.apply_status`).
- **Opóźnienia** (`Container.is_delayed`): oznaczane **automatycznie** — minęło ETA, a kontener
  jest wciąż przed przybyciem (`ZAPOWIEDZIANY` … `W_TRANSPORCIE`; `W_PORCIE`/`ODPRAWA` liczą się
  jako przybyłe), albo minęła data awizacji bez dostawy. `DOSTARCZONY`/`ZREALIZOWANY` nigdy.
- **Numer kontenera:** walidacja **blokująca** wg ISO 6346 (4 litery + 7 cyfr + cyfra kontrolna).
- **Zamówienie (PO) jako osobny obiekt** — jedno PO może mieć wiele kontenerów; widok postępu realizacji.
- **Pola obowiązkowe:** numer kontenera; dostawca wybierany ze słownika; pozostałe pola konfigurowane per spółka (do doprecyzowania).
- **Numery dostawy przychodzącej i RF:** wpisywane ręcznie (z ERP).
- **Transport główny** (`transport_type`): morski / lotniczy / kolej (+ `kola`, `inne`
  dla starych danych) + pole na szczegóły (`transport_details`).
- **Dowóz po odprawie** (`on_carriage`): drogowo / intermodal.
- Oba pola to **stałe listy w kodzie** (enumy `TransportType`, `OnCarriage` w `models/enums.py`),
  nie słowniki edytowalne przez użytkownika.
- **Historia zmian:** audyt **wszystkich pól** — kto, kiedy, stara i nowa wartość.

## 3. Awizacje i limity

- **Awizacja na datę** (bez slotów godzinowych).
- **Limit dzienny rozładunków:** domyślny per magazyn + **nadpisanie na konkretny dzień**
  (np. domyślnie 7, jednego dnia 10, kolejnego 6). Przekroczenie = **ostrzeżenie, można zapisać**.
- **Przeniesienie awizacji:** zwykła zmiana daty, ale zapisywana w historii z poprzednią datą i powodem.
- **Dni wolne:** kalendarz oznacza soboty, niedziele i święta **PL i PT** (magazyn w Iberia)
  + własne dni wolne/robocze per magazyn (np. sobota pracująca za święto).
- **Magazyn potwierdza rozładunek** po fakcie (bez akceptacji terminu awizacji).

## 4. Integracje / API

- **Śledzenie:** pozycje statków z AIS (aisstream.io), mapa/globus, oś czasu kontenera,
  kongestia portów. **Mapa terenu** (wektor + cieniowana rzeźba Natural Earth) na mapie 2D
  i globusie przy każdym zbliżeniu; zdjęcie satelitarne NASA to opcjonalna warstwa, domyślnie
  wyłączona. Kafelki trzymane w repo (`frontend/public/globe/tiles`). Integracja z zewnętrznym providerem trackingu kontenerów (2026-09)
  została usunięta decyzją biznesową — status kontenera zmienia się ręcznie.
- **Autoryzacja:** OAuth2 (tokeny access + refresh) dla panelu i systemów zewnętrznych.
- **Dokumentacja API:** automatyczna (OpenAPI/Swagger pod `/docs`) — **tylko poza produkcją**;
  na produkcji `/docs`, `/redoc` i `/openapi.json` są celowo wyłączone (`backend/app/main.py`).

## 5. Powiadomienia

- **Kanały:** e-mail, w aplikacji (dzwoneczek), Teams/Slack (webhook).
- **Zdarzenia:** zmiana ETA / opóźnienie, nowe zlecenie / wiadomość / plik, zbliżający się koniec demurrage.
- **Wyprzedzenie alertu demurrage:** konfigurowalne (domyślnie 3 dni).
- **Aktualności na Pulpicie**: powiadomienia pokazywane jak news — kategoria
  (statki / odprawa / zamówienia / dostawy / wiadomości / system) i ważność z rodzaju
  (`notification_feed.CATEGORIES`, `URGENT`), wątek per kontener albo statek, pilne
  nieprzeczytane przypięte na górze, filtry i „załaduj starsze”. Dzwonek prowadzi na Pulpit.
  Przeczytane powiadomienia kasowane po `NOTIFICATION_RETENTION_DAYS` (90 dni).

## 6. Interfejs

- **Języki:** PL + EN + PT (przełączane).
- **Widok główny:** tabela grupowana datami awizacji (jak Excel), statusy jako kolorowe etykiety.
- **Widoki dodatkowe:** dashboard ze statystykami, kalendarz awizacji z limitami,
  archiwum zrealizowanych, karta kontenera (dane + oś zdarzeń + historia + pliki + wiadomości).
- **Kafelki dokumentów dostawy** w karcie kontenera (`backend/app/document_tiles.py`):
  `PI · CI ⇄ PL · BL · SAD-DRAFT → SAD-PZ → SAD-PW`. Stan kafelka (brak / jest / sprawdzony /
  niepewny / sprzeczny) zbierany z trzech źródeł bez ponownego wgrywania: paczki faktur, załączniki
  z typem o kodzie kafelka (`DocumentType.tile_code`), drafty SAD agencji. „Wymagany” zależy od
  etapu kontenera (PI od `W_PRODUKCJI`; CI/PL/BL od `W_TRANSPORCIE`) i statusu odprawy
  (SAD-DRAFT od `DRAFT_WYSLANY`, SAD-PZ od `ODPRAWIONY`, SAD-PW od `ZWOLNIONY`).
  Spedytor widzi tylko CMR i pliki, które sam wgrał (`deps.forwarder_may_see`).
- **Filtry:** status + odprawa, zakres dat, dostawca/spedytor/magazyn, szukajka pełnotekstowa.
- **Eksport:** Excel (.xlsx).
- **Responsywny web** (działa na telefonie, bez osobnej aplikacji).

## 7. Słowniki

Dostawcy/producenci (per spółka), spedytorzy, magazyny (per spółka, z krajem i limitem dziennym),
porty, armatorzy. Rodzaje transportu (główny i dowóz) nie są słownikiem — to stałe listy w kodzie (§2).

## 8. Technologia

- **Backend:** Python + **FastAPI** (wybrane spośród Django/FastAPI/Flask), SQLAlchemy, Pydantic.
- **Baza:** **PostgreSQL** (SQLite do developmentu i testów).
- **Frontend:** **React + TypeScript** (Vite).
- **Hosting:** VPS/chmura, **Docker** (docker-compose: baza + API + web).
- **Migracja danych:** jednorazowy import z Excela (214 kontenerów, w tym 84 zrealizowane → archiwum).

## 9. Zakres MVP i etapy

MVP = wszystkie 4 moduły; realizacja etapami:

| Etap | Zakres | Status |
|------|--------|--------|
| **1. Fundament** | spółki, użytkownicy/role, kolejka, statusy, odprawy, audyt, słowniki, PO, awizacje + limity + kalendarz dni wolnych, import Excela, panel React | **zrealizowany** |
| **2. Śledzenie** | AIS statków, mapa/globus, oś czasu kontenera, kongestia portów (provider trackingu kontenerów usunięty 2026-09) | **zrealizowany** |
| **3. Moduł spedytora** | rola forwarder (widzi tylko swoje kontenery), zlecenia transportowe (pełny obieg z kontrolą przejść i ról), wiadomości przy kontenerze, załączniki, agent celny + status odprawy | **zrealizowany** |
| **4. Powiadomienia i raporty** | powiadomienia in-app (dzwoneczek) + e-mail (SMTP) + Teams/Slack (webhook), zdarzenia: zmiana ETA/opóźnienie, zlecenia/wiadomości/pliki, alerty demurrage (konfigurowalne wyprzedzenie, dedupe dzienny), eksport kolejki do .xlsx | **zrealizowany** |
| **5. Widoki i produkcja** | dashboard ze statystykami (kafelki + listy: dziś, opóźnione, demurrage), kalendarz awizacji (miesiąc, limity, dni wolne, klik → kolejka dnia), migracje Alembic | **zrealizowany** |
| **6. Postęp zamówień** | widok postępu realizacji PO: paski postępu (dostarczone / w porcie-odprawie / w drodze), status wyliczany (nowe / w toku / zakończone), szczegóły PO z listą kontenerów | **zrealizowany** |
| **7. Plan dostaw** | moduł „Plan dostaw" (§10): edytowalny układ widoku, ATD, statusy dokumentów, rozszerzony status odprawy, SENT + HS, powiązanie faktura ↔ kontener, pilność z zakupów | **w toku** (zrobione: wybór i kolejność kolumn, ATD, statusy dokumentów i odprawy, bramka zgodności dokumentu z dostawą; zostały: słownik kodów HS, pilność z zakupów) |

## 10. Plan dostaw — założenia (etap 7)

Ustalenia z omówienia modułu **Plan dostaw**. Sekcja jest źródłem dla etapu 7 —
punkty oznaczone **[?]** wymagają decyzji przed implementacją, **[✓]** są już w kodzie.

### 10.1 Widok

- **Minimalistyczny wygląd** — mniej ozdobników niż obecna kolejka, nacisk na czytelność wiersza.
- **[✓] Wybór widocznych kolumn** — przycisk „Kolumny" w kolejce (szeroki układ Acme/DLT);
  wybór zapamiętany per użytkownik w `localStorage` (przeżywa wylogowanie), nr kontenera
  zablokowany. Kolumny opisane jedną listą w `QueuePage.tsx` (szerokość + nagłówek + komórka).
- **[✓] Przestawianie kolejności kolumn** — przeciąganie nagłówka w kolejce
  (`frontend/src/pages/queue/useHeaderDrag.ts`), z klawiatury ↑/↓ w menu „Widok".
- Pilne kontenery mają **odrębną szatę kolorystyczną** (patrz 10.5).

### 10.2 Dane wiersza

| Pole | Stan w systemie |
|------|-----------------|
| Dostawca | jest — `Container.supplier_id` (słownik per spółka) |
| Nazwa statku / **nazwa pociągu** dla kolei | jest `Container.vessel` — do rozszerzenia o środek transportu kolejowego |
| Nr kontenera | jest — `container_no`, walidacja ISO 6346, **korekta ręczna zostaje** |
| Nr dostawy (18…) | jest — `incoming_delivery_no`, ma być powiązany z nr kontenera (10.3) |
| ETA / **ATD** | **[✓]** `Container.atd`; w kolejce kolumna ETA pokazuje ATD po dostawie, ETA schodzi do drugiej linii |
| Typ dostawy: drogowy / intermodal | **[✓]** `on_carriage` (drogowo / intermodal); transport główny osobno w `transport_type` (§2) |
| Magazyn | jest — `warehouse_id` |
| Spedycja | jest — `forwarder_id` + moduł spedycji |
| Nr rezerwacji frachtu | jest — `rf_number` |

- **ATD** — po dostawie ETA aktualizowana/uzupełniana o rzeczywistą datę.
  Docelowo dowodem ma być **zdjęcie kontenera ze statku** (załącznik przy kontenerze) — do zrobienia.
- **Moduł spedycji** ma pokazywać ten sam nr kontenera co plan dostaw (wspólny identyfikator).

### 10.3 Powiązanie faktura ↔ kontener ↔ nr dostawy

- **[✓]** Weryfikację z nr dostawy (18…) zastąpiła **bramka zgodności dokumentu z dostawą**
  (design: `docs/superpowers/specs/2026-10-01-bramka-dokument-dostawa-design.md`,
  kod: `backend/app/invoices/conformity.py`). Po wstawieniu faktury / packing listy system
  porównuje treść dokumentu z kontenerem: **nr kontenera, PO, dostawcę i materiały**
  (ilość ponad zamówienie = ostrzeżenie). Faktura wymieniająca kilka kontenerów jest
  sprawdzana wobec ich sumy.
- **[✓] Komunikaty i blokada:** wynik `conflict` (którykolwiek sygnał sprzeczny) blokuje
  zatwierdzenie i eksport dokumentu do poprawy; `uncertain` (brak danych SAP albo nadwyżka
  ilości) — zatwierdzenie wymaga powodu; `ok` — bez przeszkód.
- **[✓] Model powiązania:** kontener ma **wiele dokumentów**; paczka faktur (CI/PL/PI) jest
  podpięta pod **jeden kontener** (`InvoiceBatch.container_id`), a faktura wymieniająca kilka
  kontenerów jest sprawdzana wobec ich sumy. Faktura za transport (BL) obejmuje **wiele
  kontenerów** (`freight_invoice_containers`).
- **[✓] Materiały i ilości kontenera pochodzą z SAP** (`SapOrder`/`OrderItem`, importy EKKO/REF);
  faktura jest czytana parserem i porównywana z danymi SAP — integracja i parser razem.

### 10.4 Statusy dokumentów i odprawy

- **[✓] Statusy dokumentów** — `Container.document_status`: `BRAK → ZALACZONE → WYSLANE`
  (enum `DocumentStatus`). Stare `documents_ok` i tekstowy `document_flow` zostają na razie
  dla zgodności z importem Excela — do wygaszenia po przejściu użytkowników na nowy status.
- **[✓] Status odprawy** — `customs_status` rozszerzony o `DRAFT_WYSLANY` i `DRAFT_POTWIERDZONY`
  (między `ZLECONA` a `ODPRAWIONY`); dashboard liczy je jako odprawę w toku.
  **[?]** Czy przewidzieć „stopkę celną" jako osobny stan/pole?
- **SENT — TAK/NIE** — jest `sent_required` + `sent_number`; do dołożenia **słownik kodów HS**
  (kod + opis, wybór ze słownika zamiast wolnego tekstu).

### 10.5 Pilność z modułu zakupów

- Zakupy dostają **osobny moduł** do wpisania zapotrzebowania w **dowolnej jednostce**
  (sztuki / opakowania / inna), a **system przelicza, ile kontenerów jest pilnych**.
- Kontenery pilne dostają **status „pilny"** i **osobną kolorystykę** w planie dostaw.
- Przelicznik jednostka → kontener wymaga danych o zawartości kontenera — są w SAP (10.3).
- **Stan w kodzie: nie zaimplementowane.** Istnieje tylko status działu zakupów
  (`Container.purchasing_status`) i ręczna flaga „specjalny" z powodem `pilne`
  (`SPECIAL_REASONS`) — brak modułu zapotrzebowania i automatycznego przeliczania pilności.

### 10.6 Rezerwacja frachtu

- **[?]** Odpisywanie dostaw w rezerwacji frachtu — **stornowanie nie jest rozwiązaniem**.
  Do zaprojektowania mechanizm częściowego wykorzystania rezerwacji (saldo: zarezerwowane
  vs wykorzystane vs pozostałe) bez korekt księgowych.

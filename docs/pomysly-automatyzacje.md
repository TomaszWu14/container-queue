# Pomysły na automatyzacje procesów — ZAKUPY · LOGISTYKA · SPRZEDAŻ

> Katalog konkretnych, wykonalnych pomysłów automatyzacyjnych z użyciem: **Python, n8n, SharePoint, Excel, Power Automate, Power BI, OCR, API REST, SMTP/mail** oraz SAP jako źródła danych.
> Format każdego pomysłu: `- **[narzędzie]** Tytuł — co robi / problem / wyzwalacz→akcja.`
> Dokument roboczy — traktuj pozycje jak backlog, nie jako gotowe specyfikacje.

---

## 1. ZAKUPY

### 1.1 Monitoring cen i rynku

- **[Python]** Scraper cen dostawców — codzienny `requests`+`BeautifulSoup` po stronach cenników, zapis do CSV, alert gdy cena spadła >5%.
- **[Python]** Historia cen surowca — pobór notowań (LME/API GUS) do SQLite, wykres trendu 30/90/365 dni; wyzwalacz cron→mail z PNG.
- **[n8n]** Alert progu cenowego — HTTP node odpytuje API giełdy, IF cena < próg → Telegram/Teams.
- **[Excel]** Power Query z kursem NBP — automatyczne pobranie tabeli kursów, przeliczenie cen importowych na PLN przy odświeżeniu.
- **[Python]** Monitoring cen konkurencji marketplace — parsowanie Allegro/Amazon API, dzienny snapshot do arkusza, flaga podbicia/obniżki.
- **[Python]** Indeks kosztowy koszyka zakupowego — ważona średnia cen TOP 20 pozycji, alert gdy indeks rośnie >X% m/m.
- **[Power BI]** Dashboard trendów cen zakupu — kafelki price index per kategoria, drill-down do dostawcy.
- **[n8n]** Watcher zmiany cennika PDF — trigger na nowy plik w SharePoint, OCR, porównanie z poprzednią wersją, diff na mail.
- **[Python]** Alert kursu walut vs budżet — porównanie kursu spot z kursem budżetowym, ostrzeżenie o ryzyku FX na zamówieniach w USD/EUR.
- **[Excel]** Symulator wpływu ceny surowca na koszt wyrobu — dynamiczna tablica przelicza BOM przy zmianie ceny wejścia.
- **[Python]** Wykrywanie anomalii cenowych — z-score na cenach pozycji, oznacz pozycje z nietypowym skokiem do przeglądu.
- **[API]** Integracja z API dostawcy hurtowego — pobór aktualnych cen i dostępności przez REST, cache do bazy.
- **[Python]** Kalkulator TCO importu — cena + fracht + cło + ubezpieczenie + magazynowanie, ranking ofert wg landed cost.
- **[n8n]** Codzienny digest zmian cen — agregacja wszystkich alertów cenowych w jeden mail o 8:00.
- **[Power BI]** Analiza rozproszenia cen tej samej pozycji u różnych dostawców — box plot, wykrycie przepłacania.

### 1.2 Automatyczne zamówienia i reorder point

- **[Python]** Silnik reorder point — codzienny odczyt stanów z SAP, jeśli stan < ROP → generuj propozycję PO do arkusza.
- **[Python]** Wyliczanie ROP z lead time — `ROP = śr_zużycie_dzienne * lead_time + zapas_bezpieczeństwa`, aktualizacja co tydzień.
- **[Excel]** Arkusz min/max z warunkowym formatowaniem — czerwony gdy stan < min, przycisk „generuj zapotrzebowanie".
- **[n8n]** Auto-draft zamówienia — gdy stan poniżej progu (webhook z SAP) → utwórz szkic PO i wyślij do akceptacji.
- **[Python]** EOQ kalkulator — wylicza ekonomiczną wielkość zamówienia z kosztu zamówienia i kosztu magazynowania.
- **[Python]** Prognoza zapotrzebowania (Holt-Winters) — sezonowa prognoza zużycia per SKU, sugeruje wielkość i termin zamówienia.
- **[Power Automate]** Flow zatwierdzania PO — propozycja → approval do przełożonego → po akceptacji mail do dostawcy.
- **[Excel]** Konsolidacja zapotrzebowań z wielu działów — Power Query łączy arkusze cząstkowe w jedno zbiorcze zamówienie.
- **[Python]** Grupowanie PO wg dostawcy — agregacja pozycji do jednego zamówienia per dostawca (mniej fraktu).
- **[Python]** Optymalizacja pod próg darmowej dostawy — dobiera pozycje tak, by przekroczyć próg free shipping.
- **[n8n]** Cykliczne zamówienia kontraktowe — harmonogram wysyła stałe zamówienia (call-off) wg umowy ramowej.
- **[Python]** Wykrywanie martwych zapasów przed zamówieniem — blokuje reorder pozycji bez rotacji >180 dni.
- **[Excel]** Kalkulator pokrycia zapotrzebowania — ile dni starczy zapas przy bieżącym zużyciu, kolor wg pilności.
- **[Python]** Auto-split zamówienia między dostawców — dzieli wolumen wg alokacji/ceny/dostępności.
- **[Power Automate]** Eskalacja niezatwierdzonego PO — jeśli approval wisi >24h → przypomnienie, >48h → eskalacja wyżej.

### 1.3 Walidacja faktur vs PO (3-way match)

- **[Python]** 3-way match — porównanie faktura ↔ PO ↔ przyjęcie (GR), flagowanie rozbieżności ilości/ceny.
- **[OCR]** Ekstrakcja danych z faktury PDF — OCR + regex/LLM wyciąga nr faktury, NIP, pozycje, kwoty do arkusza.
- **[Python]** Kontrola ceny na fakturze vs cena z PO — tolerancja ±X%, powyżej → hold i mail do zakupów.
- **[Python]** Walidacja sum i VAT — sprawdza czy netto+VAT=brutto i czy stawka VAT poprawna.
- **[n8n]** Pipeline faktur z maila — załącznik PDF z inboxu → OCR → walidacja → wpis do rejestru → do akceptacji.
- **[Python]** Wykrywanie duplikatów faktur — hash (dostawca+nr+kwota), alert przed podwójną płatnością.
- **[Excel]** Rejestr faktur z auto-statusem — Power Query łączy faktury z PO, kolumna status (OK/rozbieżność/brak PO).
- **[Python]** Kontrola faktury bez PO — flaguje faktury bez powiązanego zamówienia (maverick buying).
- **[Power Automate]** Routing faktury do akceptanta — wg kwoty i centrum kosztów kieruje do właściwej osoby.
- **[Python]** Sprawdzenie terminu płatności vs umowa — porównuje termin na fakturze z warunkami kontraktowymi.
- **[OCR]** Odczyt numeru rachunku bankowego z faktury — porównanie z białą listą podatników VAT (API MF).
- **[API]** Weryfikacja NIP w VIES/białej liście — sprawdza status VAT dostawcy przed księgowaniem.
- **[Python]** Dopasowanie pozycji fuzzy — gdy opis na fakturze różni się od PO, dopasowanie `fuzzywuzzy`.
- **[Excel]** Zestawienie rozbieżności cenowych do reklamacji — auto-lista pozycji przepłaconych z kwotą różnicy.
- **[Python]** Auto-generacja noty korygującej — gdy wykryto błąd formalny, szkic noty do dostawcy.

### 1.4 Terminy, przypomnienia, dokumenty

- **[Python]** Monitor terminów umów — skan dat wygaśnięcia kontraktów, alert 60/30/7 dni przed.
- **[n8n]** Przypomnienie o odnowieniu certyfikatów dostawcy — trigger na datę ważności ISO/atestu → mail.
- **[Power Automate]** Kalendarz płatności — z terminów faktur tworzy zdarzenia w Outlook/Teams.
- **[SharePoint]** Lista dokumentów z alertami wygaśnięcia — kolumna data + flow przypominający.
- **[Python]** Tracker terminów dostaw — porównuje potwierdzoną datę z dzisiejszą, eskalacja opóźnień.
- **[Excel]** Kalendarz zamówień z podświetleniem przeterminowanych — warunkowe formatowanie dat.
- **[n8n]** Follow-up niepotwierdzonego zamówienia — jeśli brak potwierdzenia po 2 dniach → auto-ponaglenie.
- **[Python]** Archiwizacja dokumentów zakupowych — porządkowanie plików PO/faktur w foldery per dostawca/rok.
- **[OCR]** Indeksowanie skanów dokumentów — OCR nadaje nazwy plikom wg treści (nr dokumentu, data).
- **[SharePoint]** Repozytorium umów z metadanymi — biblioteka z kolumnami dostawca/wartość/data, wyszukiwanie.
- **[Python]** Generator raportu wygasających umów — tygodniowy PDF z listą kontraktów do renegocjacji.
- **[Power Automate]** Przypomnienie o rewizji cennika — cykliczne zadanie renegocjacji przy każdej rocznicy umowy.

### 1.5 Scoring i master data dostawców

- **[Python]** Scoring dostawców — ważony wskaźnik z OTIF, jakości, ceny, reklamacji; ranking do arkusza.
- **[Power BI]** Scorecard dostawcy — dashboard z KPI dostawcy, trend 12M, benchmark do średniej.
- **[Python]** Wskaźnik OTIF (On-Time-In-Full) — z danych dostaw liczy % terminowych i kompletnych.
- **[Excel]** Macierz Kraljica — klasyfikacja pozycji zakupowych wg ryzyka i wartości (auto-kwadrant).
- **[Python]** Wykrywanie duplikatów w master data dostawców — fuzzy match po nazwie/NIP/adresie.
- **[API]** Wzbogacanie danych dostawcy z GUS/KRS — pobór PKD, statusu, kapitału po NIP.
- **[Python]** Walidacja kompletności kartoteki dostawcy — sprawdza brakujące pola (IBAN, kontakt, warunki).
- **[SharePoint]** Formularz onboardingu dostawcy — Power Apps + lista, workflow akceptacji nowego dostawcy.
- **[Python]** Ankieta oceny dostawcy — auto-wysyłka kwartalnej ankiety, zbiór wyników do scoringu.
- **[Power BI]** Analiza koncentracji zakupów — udział TOP dostawców (ryzyko uzależnienia), Pareto.
- **[Python]** Monitoring kondycji finansowej dostawcy — alert przy pogorszeniu scoringu z wywiadowni/API.
- **[Excel]** Baza cenników dostawców z historią — Power Query konsoliduje cenniki, śledzi zmiany w czasie.
- **[Python]** Auto-aktualizacja warunków płatności — synchronizacja terminów z umów do master data.
- **[n8n]** Alert o dostawcy na liście sankcyjnej — sprawdzanie w bazach sankcyjnych przy dodaniu/płatności.

### 1.6 Obsługa maili od dostawców (parsowanie)

- **[Python]** Parser potwierdzeń zamówień z maila — `imaplib` + regex/LLM wyciąga nr PO, ETA, ilości do bazy.
- **[n8n]** Ekstrakcja ETA z maila dostawcy — trigger na maila, LLM node wyciąga datę, aktualizacja zamówienia.
- **[Python]** Klasyfikacja maili zakupowych — auto-kategoria (potwierdzenie/oferta/reklamacja/awizacja).
- **[OCR]** Odczyt potwierdzenia zamówienia z załącznika PDF — mapowanie pozycji na PO.
- **[Power Automate]** Auto-zapis załączników z maili dostawców do SharePoint — segregacja per dostawca.
- **[Python]** Wykrywanie zmiany ceny w potwierdzeniu — porównuje cenę potwierdzoną z zamówioną, alert.
- **[n8n]** Automatyczna odpowiedź na potwierdzenie — po zgodności PO wysyła akceptację, przy rozbieżności eskaluje.
- **[Python]** Ekstrakcja awizacji dostawy z maila — data/godzina/nr auta → kalendarz przyjęć.
- **[Python]** Detekcja opóźnienia z treści maila — słowa kluczowe „delay/opóźnienie" → flaga ryzyka.
- **[Python]** Auto-parsowanie ofert do porównywarki — z maili z ofertami buduje tabelę porównawczą.

### 1.7 Tracking kontenerów, cła, import

- **[API]** Tracking kontenerów po nr BL — odpytanie API armatora/agregatora (np. Searates), status do bazy.
- **[Python]** Monitor ETA statków — codzienny pobór pozycji AIS/harmonogramów, alert o zmianie ETA.
- **[n8n]** Alert „kontener w porcie" — webhook ze statusu → powiadomienie do spedycji/magazynu o awizacji.
- **[Python]** Kalkulator demurrage/detention — liczy dni wolne vs upływające, alert przed naliczeniem opłat.
- **[OCR]** Odczyt dokumentów celnych (SAD/faktura handlowa) — ekstrakcja pozycji, kodów HS, wartości.
- **[Python]** Walidacja kodów HS/CN — sprawdza poprawność kodu taryfowego i stawki cła.
- **[API]** Pobór stawek celnych z TARIC — przelicza cło i VAT importowy per pozycja.
- **[Python]** Tracker dokumentów importowych — checklist kompletności (CIPL, BL, świadectwo pochodzenia, EUR.1).
- **[Excel]** Kalkulator landed cost importu — pełny koszt sprowadzenia z podziałem na pozycje wg wagi/wartości.
- **[n8n]** Powiadomienie agencji celnej — po skompletowaniu dokumentów auto-mail z paczką do odprawy.
- **[Python]** Rozliczenie kosztów frachtu na pozycje — alokacja kosztu transportu proporcjonalnie do wolumenu.
- **[Power BI]** Dashboard statusu importów — mapa/timeline kontenerów w drodze, ETA, ryzyka.
- **[Python]** Alert zbliżającej się granicy free time — przypomnienie o odbiorze kontenera przed opłatami.
- **[OCR]** Ekstrakcja z Certificate of Origin — automatyczne wpisanie do rejestru pochodzenia.
- **[Python]** Rekoncyliacja ilości: zamówienie vs BL vs przyjęcie — trójstronne porównanie dla importu.

### 1.8 Analityka i raportowanie zakupów

- **[Power BI]** Dashboard wydatków (spend analysis) — spend per kategoria/dostawca/miesiąc, drill-down.
- **[Python]** Analiza ABC pozycji zakupowych — klasyfikacja wg wartości rocznej, priorytetyzacja uwagi.
- **[Python]** Raport oszczędności (savings) — porównanie ceny bieżącej z bazową, kwota savings do raportu zarządczego.
- **[Excel]** Pivot spend cube — dynamiczna kostka wydatków z filtrami, odświeżana z bazy.
- **[Python]** Wykrywanie maverick buying — zakupy poza kontraktem/procedurą, lista do audytu.
- **[Power BI]** Analiza cyklu zamówienia (PO cycle time) — czas od zapotrzebowania do dostawy, wąskie gardła.
- **[Python]** Prognoza budżetu zakupowego — ekstrapolacja wydatków vs plan, alert przekroczenia.
- **[Excel]** Raport zgodności z umowami ramowymi — % zakupów realizowanych wg kontraktu.
- **[Python]** Analiza tail spend — identyfikacja rozdrobnionych drobnych zakupów do konsolidacji.
- **[Power BI]** KPI zakupowe — cost savings, PO on time, invoice accuracy, supplier count na jednym pulpicie.

### 1.9 RFQ, e-sourcing, negocjacje

- **[Python]** Generator zapytania ofertowego (RFQ) — z listy pozycji tworzy spersonalizowane RFQ do dostawców.
- **[n8n]** Rozsyłka RFQ do puli dostawców — jeden trigger → maile z terminem odpowiedzi i śledzeniem.
- **[Python]** Porównywarka ofert (bid comparison) — zbiera odpowiedzi, tabela cena/termin/warunki, ranking.
- **[Excel]** Macierz oceny ofert ważona — kryteria z wagami, automatyczny scoring i rekomendacja.
- **[Python]** Przypomnienie o brakującej odpowiedzi na RFQ — ponaglenie dostawców przed deadline.
- **[Python]** Analiza should-cost — modelowanie kosztu wytworzenia jako punkt odniesienia do negocjacji.
- **[Excel]** Kalkulator oszczędności z negocjacji — cena wyjściowa vs wynegocjowana, wpływ roczny.
- **[Python]** Historia cen dostawcy do negocjacji — trend cen z ostatnich lat jako argument.
- **[n8n]** Aukcja elektroniczna (reverse auction) lite — zbiera kolejne oferty w rundach.
- **[Python]** Symulacja scenariuszy alokacji wolumenu — podział między dostawców minimalizujący koszt/ryzyko.

### 1.10 Compliance, ryzyko, zrównoważony rozwój

- **[Python]** Sprawdzanie białej listy VAT (batch) — masowa weryfikacja rachunków dostawców przez API MF.
- **[API]** Kontrola statusu w KRS/CEIDG — monitoring aktywności działalności dostawcy.
- **[Python]** Screening list sankcyjnych — sprawdzanie dostawców/odbiorców w bazach OFAC/UE.
- **[Python]** Monitoring split payment/MPP — flagowanie transakcji objętych mechanizmem.
- **[SharePoint]** Rejestr wymaganych certyfikatów dostawców — ISO/REACH/RoHS z datami ważności.
- **[Python]** Ankieta ESG dostawcy — auto-wysyłka i zbieranie danych środowiskowych/społecznych.
- **[Python]** Kalkulator śladu węglowego dostaw — emisja per transport/pozycja do raportu CSRD.
- **[Python]** Wykrywanie konfliktu interesów — porównanie danych dostawców z pracownikami.
- **[Power BI]** Dashboard ryzyka dostaw — geograficzne, finansowe, koncentracji, jakościowe.
- **[Python]** Audyt trail zmian w zamówieniach — log kto/kiedy/co zmienił w PO.

### 1.11 Master data materiałów i katalog

- **[Python]** Walidacja kompletności kartoteki materiału — brakujące wymiary/wagi/jednostki → raport.
- **[Python]** Deduplikacja indeksów materiałowych — wykrycie tego samego towaru pod różnymi kodami.
- **[Excel]** Katalog produktów z klasyfikacją — auto-przypisanie grup towarowych wg reguł.
- **[Python]** Standaryzacja opisów materiałów — ujednolicenie nazewnictwa i atrybutów.
- **[OCR]** Ekstrakcja danych technicznych z kart katalogowych — do kartoteki materiału.
- **[Python]** Mapowanie kodów dostawcy na indeksy własne — tabela translacji SKU.
- **[Python]** Kontrola spójności jednostek zakupu vs magazynowej — wykrycie błędnych przeliczników.
- **[API]** Wzbogacanie kartoteki o kody GTIN/EAN — pobór z bazy GS1.

### 1.12 Rozliczenia i finanse zakupów

- **[Python]** Prognoza cash flow zobowiązań — kalendarz płatności z faktur do planowania płynności.
- **[Excel]** Zestawienie zobowiązań wg terminów (aging AP) — koszyki wymagalności.
- **[Python]** Wykrywanie faktur do zapłaty z rabatem za wcześniejszą płatność — early payment discount.
- **[Python]** Rekoncyliacja saldo dostawcy vs system — porównanie wyciągu dostawcy z księgami.
- **[Python]** Kontrola limitów zakupowych per centrum kosztów — alert przekroczenia budżetu.
- **[Power BI]** Analiza accruals (rezerw) na dostawy niezafakturowane — GR/IR.
- **[Python]** Auto-alokacja kosztów dodatkowych na pozycje — fracht/cło/ubezpieczenie proporcjonalnie.

### 1.13 Planowanie potrzeb (MRP lite)

- **[Python]** MRP lite z BOM — z zamówień sprzedaży rozwija zapotrzebowanie na komponenty.
- **[Python]** Netting zapotrzebowania — potrzeba minus stan minus zamówienia w drodze.
- **[Excel]** Arkusz planu zakupów rolling 12M — projekcja potrzeb na horyzont.
- **[Python]** Wykrywanie niedoborów w horyzoncie — kiedy zabraknie komponentu do produkcji.
- **[Python]** Sugestia terminu zamówienia wstecz od potrzeby — backward scheduling wg lead time.
- **[Python]** Konsolidacja zapotrzebowań międzyokresowych — łączenie potrzeb w opłacalne partie.
- **[Power BI]** Bilans zaopatrzenia — potrzeby vs pokrycie w czasie, luki.

### 1.14 Komunikacja i obsługa dostawców

- **[SMTP]** Szablonowe potwierdzenia zamówień do dostawcy — auto-mail z PO w załączniku PDF.
- **[n8n]** Portal statusu zamówień dla dostawcy — self-service podglądu stanu PO.
- **[Python]** Auto-ponaglenie o brakujące dokumenty — checklist per dostawa, mail o brakach.
- **[Python]** Podsumowanie miesięczne współpracy do dostawcy — obroty, OTIF, uwagi.
- **[n8n]** Zbieranie potwierdzeń ETA przez formularz — dostawca wpisuje, system aktualizuje.
- **[Python]** Tłumaczenie korespondencji zakupowej (LLM) — obsługa dostawców zagranicznych.

---

## 2. LOGISTYKA MAGAZYNOWA

### 2.1 Stany magazynowe (min/max, alerty)

- **[Python]** Alert stanu minimalnego — codzienny odczyt stanów z SAP, mail z listą pozycji poniżej min.
- **[Python]** Alert przekroczenia max — flaguje nadmierne zapasy (przekroczony poziom maksymalny) do redukcji.
- **[Excel]** Tablica min/max/aktualny z semaforem — kolory zielony/żółty/czerwony wg progu.
- **[n8n]** Webhook „stan zerowy" — gdy pozycja zejdzie do 0 → natychmiastowe powiadomienie do zakupów i sprzedaży.
- **[Python]** Dynamiczne progi min/max — przeliczanie progów wg sezonowości zużycia co miesiąc.
- **[Power BI]** Heatmapa stanów vs progi — wizualizacja pozycji w strefie ryzyka braku/nadmiaru.
- **[Python]** Prognoza dnia wyczerpania zapasu — ekstrapolacja zużycia, data „stock-out" per SKU.
- **[Excel]** Kalkulator zapasu bezpieczeństwa — z odchylenia popytu i lead time, service level.
- **[Python]** Bilans dostępności (ATP) — stan − rezerwacje + zamówienia w drodze = dostępne do obietnicy.
- **[n8n]** Alert rozbieżności stanu systemowego vs fizycznego — po inwentaryzacji cząstkowej.
- **[Python]** Raport pozycji zablokowanych/kwarantanna — lista stanów niedostępnych do sprzedaży.
- **[Power BI]** Wskaźnik pokrycia zapasem (days of supply) — per kategoria, trend.

### 2.2 Zapasy stęchłe, rotacja, przeceny

- **[Python]** Detektor slow-moving/dead stock — pozycje bez rotacji >90/180/365 dni, wartość zamrożona.
- **[Python]** Analiza rotacji zapasów (inventory turnover) — COGS/średni zapas per kategoria.
- **[Excel]** Raport wiekowania zapasu (aging) — koszyki 0-30/31-60/61-90/>90 dni, wartość.
- **[Python]** Alert zbliżającego się terminu przydatności — FEFO, lista partii do priorytetowego wydania.
- **[n8n]** Powiadomienie o przecenie stęchłego towaru — auto-sugestia rabatu do sprzedaży.
- **[Power BI]** Dashboard martwego kapitału — wartość dead stock w czasie, top pozycje.
- **[Python]** Rekomendacja likwidacji/wyprzedaży — pozycje kwalifikujące się do odpisu.
- **[Python]** ABC-XYZ analiza — krzyżowa klasyfikacja wartość × przewidywalność popytu, strategia zapasu.
- **[Excel]** Tracker rezerwy na odpisy zapasu — auto-wyliczenie rezerwy wg polityki wiekowania.

### 2.3 Planowanie dostaw, awizacje, dock scheduling

- **[SharePoint]** Kalendarz awizacji dostaw — lista/kalendarz z oknami czasowymi ramp, rezerwacja slotów.
- **[Power Automate]** Potwierdzenie awizacji dostawcy — formularz → auto-mail z przydzielonym oknem.
- **[Python]** Optymalizator harmonogramu ramp — rozkłada dostawy w oknach unikając kolizji (greedy/OR-Tools).
- **[n8n]** Przypomnienie o awizacji dzień przed — mail/SMS do przewoźnika z oknem i instrukcją.
- **[Excel]** Grafik przyjęć na dobę — wizualny plan ramp godzina po godzinie.
- **[Python]** Wyrównanie obciążenia magazynu — bilansuje przyjęcia/wydania w czasie, alert przeciążenia.
- **[Power BI]** KPI terminowości awizacji — % dostaw w oknie, opóźnienia przewoźników.
- **[n8n]** Auto-slot dla przewoźnika przez formularz web — self-booking okna dostawy.
- **[Python]** Prognoza wolumenu przyjęć — z zamówień w drodze planuje potrzebne zasoby ludzkie.

### 2.4 Paletyzacja, załadunek, przestrzeń

- **[Python]** Kalkulator paletyzacji — ile kartonów na paletę EU, warstwy, wykorzystanie py3dbp.
- **[Python]** Optymalizacja załadunku kontenera/auta — bin packing 3D, plan rozmieszczenia.
- **[Excel]** Kalkulator liczby palet na wysyłkę — z wymiarów i wagi pozycji.
- **[Python]** Wyliczenie ładowności vs limit osi — kontrola przekroczenia DMC pojazdu.
- **[Python]** Generator etykiety palety SSCC — kod GS1-128 + PDF etykiety do druku.
- **[Power BI]** Wskaźnik wykorzystania przestrzeni magazynu — % zajętości lokalizacji/stref.
- **[Python]** Prognoza zajętości magazynu — projekcja wolnych miejsc na podstawie przyjęć/wydań.
- **[Python]** Sugestia lokalizacji składowania (slotting) — ABC-based, szybkorotujące bliżej wydania.
- **[Excel]** Mapa zajętości regałów — warunkowe formatowanie siatki lokalizacji.

### 2.5 Inwentaryzacja

- **[Python]** Generator arkuszy spisowych — losowa próbka pozycji do liczenia cyklicznego (cycle count).
- **[Python]** Rekoncyliacja spisu z systemem — import wyników skanowania, raport różnic ilość/wartość.
- **[Excel]** Arkusz różnic inwentaryzacyjnych — auto-obliczenie odchyleń i wartości korekty.
- **[n8n]** Workflow zatwierdzania korekt inwentaryzacyjnych — różnica > próg → approval.
- **[Python]** Harmonogram cyklicznego liczenia — plan cycle count wg klasy ABC (A częściej).
- **[Power BI]** Dokładność inwentaryzacji (IRA) — % zgodności rekordów, trend, per strefa.
- **[Python]** Wykrywanie systematycznych błędów lokalizacji — powtarzające się różnice w tych samych miejscach.
- **[OCR]** Odczyt spisu z ręcznych arkuszy — digitalizacja wyników liczenia papierowego.

### 2.6 Etykiety, skanery, identyfikacja

- **[Python]** Masowy generator etykiet kodów kreskowych — Code128/QR z listy SKU do PDF (reportlab).
- **[Python]** Generator etykiet GS1 — struktura AI (GTIN, partia, data, ilość) w kodzie DataMatrix.
- **[n8n]** Druk etykiety po skanie — webhook ze skanera → generuj i wyślij do drukarki ZPL.
- **[Python]** Walidacja poprawności kodu EAN — sprawdzenie cyfry kontrolnej przy wprowadzaniu.
- **[Excel]** Szablon etykiet do korespondencji seryjnej — mail merge z listy wysyłek.
- **[Python]** Parser logów skanera — analiza czasów skanowania, wydajność operatorów.
- **[Python]** Konwerter ZPL/EPL — generowanie kodu dla drukarek Zebra z danych pozycji.
- **[API]** Integracja skanera przez REST — endpoint przyjmuje skan i zwraca dane pozycji/lokalizacji.

### 2.7 Kolejkowanie przyjęć/wydań, procesy WMS

- **[Python]** Kolejka zadań kompletacji (picking) — priorytetyzacja wg pilności wysyłki, kolejność tras.
- **[Python]** Optymalizacja trasy pickera — najkrótsza ścieżka po lokalizacjach (TSP heurystyka).
- **[n8n]** Auto-przydział zadania magazynierowi — dispatch zadania do wolnego operatora.
- **[Python]** Konsolidacja zamówień do jednej trasy (batch picking) — grupuje pozycje po lokalizacji.
- **[Power BI]** Monitor kolejki wydań w czasie rzeczywistym — liczba oczekujących, SLA.
- **[Python]** Wykrywanie utknięcia zlecenia — zlecenie bez postępu > X h → eskalacja.
- **[Python]** Balansowanie obciążenia stanowisk pakowania — rozdział zleceń wg przepustowości.
- **[Excel]** Tablica statusu zleceń wydania — kanban przyjęte/w toku/spakowane/wysłane.

### 2.8 KPI magazynu i raportowanie

- **[Power BI]** Dashboard KPI magazynu — przyjęcia, wydania, dokładność, wykorzystanie, na jednym pulpicie.
- **[Python]** Wskaźnik produktywności (linii/godzinę) — z logów WMS per zmiana/operator.
- **[Python]** Order fulfillment cycle time — czas od zlecenia do wysyłki, percentyle.
- **[Excel]** Raport dzienny operacji magazynu — auto-generacja o 6:00 z podsumowaniem doby.
- **[Power BI]** Wskaźnik perfect order — % zamówień bez błędów (ilość, czas, dokumenty, uszkodzenia).
- **[Python]** Analiza szczytów obciążenia — godziny/dni peak, planowanie zasobów.
- **[Python]** Koszt obsługi jednostki (cost per unit handled) — z kosztów i wolumenu.
- **[Power BI]** Trend zwrotów i uszkodzeń — źródła, przyczyny, koszt.

### 2.9 Integracja z SAP EWM / systemami

- **[Python]** Eksport stanów z SAP do hurtowni — cykliczny odczyt (RFC/OData) do bazy analitycznej.
- **[API]** Integracja OData SAP EWM — pobór zleceń magazynowych, kolejek, stanów przez REST.
- **[Python]** Synchronizacja master data materiałów SAP↔Excel — dwukierunkowa aktualizacja atrybutów.
- **[n8n]** Most SAP → Teams — status zleceń EWM (kolejki) publikowany na kanał.
- **[Python]** Rekoncyliacja SAP vs WMS zewnętrzny — porównanie stanów między systemami, raport driftu.
- **[Python]** Parser plików IDoc — ekstrakcja danych z IDoc (WHSCON, DELVRY) do analizy.
- **[Excel]** Power Query po tabelach SAP (extract) — bezpośrednie ładowanie wyeksportowanych tabel.
- **[Python]** Automatyzacja transakcji SAP GUI (scripting) — masowe księgowanie ruchów przez SAP GUI Scripting.

### 2.10 Zwroty, cross-docking, przepływy specjalne

- **[Python]** Kolejka obsługi zwrotów — priorytetyzacja i status zwrotów od klientów.
- **[Python]** Kandydaci do cross-dockingu — pozycje z zamówieniem klienta pasujące do przyjęcia (bez składowania).
- **[n8n]** Alert dopasowania przyjęcie↔zamówienie — sygnał do przeładunku bezpośredniego.
- **[Python]** Rekomendacja put-away — sugeruje strefę składowania wg cech towaru (waga/rotacja/warunki).
- **[Python]** Obsługa kompletacji zestawów (kitting) — lista komponentów per zestaw, kontrola dostępności.
- **[Excel]** Tablica statusu zwrotów RMA — etapy od zgłoszenia do rozliczenia.
- **[Python]** Analiza przyczyn zwrotów — kategoryzacja i trend do działań korygujących.

### 2.11 Chłodnia / warunki specjalne / bezpieczeństwo

- **[Python]** Monitoring temperatury (IoT) — odczyt czujników, alert przy przekroczeniu zakresu.
- **[n8n]** Alert przekroczenia temperatury chłodni — natychmiastowe powiadomienie + log incydentu.
- **[Python]** Raport łańcucha chłodniczego — ciągłość temperatury per partia do audytu.
- **[Python]** Rejestr towarów niebezpiecznych (ADR) — kontrola zgodności składowania i sąsiedztwa.
- **[Python]** Alert kończącej się przydatności partii FEFO — priorytet wydania.
- **[Power BI]** Dashboard warunków magazynowych — temperatura/wilgotność stref w czasie.

### 2.12 Zasoby ludzkie i wydajność

- **[Python]** Planowanie obsady zmian — dopasowanie liczby operatorów do prognozy wolumenu.
- **[Excel]** Grafik pracy magazynu — rozpiska zmian z pokryciem stanowisk.
- **[Python]** Analiza wydajności operatorów — linie/godzinę, ranking, wykrywanie odstępstw.
- **[Power BI]** Dashboard produktywności zespołu — trend, per zmiana, per proces.
- **[Python]** Wykrywanie wąskich gardeł procesu — etap z najdłuższym czasem oczekiwania.
- **[Python]** Kalkulator zapotrzebowania na sprzęt (wózki) — z wolumenu i cykli.

### 2.13 Transport i wysyłki (wychodzące)

- **[Python]** Konsolidacja wysyłek na trasę — grupuje zlecenia wg kierunku/terminu.
- **[Python]** Optymalizacja doboru przewoźnika — najtańszy spełniający SLA per przesyłka.
- **[API]** Tracking przesyłek kurierskich — status paczek przez API kuriera, alert opóźnień.
- **[Python]** Generator listu przewozowego/CMR — auto z danych wysyłki do PDF.
- **[n8n]** Auto-awizacja wysyłki do klienta — mail z nr śledzenia po nadaniu.
- **[Python]** Kalkulator kosztu frachtu — wg wagi/objętości/strefy, porównanie taryf.
- **[Power BI]** KPI transportu wychodzącego — koszt/kg, terminowość, uszkodzenia.
- **[Python]** Wykrywanie nadwymiarowych/kosztownych przesyłek — do optymalizacji pakowania.

### 2.14 Kontrola jakości (QC)

- **[Python]** Plan kontroli jakości przyjęć — próbkowanie wg AQL, lista pozycji do sprawdzenia.
- **[SharePoint]** Rejestr niezgodności jakościowych — lista + workflow blokady/zwolnienia partii.
- **[Python]** Blokada partii przy przekroczeniu wad — auto-status kwarantanna.
- **[Power BI]** Dashboard jakości dostaw — % wadliwych, top wadliwe pozycje/dostawcy.
- **[Python]** Powiązanie reklamacji jakościowej z dostawcą — feedback do scoringu.
- **[OCR]** Odczyt certyfikatów jakości/atestów — CoA do rejestru partii.
- **[Python]** Trend defektów w czasie — SPC lite, wykrywanie pogorszenia jakości.

### 2.15 Opakowania i materiały pomocnicze

- **[Python]** Zużycie materiałów opakowaniowych vs wysyłki — norma vs rzeczywistość.
- **[Python]** Reorder point dla opakowań/palet — nie zabraknie folii/kartonów/palet.
- **[Excel]** Kalkulator zapotrzebowania na palety na dzień — z planu wysyłek.
- **[Python]** Rejestr obrotu paletowego (paleta EU) — saldo z dostawcami/klientami.
- **[Python]** Alert deficytu palet — gdy saldo poniżej progu operacyjnego.

### 2.16 Więcej KPI i analiz magazynu

- **[Power BI]** Wskaźnik dokładności kompletacji (pick accuracy) — błędy/1000 linii.
- **[Python]** Analiza dead-zone lokalizacji — miejsca nieużywane do reorganizacji.
- **[Python]** Wskaźnik dwell time przyjęć — czas od dostawy do dostępności w systemie.
- **[Power BI]** Koszt magazynowania na SKU — obciążenie wolno rotujących.
- **[Python]** Analiza korelacji: opóźnienie dostawy → brak w magazynie — źródła stock-out.
- **[Python]** Symulacja pojemności przy wzroście wolumenu — kiedy zabraknie miejsca.
- **[Excel]** Bilans przepływu magazynu (in/out/saldo) — dobowy z alertem anomalii.

### 2.17 Bezpieczeństwo i BHP magazynu

- **[SharePoint]** Rejestr zdarzeń BHP — lista incydentów z workflow działań korygujących.
- **[Python]** Harmonogram przeglądów sprzętu — alert o terminach UDT wózków/regałów.
- **[n8n]** Przypomnienie o szkoleniach BHP — trigger na wygasające uprawnienia.
- **[Python]** Analiza near-miss — trend zdarzeń potencjalnie wypadkowych.
- **[Power BI]** Dashboard BHP — wskaźniki wypadkowości, dni bez wypadku.

### 2.18 Śledzenie i identyfikowalność (traceability)

- **[Python]** Genealogia partii — powiązanie partii przyjęcia z wydaniami (recall readiness).
- **[Python]** Symulacja wycofania partii (recall) — kto dostał daną partię, w minutę.
- **[Python]** Śledzenie numerów seryjnych — rejestr serial→klient→data.
- **[OCR]** Odczyt numerów partii z etykiet przyjęcia — do systemu traceability.
- **[Python]** Raport identyfikowalności do audytu — pełna ścieżka partii na żądanie.

### 2.19 Integracje i wymiana danych logistycznych

- **[API]** EDI z przewoźnikami (status, awizacje) — wymiana komunikatów bez maili.
- **[Python]** Parser plików EDIFACT/DESADV — awizacje dostaw do systemu.
- **[n8n]** Most WMS↔ERP — synchronizacja statusów zleceń w obie strony.
- **[Python]** Eksport danych do platformy TMS — zlecenia transportowe automatycznie.
- **[API]** Integracja z systemem operatora logistycznego (3PL) — stany i ruchy przez REST.

### 2.20 Prognozy i planowanie zapasów

- **[Python]** Prognoza stanów na horyzont — projekcja z przyjęć/wydań, alert luk.
- **[Python]** Optymalizacja poziomów zapasu (multi-echelon) — bilans kosztu vs dostępność.
- **[Python]** Klasyfikacja pozycji wg zmienności popytu (XYZ) — strategia buforów.
- **[Power BI]** Symulator wpływu lead time na zapas bezpieczeństwa — scenariusze.
- **[Python]** Wykrywanie sezonowych wzorców zużycia — dostosowanie progów.

---

## 3. SPRZEDAŻ

### 3.1 Raporty sprzedaży

- **[Power BI]** Dashboard sprzedaży — obrót/marża/ilość per produkt/klient/region, drill-down, trend.
- **[Python]** Raport dzienny sprzedaży na mail — auto-generacja o 7:00 z podsumowaniem poprzedniej doby.
- **[Excel]** Pivot sprzedaży z Power Query — kostka odświeżana z bazy, filtry rok/miesiąc/kategoria.
- **[Python]** Porównanie sprzedaży r/r i m/m — automatyczne wskaźniki dynamiki z komentarzem tekstowym.
- **[Power BI]** Analiza realizacji planu sprzedaży — plan vs wykonanie, % realizacji, projekcja końca miesiąca.
- **[Python]** Ranking bestsellerów i maruderów — TOP/BOTTOM produkty wg obrotu i marży.
- **[Excel]** Raport sprzedaży per handlowiec — zestawienie wyników zespołu z celami.
- **[Python]** Analiza sezonowości sprzedaży — dekompozycja szeregu, wzorce miesięczne/tygodniowe.
- **[Power BI]** Mapa sprzedaży geograficzna — obrót per województwo/kraj na mapie.
- **[Python]** Kohortowa analiza klientów — sprzedaż wg cohort pozyskania, retencja.
- **[Excel]** Raport rozliczenia rabatów i bonusów — auto-wyliczenie należnych bonusów per klient.
- **[Python]** Prognoza sprzedaży (forecast) — model szeregów czasowych per SKU/klient, przedział ufności.

### 3.2 CRM lite, lejek, follow-up

- **[SharePoint]** Lista CRM leadów — lista jako baza z etapami lejka, właściciel, wartość, next step.
- **[Power Automate]** Przypomnienie o follow-up — jeśli brak kontaktu z leadem > X dni → zadanie/mail do handlowca.
- **[Python]** Scoring leadów — punktacja wg wielkości/branży/zaangażowania, priorytetyzacja.
- **[n8n]** Auto-zapis leada z formularza web — webhook z formularza → wpis do CRM + powiadomienie.
- **[Power BI]** Lejek sprzedaży (funnel) — konwersja etapów, wartość pipeline, wąskie gardła.
- **[Python]** Wykrywanie stagnacji szansy — okazje bez ruchu w lejku > X dni → flaga.
- **[Power Automate]** Sekwencja nurturingu mailowego — automatyczna kadencja maili do leada.
- **[Excel]** Tablica pipeline z ważoną wartością — wartość × prawdopodobieństwo etapu.
- **[Python]** Prognoza domknięć (win probability) — model na historycznych danych sprzedaży.
- **[n8n]** Alert o „gorącym" leadzie — wielokrotne wejścia na ofertę → natychmiastowe powiadomienie.

### 3.3 Oferty, proformy, potwierdzenia

- **[Python]** Generator oferty PDF — z szablonu + dane klienta/pozycje → gotowa oferta (jinja2+weasyprint).
- **[Python]** Generator proformy/faktury pro forma — auto z zamówienia, numeracja, wysyłka mailem.
- **[Excel]** Kalkulator oferty z marżą — wpis kosztu → auto cena wg polityki marż, warunki.
- **[Power Automate]** Workflow zatwierdzania oferty rabatowej — rabat > próg → approval przełożonego.
- **[n8n]** Auto-potwierdzenie zamówienia — po wpłynięciu zamówienia → mail z potwierdzeniem i terminem.
- **[Python]** Wersjonowanie ofert — śledzenie kolejnych wersji oferty do klienta, historia zmian.
- **[Python]** Masowa personalizacja ofert — mail merge cenowy per klient z indywidualnymi warunkami.
- **[OCR]** Odczyt zamówienia klienta z PDF/skanu — ekstrakcja pozycji do systemu sprzedaży.
- **[Python]** Walidacja zamówienia klienta — sprawdza dostępność, cenę, limit kredytowy przed potwierdzeniem.
- **[Power Automate]** Auto-wysyłka potwierdzenia z terminem realizacji — z ATP/planowania.

### 3.4 Marże, ceny, analiza

- **[Python]** Analiza marż per transakcja — wykrycie sprzedaży poniżej progu marży, alert.
- **[Power BI]** Dashboard marżowości — marża brutto per produkt/klient/kanał, waterfall.
- **[Excel]** Symulator cennika — wpływ zmiany ceny na marżę i wolumen (elastyczność).
- **[Python]** Wykrywanie erozji cen — spadek średniej ceny realizacji w czasie per produkt.
- **[Python]** Kontrola zgodności cen z cennikiem — sprzedaż poza cennikiem → raport odchyleń.
- **[Power BI]** Analiza rentowności klienta — cost-to-serve vs marża, klienci nierentowni.
- **[Python]** Rekomendacja optymalnej ceny — na bazie historii i elastyczności popytu.
- **[Excel]** Kalkulator break-even zamówienia — minimalna cena/wolumen pokrywający koszty.

### 3.5 Segmentacja klientów i alerty

- **[Python]** Segmentacja RFM — Recency/Frequency/Monetary, klasy klientów, akcje per segment.
- **[Python]** Alert spadku zamówień klienta — klient zamawiający regularnie milczy > oczekiwany cykl → flaga churn.
- **[n8n]** Powiadomienie o utraconym kliencie — brak zamówień X dni → zadanie retencyjne dla handlowca.
- **[Power BI]** Analiza churn i retencji — wskaźniki utraty, wartość zagrożona.
- **[Python]** Wykrywanie cross-sell/up-sell — koszyki produktowe, rekomendacje uzupełnień.
- **[Python]** Predykcja churn (model) — klasyfikacja klientów zagrożonych odejściem.
- **[Excel]** Macierz klient × produkt — luki w portfelu zakupowym klienta (białe plamy).
- **[Python]** Alert nietypowego zamówienia — nagły duży/mały wolumen vs historia klienta.
- **[Power BI]** Analiza koncentracji sprzedaży — udział TOP klientów, ryzyko zależności.
- **[n8n]** Auto-życzenia i kampanie okolicznościowe — trigger na rocznicę współpracy/urodziny kontaktu.

### 3.6 Obsługa posprzedażowa

- **[n8n]** Ankieta satysfakcji po dostawie — auto-mail z NPS X dni po wysyłce.
- **[Python]** Analiza zwrotów i reklamacji — trendy przyczyn, produkty problematyczne.
- **[SharePoint]** Rejestr reklamacji z workflow — lista + Power Automate routing do obsługi.
- **[Power Automate]** Eskalacja niezałatwionej reklamacji — SLA > próg → eskalacja.
- **[Python]** Auto-generacja dokumentu RMA — z formularza zwrotu → numer i etykieta zwrotna.
- **[Power BI]** Dashboard obsługi klienta — czas reakcji, liczba zgłoszeń, satysfakcja.

### 3.7 E-commerce i kanały online

- **[API]** Synchronizacja stanów do sklepu/marketplace — auto-update dostępności przez API.
- **[Python]** Import zamówień z marketplace do ERP — pobór i mapowanie zamówień Allegro/Amazon.
- **[n8n]** Alert nowego zamówienia online — powiadomienie + wpis do kolejki realizacji.
- **[Python]** Aktualizacja cen w kanałach — masowa zmiana cen wg reguł marży/konkurencji.
- **[Python]** Monitoring opinii/ocen produktów — agregacja recenzji, alert negatywnych.
- **[Excel]** Raport sprzedaży per kanał — porównanie B2B/e-commerce/marketplace.
- **[Python]** Wykrywanie braków blokujących sprzedaż online — pozycje z ruchem ale zerowym stanem.

### 3.8 Marketing i kampanie

- **[n8n]** Kampania mailowa segmentowa — wysyłka oferty do wybranego segmentu RFM.
- **[Python]** Generator newslettera z bestsellerami — auto-dobór produktów do promocji.
- **[Power BI]** Analiza skuteczności promocji — sprzedaż w okresie akcji vs baseline.
- **[Python]** Rekomendacje produktowe (market basket) — reguły asocjacyjne do cross-sell.
- **[n8n]** Reaktywacja uśpionych klientów — automatyczna kampania win-back.
- **[Python]** A/B test ofert — porównanie konwersji wariantów.

### 3.9 Prognozy i planowanie sprzedaży

- **[Python]** Prognoza popytu per SKU — model szeregów czasowych zasilający zakupy/produkcję.
- **[Python]** Konsensus S&OP — łączenie prognozy statystycznej z korektą handlowców.
- **[Excel]** Arkusz planowania targetów — rozbicie celu rocznego na miesiące/handlowców.
- **[Power BI]** Prognoza vs realizacja z alertem odchylenia — bieżąca kontrola planu.
- **[Python]** Wykrywanie anomalii sprzedaży — nietypowe skoki/spadki do wyjaśnienia.
- **[Python]** Symulacja wpływu promocji na popyt — uplift modeling.

### 3.10 Rozliczenia i windykacja sprzedaży

- **[Python]** Aging należności (AR) — koszyki wymagalności per klient, wartość zagrożona.
- **[n8n]** Automatyczne monity o płatność — sekwencja przypomnień przed i po terminie.
- **[Python]** Alert przekroczenia limitu kredytowego — blokada/flaga przy nowym zamówieniu.
- **[Python]** Scoring wiarygodności płatniczej klienta — z historii terminowości.
- **[Excel]** Zestawienie DSO per klient — dni ściągania należności, trend.
- **[Python]** Auto-generacja wezwania do zapłaty — z rejestru przeterminowanych.
- **[Power BI]** Dashboard windykacji — przeterminowane, odzyskane, prognoza wpływów.

### 3.11 Dokumenty i obieg sprzedażowy

- **[Python]** Auto-generacja faktury sprzedaży — z zamówienia, numeracja, wysyłka.
- **[OCR]** Odczyt zamówienia klienta z maila/faksu — do systemu bez przepisywania.
- **[Python]** Kompletacja dokumentów wysyłkowych — WZ + faktura + specyfikacja w paczce PDF.
- **[Power Automate]** Obieg akceptacji warunków handlowych — nietypowe warunki → approval.
- **[SharePoint]** Repozytorium umów handlowych z alertami — daty, rabaty, wolumeny minimalne.
- **[Python]** Kontrola realizacji zobowiązań umownych — minimalne wolumeny/rabaty progowe.

### 3.12 Analityka klienta i produktu

- **[Python]** Analiza koszyka zakupowego klienta — struktura i zmiana w czasie.
- **[Python]** Wskaźnik share of wallet — udział w zakupach klienta vs potencjał.
- **[Power BI]** Analiza cyklu życia produktu — sprzedaż od wprowadzenia do wycofania.
- **[Python]** Wykrywanie kanibalizacji produktów — nowy produkt zjada sprzedaż innego.
- **[Python]** Analiza elastyczności cenowej — reakcja wolumenu na zmianę ceny.
- **[Excel]** Ranking rentowności produktów — marża × wolumen, macierz decyzyjna.
- **[Python]** Prognoza wartości życiowej klienta (CLV) — priorytetyzacja obsługi.

### 3.13 Automatyzacja pracy handlowca

- **[Python]** Auto-brief przed spotkaniem z klientem — historia, otwarte kwestie, sugestie.
- **[n8n]** Powiadomienie o wygasającej ofercie — przypomnienie o domknięciu.
- **[Power Automate]** Auto-zapis notatek ze spotkań do CRM — z formularza mobilnego.
- **[Python]** Sugestia następnej akcji (next best action) — na bazie etapu i historii.
- **[Excel]** Kalkulator prowizji handlowca — auto z realizacji celów.
- **[n8n]** Dzienny plan wizyt handlowca — priorytety klientów na dziś.

### 3.14 Ceny i cenniki

- **[Python]** Masowa aktualizacja cennika wg reguł — koszt + narzut per grupa.
- **[Excel]** Generator cennika PDF per klient — z indywidualnymi rabatami.
- **[Python]** Kontrola spójności cen między kanałami — brak konfliktów B2B/online.
- **[n8n]** Powiadomienie klientów o zmianie cennika — z wyprzedzeniem umownym.
- **[Python]** Historia cen realizacji per klient — do negocjacji i audytu.
- **[Python]** Wykrywanie cen odstających od polityki — sprzedaż z nietypowym rabatem.

### 3.15 Zamówienia i potwierdzenia (sprzedażowe)

- **[Python]** Walidacja MOQ i wielokrotności opakowania — korekta zamówienia klienta.
- **[n8n]** Auto-potwierdzenie z ATP i terminem — natychmiast po zamówieniu.
- **[Python]** Wykrywanie zamówień do backorder — pozycje bez pokrycia, obsługa.
- **[Python]** Priorytetyzacja alokacji przy niedoborze — kto dostanie towar wg reguł.
- **[Excel]** Rejestr zamówień otwartych — status realizacji, alert opóźnień.
- **[Python]** Powiadomienie o gotowości do wysyłki — trigger do klienta i logistyki.

### 3.16 KPI i cele sprzedaży

- **[Power BI]** Realizacja celu w czasie rzeczywistym — gauge per handlowiec/zespół.
- **[Python]** Alert zagrożenia planu miesięcznego — projekcja poniżej celu → sygnał.
- **[Excel]** Tablica wyników sprzedaży (leaderboard) — motywacyjny ranking zespołu.
- **[Python]** Rozkład sprzedaży w miesiącu (linearity) — wykrycie kumulacji na koniec.
- **[Power BI]** Analiza win/loss ofert — wskaźnik skuteczności i przyczyny przegranych.
- **[Python]** Wskaźnik średniej wartości zamówienia (AOV) — trend per segment.

### 3.17 Obsługa zapytań i leadów przychodzących

- **[n8n]** Auto-odpowiedź na zapytanie ofertowe — potwierdzenie + termin przygotowania oferty.
- **[Python]** Klasyfikacja zapytań przychodzących (LLM) — routing do właściwego handlowca.
- **[Python]** Ekstrakcja danych z zapytania klienta — pozycje/ilości do wstępnej wyceny.
- **[Power Automate]** SLA odpowiedzi na zapytanie — alert gdy zapytanie czeka za długo.
- **[Python]** Auto-wycena prostych zapytań — z cennika bez udziału handlowca.

---

## 4. PRZEKROJOWE — raportowanie, alerty, integracje danych

### 4.1 Dashboardy i raportowanie

- **[Power BI]** Jeden pulpit zarządczy (zakupy+magazyn+sprzedaż) — KPI całej firmy z jednego źródła.
- **[Python]** Auto-generacja raportu PDF — cotygodniowy raport z wykresami (matplotlib) i wysyłka.
- **[Excel]** Raport samoodświeżający Power Query — otwarcie pliku odświeża dane z bazy/API.
- **[Power BI]** Subskrypcja raportu na mail — harmonogram wysyłki snapshotu do odbiorców.
- **[Python]** Dashboard web Streamlit — interaktywny pulpit KPI dla zespołu bez licencji BI.
- **[Power BI]** Alerty progowe w usłudze — powiadomienie gdy KPI przekroczy próg.
- **[Python]** Raport wyjątków (exception report) — tylko odchylenia wymagające uwagi, nie cała tabela.
- **[Excel]** Cockpit KPI z sparklinami — mini-wykresy trendów obok liczb.

### 4.2 ETL i integracja danych

- **[Python]** ETL Excel→baza — pandas ładuje arkusze do SQL, walidacja schematu, log strat.
- **[Python]** Pipeline SharePoint→DB — pobór plików z biblioteki (Graph API), parsowanie, ładowanie.
- **[n8n]** Synchronizacja arkusz↔baza↔CRM — orkiestracja przepływu danych między systemami.
- **[Excel]** Power Query jako mini-ETL — łączenie, czyszczenie, przekształcanie z wielu źródeł.
- **[Python]** Konwerter formatów (xlsx/csv/json/parquet) — uniwersalny transformer plików.
- **[API]** Warstwa integracyjna REST — jeden endpoint agregujący dane z SAP/CRM/WMS.
- **[Python]** Inkrementalny load (tylko zmiany) — ładowanie delta zamiast pełnego, po timestampie.
- **[n8n]** Harmonogram ETL nocny — cron uruchamia pipeline, raport statusu rano.
- **[Python]** Walidacja jakości danych (data quality) — reguły kompletności/poprawności, raport naruszeń.
- **[Python]** Rekoncyliacja między źródłami — porównanie sum kontrolnych systemów.

### 4.3 Powiadomienia i alerty

- **[n8n]** Centrum alertów na Teams — jeden kanał zbierający wszystkie krytyczne zdarzenia.
- **[Python]** Wysyłka SMS przy krytycznym zdarzeniu — Twilio przy awarii/braku krytycznej pozycji.
- **[Power Automate]** Adaptive Card w Teams z akcjami — approve/reject bezpośrednio w powiadomieniu.
- **[Python]** Digest dzienny zamiast spamu — agregacja alertów w jeden mail o stałej porze.
- **[SMTP]** Silnik mailowy z szablonami — parametryzowane maile HTML z jinja2.
- **[n8n]** Deduplikacja alertów — nie wysyłaj tego samego alertu dwa razy w oknie czasowym.
- **[Python]** Eskalacja wielopoziomowa — brak reakcji → kolejny poziom odbiorców.
- **[Power Automate]** Powiadomienie push do aplikacji mobilnej — dla pracowników w terenie.

### 4.4 Backup, harmonogramy, higiena

- **[Python]** Backup krytycznych arkuszy — kopia z timestampem do archiwum, rotacja starych.
- **[Python]** Scheduler zadań (schedule/APScheduler) — orkiestracja cyklicznych skryptów.
- **[n8n]** Harmonogram workflowów z retry — ponawianie przy błędzie, alert po X próbach.
- **[Python]** Wersjonowanie plików wynikowych — snapshot raportów per data w strukturze folderów.
- **[SharePoint]** Auto-archiwizacja starych dokumentów — flow przenosi pliki > X mies. do archiwum.
- **[Python]** Monitor wolnego miejsca/rozmiaru plików — alert gdy arkusz/baza rośnie nadmiernie.
- **[Python]** Health-check integracji — codzienny test dostępności API/źródeł, raport statusu.

### 4.5 OCR i przetwarzanie dokumentów

- **[OCR]** Uniwersalny ekstraktor dokumentów — Tesseract/Azure/LLM → strukturalne pola do JSON.
- **[OCR]** Klasyfikator typu dokumentu — rozpoznaje czy to faktura/WZ/CMR/oferta, routing.
- **[OCR]** Odczyt tabel z PDF — camelot/tabula → DataFrame z pozycjami.
- **[Python]** Post-korekta OCR słownikiem — poprawa błędów rozpoznania wg słownika pozycji.
- **[OCR]** Ekstrakcja z CMR/listu przewozowego — dane transportu do rejestru.
- **[n8n]** Pipeline dokument→dane→system — skan → OCR → walidacja → wpis, bez ręcznego przepisywania.
- **[OCR]** Odczyt WZ dostawcy — dopasowanie do przyjęcia magazynowego.

### 4.6 Czyszczenie i deduplikacja danych

- **[Python]** Deduplikacja rekordów — fuzzy match (rapidfuzz) po nazwie/adresie/NIP.
- **[Python]** Normalizacja danych adresowych — ujednolicenie formatu ulic/kodów/miast.
- **[Excel]** Reguły czyszczenia w Power Query — trim/proper/replace wielokrotnie użyte.
- **[Python]** Standaryzacja jednostek miary — konwersja szt/kg/palet do wspólnej bazy.
- **[Python]** Wykrywanie i naprawa braków — imputacja/flagowanie pustych krytycznych pól.
- **[Python]** Walidacja NIP/IBAN/EAN — reguły cyfr kontrolnych, raport błędnych.
- **[Python]** Kanonizacja nazw produktów/klientów — mapowanie wariantów zapisu na kanoniczny.

### 4.7 Bezpieczeństwo, dostęp, audyt

- **[Python]** Rotacja i przechowywanie sekretów — klucze API w vault/.env, nie w kodzie.
- **[Python]** Log audytowy zmian danych — kto/kiedy/co, zapis do niezmiennego rejestru.
- **[Power Automate]** Alert o nietypowym dostępie do pliku — powiadomienie o pobraniu wrażliwego dokumentu.
- **[Python]** Maskowanie danych wrażliwych w raportach — anonimizacja przed dystrybucją.
- **[SharePoint]** Uprawnienia per lista/biblioteka — kontrola dostępu do danych działów.
- **[Python]** Weryfikacja integralności plików (hash) — wykrycie modyfikacji krytycznych danych.

### 4.8 Chatboty i asystenci danych

- **[Python]** Asystent Q&A nad danymi (LLM + SQL) — pytanie w języku naturalnym → zapytanie → odpowiedź.
- **[n8n]** Bot Teams odpytujący stany/zamówienia — komenda → dane z systemu w czacie.
- **[Python]** Auto-podsumowanie raportu przez LLM — komentarz tekstowy do liczb dla zarządu.
- **[Python]** Klasyfikacja i routing zgłoszeń mailowych — LLM kieruje maila do właściwego działu.
- **[n8n]** Bot FAQ dla dostawców/klientów — automatyczne odpowiedzi na typowe pytania.

### 4.9 Monitorowanie i niezawodność

- **[Python]** Watchdog integracji — cykliczny ping źródeł, alert gdy API/plik niedostępny.
- **[n8n]** Dead man's switch — brak sygnału z pipeline → alert, że coś przestało działać.
- **[Python]** Raport SLA integracji — czas odpowiedzi/dostępność źródeł danych.
- **[Python]** Kolejka z ponawianiem (retry queue) — nieudane operacje wracają do przetworzenia.
- **[Power BI]** Monitor świeżości danych — kiedy ostatnio odświeżono każde źródło.

### 4.10 Współpraca i przepływ pracy

- **[Power Automate]** Auto-tworzenie zadań w Planner/To Do — z alertów/wyjątków dla właściciela.
- **[n8n]** Synchronizacja kalendarzy zdarzeń operacyjnych — dostawy/wysyłki do wspólnego kalendarza.
- **[Python]** Generator agendy spotkania operacyjnego — auto-zestawienie otwartych kwestii.
- **[SharePoint]** Tablica zadań działu (kanban) — lista z widokiem statusów.
- **[Power Automate]** Eskalacja przeterminowanych zadań — brak zamknięcia → przełożony.
- **[n8n]** Digest tygodniowy dla zarządu — agregacja KPI wszystkich obszarów w jeden mail.

### 4.11 Migracja i konsolidacja plików

- **[Python]** Masowa konwersja starych xls→xlsx/csv — porządkowanie archiwum.
- **[Python]** Scalanie wielu arkuszy w jeden zbiór — z kontrolą spójności kolumn.
- **[Python]** Rozbijanie dużego arkusza na pliki per klient/dostawca — dystrybucja raportów.
- **[Python]** Ekstrakcja danych z zagnieżdżonych folderów — rekurencyjne zbieranie plików.
- **[Excel]** Import danych z PDF (Get Data from PDF) — bez zewnętrznych narzędzi.

### 4.12 Dokumentacja i wiedza

- **[Python]** Auto-generacja dokumentacji procesu z logów — ślad wykonanych kroków.
- **[SharePoint]** Baza wiedzy procedur (wiki) — instrukcje z wyszukiwaniem.
- **[Python]** Generator changelogu zmian w danych referencyjnych — co się zmieniło w cenniku/master.
- **[n8n]** Auto-powiadomienie o zmianie procedury — informacja do zespołu.

### 4.13 Testy i walidacja automatyzacji

- **[Python]** Testy regresji reguł biznesowych — pytest na progach/marżach/reorder.
- **[Python]** Sandbox dla nowych flow — środowisko testowe na danych syntetycznych.
- **[Python]** Walidacja wyników automatyzacji vs ręczne — okres równoległy przed cutover.
- **[Python]** Monitoring dryfu danych — alert gdy rozkład danych się zmienia (psuje modele).

### 4.14 Raporty regulacyjne i zewnętrzne

- **[Python]** Generator JPK/plików fiskalnych z danych — walidacja przed wysyłką.
- **[Python]** Raport Intrastat z danych importu/eksportu — auto-zestawienie wg CN.
- **[Excel]** Zestawienie do sprawozdania GUS — auto-agregacja wymaganych pól.
- **[Python]** Raport CSRD/ESG z danych operacyjnych — emisje/wolumeny/dostawcy.
- **[Python]** Walidacja zgodności przed wysyłką urzędową — reguły formalne.

### 4.15 Optymalizacja i decyzje

- **[Python]** OR-Tools do alokacji zasobów — przydział zleceń/tras/dostawców minimalizujący koszt.
- **[Python]** Symulacja Monte Carlo ryzyka dostaw — rozkład terminów/kosztów.
- **[Python]** What-if scenariusze w arkuszu sterowanym Pythonem — porównanie wariantów.
- **[Python]** Analiza wrażliwości decyzji — jak wynik zależy od założeń.
- **[Excel]** Solver do optymalizacji miksu zamówień — pod ograniczenia budżetu/pojemności.

### 4.16 Powiadomienia specjalistyczne i kanały

- **[Python]** Alert SMS przez bramkę (Twilio/SMSAPI) — krytyczne zdarzenia poza godzinami pracy.
- **[n8n]** Powiadomienie na WhatsApp Business — status zamówienia/dostawy do klienta.
- **[Python]** Push do Telegram (bot) — szybki kanał alertów dla zespołu.
- **[Power Automate]** Powiadomienie w Teams z @wzmianką osoby odpowiedzialnej — kieruje uwagę.
- **[Python]** Priorytetyzacja alertów (severity) — krytyczne natychmiast, reszta w digest.
- **[Python]** Cichy tryb w godzinach nocnych — wstrzymanie niekrytycznych powiadomień.

### 4.17 Konsolidacja raportów i dystrybucja

- **[Python]** Bursting raportów — jeden raport dzielony i wysyłany per odbiorca (jego dane).
- **[Python]** Kompozytor raportu miesięcznego — sklejenie wielu sekcji w jeden PDF.
- **[Power Automate]** Dystrybucja raportu do listy odbiorców z SharePoint — dynamiczna lista.
- **[Python]** Archiwum wersji raportów z metadanymi — kto/kiedy/co dostał.
- **[Excel]** Szablon raportu z placeholderami wypełnianymi z bazy — spójny wygląd.

### 4.18 Onboarding danych i integracje jednorazowe

- **[Python]** Migracja danych ze starego systemu — mapowanie i walidacja przy przenosinach.
- **[Python]** Import historyczny z plików Excel do bazy — jednorazowe zasilenie z kontrolą jakości.
- **[Python]** Mapowanie kodów między systemami — słownik translacji dla integracji.
- **[Python]** Weryfikacja kompletności migracji — sumy kontrolne przed/po.

### 4.19 Kontrola kosztów i budżet całości

- **[Power BI]** Skonsolidowany budżet vs wykonanie — zakupy/magazyn/sprzedaż w jednym.
- **[Python]** Alert przekroczenia budżetu działu — miesięczna projekcja vs plan.
- **[Excel]** Rolling forecast kosztów operacyjnych — aktualizowany co miesiąc.
- **[Python]** Analiza odchyleń plan-wykonanie z komentarzem — auto-wskazanie przyczyn.
- **[Python]** Kalkulator wskaźnika kosztu logistyki do obrotu — trend miesięczny.
- **[Power BI]** Waterfall zmian kosztów r/r — co zwiększyło/zmniejszyło koszty.
- **[Python]** Wykrywanie kosztów jednorazowych vs powtarzalnych — czystszy trend.

---

## 5. PER NARZĘDZIE — sztuczki i wzorce

### 5.1 Python — pandas / openpyxl / requests / schedule

- **[Python]** `pandas.merge` z `indicator=True` — kontrola strat przy złączeniach (left_only/right_only).
- **[Python]** `read_excel(sheet_name=None)` — wczytanie wszystkich arkuszy naraz do słownika DataFrame.
- **[Python]** `openpyxl` do wypełniania szablonu — zachowanie formatowania, wstawianie tylko danych.
- **[Python]** `pandas.pivot_table` → Excel — generowanie tabel przestawnych bez ręcznej pracy.
- **[Python]** `df.to_excel` z `xlsxwriter` — formatowanie warunkowe i wykresy z kodu.
- **[Python]** `requests.Session` z retry — stabilne odpytywanie API z backoff (urllib3 Retry).
- **[Python]** `schedule`/APScheduler — cykliczne uruchamianie zadań bez zewnętrznego crona.
- **[Python]** `pandas` styler → HTML mail — kolorowa tabela w treści maila.
- **[Python]** `python-dotenv` na sekrety — klucze API poza kodem, w .env.
- **[Python]** `logging` z rotacją plików — audyt działania skryptów, RotatingFileHandler.
- **[Python]** `pydantic` do walidacji wejścia — kontrakt danych z jasnym błędem przy naruszeniu.
- **[Python]** `pathlib` + glob do batch plików — masowe przetwarzanie folderu dokumentów.
- **[Python]** `datetime`/`workalendar` — liczenie dni roboczych (terminy płatności/dostaw).
- **[Python]** `smtplib`+`email.mime` — wysyłka maili z załącznikami z kodu.
- **[Python]** `sqlalchemy` jako warstwa DB — jeden kod do SQLite/Postgres/SQL Server.
- **[Python]** `duckdb` nad plikami Parquet/CSV — SQL na dużych plikach bez ładowania do RAM.
- **[Python]** `caching` (functools.lru_cache) — cache wolnych odpytań API/kursów.
- **[Python]** `tqdm` do długich pętli — pasek postępu przy masowym przetwarzaniu.
- **[Python]** `great_expectations`/asserty — testy jakości danych w pipeline.
- **[Python]** `win32com`/`xlwings` — sterowanie Excelem z Pythona (odświeżanie makr/PQ).

### 5.2 n8n — konkretne workflowy

- **[n8n]** Webhook → Function → HTTP → Slack — wzorzec przyjmij-przetwórz-powiadom.
- **[n8n]** Schedule Trigger → Postgres → IF → Email — cykliczny alert progowy.
- **[n8n]** IMAP Email → Extract → Spreadsheet — parsowanie skrzynki do arkusza.
- **[n8n]** HTTP Request z paginacją — Loop node przez strony API do wyczerpania.
- **[n8n]** Error Workflow globalny — jeden handler łapie błędy wszystkich flow → alert.
- **[n8n]** Merge node do łączenia źródeł — join danych z dwóch API po kluczu.
- **[n8n]** Split In Batches — przetwarzanie dużych zbiorów partiami (rate limit).
- **[n8n]** Wait node na approval — pauza flow do kliknięcia w mailu/webhooku.
- **[n8n]** Code node (JS) do transformacji — mapowanie/filtrowanie gdy brak gotowego node.
- **[n8n]** Cron → SAP OData → Power BI push — odświeżanie datasetu BI.
- **[n8n]** Redis/Static Data do deduplikacji — pamięć między uruchomieniami.
- **[n8n]** Switch node routing dokumentów — kieruje wg typu do różnych ścieżek.
- **[n8n]** HTTP → Binary → Google Drive/SharePoint — auto-zapis pobranych plików.
- **[n8n]** Sub-workflow reużywalny — wspólna logika (np. wyślij mail) wołana z wielu flow.
- **[n8n]** Trigger na nowy plik SharePoint → OCR API → DB — pipeline dokumentowy.

### 5.3 SharePoint / Power Platform

- **[SharePoint]** Lista jako baza danych — kolumny typowane, widoki filtrowane zamiast Excela na dysku.
- **[SharePoint]** Widoki warunkowe z formatowaniem JSON — kolorowanie wierszy wg statusu.
- **[Power Automate]** Flow „gdy utworzono element" — trigger na nowy wpis listy → akcje.
- **[Power Apps]** Formularz mobilny na liście — wprowadzanie danych z telefonu/tabletu.
- **[Power Automate]** Approval flow wieloetapowy — sekwencyjne/równoległe zatwierdzenia.
- **[SharePoint]** Biblioteka dokumentów z metadanymi + retencja — auto-archiwizacja.
- **[Power Automate]** Zapis załącznika maila do biblioteki — segregacja wg reguł.
- **[SharePoint]** Kolumna wyliczana + alert — status liczony, flow reaguje na zmianę.
- **[Power Automate]** Harmonogram (Recurrence) → generacja raportu → mail — cykliczny raport.
- **[Power Automate]** Integracja z Excel (tabela) — czytanie/zapis wierszy tabeli w pliku SharePoint.
- **[SharePoint]** Lista wyszukiwalna z filtrami jako CRM lite — bez zewnętrznego systemu.
- **[Power Automate]** Publikowanie do Teams (Adaptive Card) — powiadomienia z akcjami.
- **[Power Automate]** HTTP z Graph API — dostęp do danych M365 poza gotowymi konektorami.
- **[SharePoint]** Wersjonowanie dokumentów — historia zmian umów/cenników wbudowana.

### 5.4 Excel — Power Query, dynamiczne tablice, VBA→Python

- **[Excel]** Power Query z folderu — konsolidacja wszystkich plików z katalogu jednym zapytaniem.
- **[Excel]** Merge/Append w PQ — SQL-owe joiny i union bez formuł.
- **[Excel]** Parametry PQ — ścieżka/data jako parametr, jeden szablon dla wielu okresów.
- **[Excel]** `XLOOKUP` zamiast VLOOKUP — odporne dopasowanie w obie strony, z domyślną wartością.
- **[Excel]** Dynamiczne tablice (`FILTER`/`SORT`/`UNIQUE`) — raporty bez tabel przestawnych.
- **[Excel]** `LET`/`LAMBDA` — czytelne złożone formuły, funkcje własne bez VBA.
- **[Excel]** Tabela (Ctrl+T) jako źródło — auto-rozszerzanie zakresów, spójne formuły.
- **[Excel]** Formatowanie warunkowe z formułą — semafory statusów, paski danych.
- **[Excel]** Wykresy przebiegu w czasie (sparkline) — trend w jednej komórce.
- **[Excel]** Migracja makra VBA → skrypt Python — pandas zamiast pętli VBA (szybsze, testowalne).
- **[Excel]** Model danych + PivotTable z relacjami — mini-hurtownia w jednym pliku.
- **[Excel]** `GETPIVOTDATA` do dashboardu — sterowane odwołania do przestawnej.
- **[Excel]** Walidacja danych (lista rozwijana) — kontrola wprowadzania na wejściu.
- **[Excel]** Office Scripts (TypeScript) — automatyzacja w Excel Online + Power Automate.
- **[Excel]** Nazwane zakresy + `INDIRECT` — dynamiczne raporty sterowane wyborem.
- **[Excel]** `TEXTSPLIT`/`TEXTJOIN` — parsowanie i sklejanie danych tekstowych.

### 5.5 Python — więcej wzorców praktycznych

- **[Python]** `concurrent.futures` do równoległych zapytań API — szybszy pobór wielu źródeł.
- **[Python]** `jinja2` + `weasyprint` — generowanie PDF (oferty, raporty) z szablonów HTML.
- **[Python]** `imaplib`/`exchangelib` — czytanie skrzynki i załączników z kodu.
- **[Python]** `fuzzywuzzy`/`rapidfuzz` — dopasowanie nieidealnych tekstów (nazwy, opisy).
- **[Python]** `camelot`/`pdfplumber` — ekstrakcja tabel z PDF do DataFrame.
- **[Python]** `statsmodels`/`prophet` — prognozy z sezonowością i trendem.
- **[Python]** `openpyxl` conditional_formatting z kodu — semafory w generowanych arkuszach.
- **[Python]** `typer`/`argparse` — CLI do uruchamiania skryptów z parametrami.
- **[Python]** `pytest` na logikę biznesową — testy reguł (marże, progi) jako strażnik regresji.
- **[Python]** `polars` zamiast pandas na dużych danych — szybsze przetwarzanie.
- **[Python]** `httpx` async — asynchroniczne odpytywanie wielu endpointów.
- **[Python]** `tenacity` — deklaratywne retry z backoffem dla niestabilnych API.

### 5.6 API REST — wzorce integracyjne

- **[API]** Uwierzytelnianie OAuth2 client credentials — bezpieczny dostęp do SAP/Graph/CRM.
- **[API]** Webhook zamiast pollingu — reagowanie na zdarzenie zamiast ciągłego odpytywania.
- **[API]** Idempotency key — bezpieczne ponawianie bez duplikatów (zamówienia/płatności).
- **[API]** Paginacja i rate limiting — obsługa dużych zbiorów bez blokady.
- **[API]** Warstwa cache dla wolnych API — Redis/plik, redukcja wywołań.
- **[API]** Kontrakt OpenAPI + walidacja — pewność zgodności danych z endpointem.
- **[API]** Fasada REST nad SAP OData — uproszczony endpoint dla frontendu/n8n.
- **[API]** Kolejka zdarzeń (message queue) — buforowanie i asynchroniczne przetwarzanie.

### 5.7 Power BI — wzorce raportowe

- **[Power BI]** Model gwiazdy (star schema) — fakty + wymiary zamiast płaskiej tabeli.
- **[Power BI]** Miary DAX z time intelligence — YTD/MTD/YoY jednym wzorem.
- **[Power BI]** Incremental refresh — odświeżanie tylko nowych danych.
- **[Power BI]** Row-level security — te same raporty, dane per rola/handlowiec.
- **[Power BI]** Tooltipy stron raportu — kontekstowe detale bez zaśmiecania.
- **[Power BI]** Bookmarki i przyciski nawigacji — interaktywne scenariusze analizy.
- **[Power BI]** Dataflow jako wspólne źródło — jedna transformacja dla wielu raportów.
- **[Power BI]** Alerty i subskrypcje — proaktywne powiadomienia o KPI.

### 5.8 n8n — więcej gotowych scenariuszy

- **[n8n]** Cron → HTTP (kurs NBP) → Google Sheets — dzienny zapis kursów do arkusza.
- **[n8n]** Webhook formularza → walidacja → SharePoint list — rejestracja zgłoszeń.
- **[n8n]** IMAP → OCR (HTTP) → IF rozbieżność → Approval — obieg faktur.
- **[n8n]** Schedule → SQL → HTML table → SMTP — cykliczny raport mailowy.
- **[n8n]** RSS/HTTP monitor cen → IF próg → Telegram — alert rynkowy.
- **[n8n]** Trigger SAP (OData) → transform → Power BI push dataset — świeże KPI.
- **[n8n]** Loop dostawcy → Send RFQ → Wait → zbierz odpowiedzi — proces sourcingu.
- **[n8n]** Error trigger → log do DB + alert — centralna obsługa błędów.
- **[n8n]** HTTP tracking kuriera → IF opóźnienie → mail do klienta — proaktywna obsługa.
- **[n8n]** Webhook e-commerce → mapowanie → ERP API — integracja zamówień.

### 5.9 SharePoint / Excel Online — dodatkowe wzorce

- **[SharePoint]** Kolumny osoby/lookup — relacje między listami (zamówienie→dostawca).
- **[SharePoint]** Reguły alertów wbudowane — powiadomienie o zmianie elementu.
- **[Power Automate]** Zaplanowany eksport listy do Excela — snapshot do raportu.
- **[Excel]** Skoroszyt współdzielony z Power Query z SharePoint — wspólne źródło zespołu.
- **[Excel]** Makro Office Scripts + Power Automate — automatyczne formatowanie raportu.
- **[SharePoint]** Formularz Microsoft Forms → lista → flow — zbieranie danych z pola.
- **[Excel]** Połączenie z SQL Server (natywne) — raport na żywo bez eksportów.

### 5.10 OCR — wzorce ekstrakcji

- **[OCR]** Szablon strefowy (template zones) — stałe położenie pól na powtarzalnym formularzu.
- **[OCR]** LLM extraction dla zmiennych układów — ~100 formatów faktur bez sztywnego szablonu.
- **[OCR]** Wstępne prostowanie skanu (deskew) — poprawa jakości przed rozpoznaniem.
- **[OCR]** Walidacja krzyżowa pól — suma pozycji = suma faktury jako kontrola OCR.
- **[OCR]** Confidence threshold + ręczny przegląd — niska pewność → do weryfikacji człowieka.
- **[OCR]** Rozpoznawanie kodów kreskowych ze skanu — zbindowanie dokumentu z rekordem.
- **[OCR]** Ekstrakcja z tabel wielostronicowych — łączenie pozycji z kolejnych stron.

### 5.11 SMTP / mail — wzorce

- **[SMTP]** Maile HTML z inline wykresami — obraz PNG jako CID w treści.
- **[SMTP]** Personalizacja masowa z rate limitem — uniknięcie oznaczenia jako spam.
- **[Python]** Parsowanie odpowiedzi (reply parsing) — wyciąganie treści bez cytowanej historii.
- **[Python]** Kolejka wysyłki z retry — niewysłane maile ponawiane.
- **[SMTP]** Podpis i stopka z danymi dynamicznymi — nr sprawy/link do statusu.
- **[Python]** Auto-załączanie właściwych dokumentów — dobór PDF wg kontekstu maila.

### 5.12 Bazy danych i przechowywanie

- **[Python]** SQLite jako lokalna baza automatyzacji — szybki start bez serwera.
- **[Python]** Postgres do współdzielonych danych — jedno źródło prawdy dla wielu skryptów.
- **[Python]** Parquet do archiwum analitycznego — kompaktowe, szybkie do odczytu.
- **[Python]** Upsert (INSERT ON CONFLICT) — idempotentne ładowanie bez duplikatów.
- **[Python]** Widoki SQL jako warstwa raportowa — logika w bazie, nie w każdym skrypcie.
- **[Python]** Partycjonowanie po dacie — wydajne zapytania na dużych tabelach.

### 5.13 Harmonogramowanie i uruchamianie

- **[Python]** Windows Task Scheduler + skrypt — uruchamianie cykliczne na stacji/serwerze.
- **[Python]** Docker + cron — powtarzalne środowisko dla automatyzacji.
- **[n8n]** Self-hosted n8n jako orkiestrator — jedno miejsce na wszystkie flow.
- **[Python]** Lock pliku/DB przeciw równoległym uruchomieniom — brak kolizji zadań.
- **[Python]** Kolejka zadań (RQ/Celery) — asynchroniczne, skalowalne przetwarzanie.

### 5.14 Excel — dodatkowe techniki analityczne

- **[Excel]** `SUMIFS`/`COUNTIFS`/`AVERAGEIFS` — raporty warunkowe bez przestawnych.
- **[Excel]** Fragmentator (slicer) na tabeli i przestawnej — interaktywne filtry.
- **[Excel]** Oś czasu (timeline) do filtrowania dat — intuicyjny wybór okresu.
- **[Excel]** `XMATCH`+`INDEX` — elastyczne wyszukiwanie dwukierunkowe.
- **[Excel]** Analiza scenariuszy (Menedżer scenariuszy) — porównanie wariantów założeń.
- **[Excel]** `AGGREGATE` z pominięciem błędów/ukrytych — odporne sumy.
- **[Excel]** Nazwane formuły LAMBDA jako biblioteka — reużywalne funkcje w skoroszycie.

### 5.15 Python — raportowanie i wizualizacja

- **[Python]** `matplotlib`/`plotly` do wykresów w raportach — PNG/HTML osadzane w mailu.
- **[Python]** `pandas.style` + eksport HTML — kolorowe tabele bez Excela.
- **[Python]** `great_tables` do publikacyjnych tabel — ładne zestawienia.
- **[Python]** `streamlit`/`dash` mini-app — interaktywny raport dla zespołu.
- **[Python]** Generowanie slajdów (python-pptx) — auto-prezentacja wyników.

---

## 6. TOP 20 do zrobienia najpierw (największy zwrot / najmniejszy koszt)

1. **[Python]** 3-way match faktura↔PO↔przyjęcie — eliminuje ręczną kontrolę i nadpłaty.
2. **[Python]** Silnik reorder point z alertem — zapobiega brakom i nadmiarom.
3. **[OCR]** Ekstrakcja faktur PDF do rejestru — koniec przepisywania ręcznie.
4. **[Python]** Alert stanu minimalnego z SAP na mail — codzienna higiena zapasów.
5. **[Power BI]** Jeden pulpit KPI (zakupy+magazyn+sprzedaż) — wspólny obraz sytuacji.
6. **[Python]** Detektor dead stock/slow-moving — uwalnia zamrożony kapitał.
7. **[n8n]** Pipeline faktur z maila (OCR→walidacja→rejestr) — end-to-end bez rąk.
8. **[Python]** Parser potwierdzeń zamówień/ETA z maili — auto-aktualizacja terminów.
9. **[Excel]** Power Query konsolidujący raporty z folderu — koniec ręcznego sklejania.
10. **[Python]** Scoring dostawców (OTIF+jakość+cena) — obiektywna ocena, mniej ryzyka.
11. **[API]** Tracking kontenerów po BL — bieżący status importu bez telefonów.
12. **[Python]** Raport dzienny sprzedaży na mail — start dnia z liczbami.
13. **[Power Automate]** Approval flow PO/rabatów — szybsze i udokumentowane decyzje.
14. **[Python]** Alert spadku zamówień klienta (churn) — reakcja zanim klient odejdzie.
15. **[Python]** Wykrywanie duplikatów faktur — blokada podwójnych płatności.
16. **[SharePoint]** Kalendarz awizacji dostaw — koniec kolizji na rampie.
17. **[Python]** Segmentacja RFM klientów — ukierunkowane działania sprzedażowe.
18. **[Python]** Kalkulator landed cost importu — realny koszt sprowadzenia towaru.
19. **[n8n]** Centrum alertów na Teams z deduplikacją — jedno miejsce na sygnały krytyczne.
20. **[Python]** ETL Excel→baza z walidacją — fundament pod wszystkie dalsze analizy.

---

_Uwaga wdrożeniowa:_ zacznij od pozycji, które usuwają ręczne przepisywanie danych (OCR, ETL, parsowanie maili) i od alertów progowych — dają najszybszy zwrot przy najmniejszym nakładzie. Cięższe optymalizacje (bin packing, prognozy, modele churn) rób dopiero, gdy dane są już czyste i zintegrowane.

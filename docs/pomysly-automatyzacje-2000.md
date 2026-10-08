# TIMPORYE — 2000 pomysłów na automatyzacje i feature'y

> Rozszerzenie `docs/pomysly-automatyzacje.md`. Format pozycji:
> `- [✅|🔲] **[tag]** Tytuł — co robi / wyzwalacz→akcja.`
> Legenda: **✅ = już zaimplementowane w repo TIMPORYE** (potwierdzone w routerach/modelach/ekranach/pętlach tła),
> **🔲 = backlog (do zrobienia)**. Tagi: [Python][n8n][Excel][SharePoint][PowerBI][OCR][Teams][API][Feature].
>
> Bazę „co już działa" ustalono z: `backend/app/routers/*.py`, `backend/app/models.py`,
> `frontend/src/pages/*.tsx`, pętli tła w `backend/app/main.py`
> (demurrage, customs_delay, complaint_reminder, pallet_urgent, tracking, ais, daily/weekly digest, verify_backup).

---

## Skrót — co już działa w repo (baza dla znaczników ✅)

- Kolejka kontenerów (QueuePage, QueueTv, WarehouseQueue, containers, Container) — cykl życia kontenera.
- Tracking + timeline kontenera (tracking_loop, TrackingEvent, TrackingPage) + AIS statków (ais_loop, TrackedVessel/VesselPosition/VesselPortCall/PortCongestion).
- Demurrage/free-time (demurrage_loop, PortTransitTime), opóźnienia odpraw (customs_delay_loop, CustomsPage).
- Reklamacje (complaints, Complaint/Problem/Photo, complaint_reminder_loop, ComplaintStats).
- Wywołania palet/DLT (pallets, dlt, PalletCall*, DltStock, pallet_urgent_loop, PalletCallsPage, DltPage).
- Zlecenia spedycyjne/transportowe (forwarding, TransportOrder/Job, ForwardingPage, QuotesPage, Quote/Revision).
- Awizacja (avizo, AvizoRequest/Item/Proposal, AvizoFormPage), karta rozładunku (warehouse_ops, KartaRozladunku, GatePage, UnloadPhoto), checklist (ChecklistPoint/Result).
- Faktury/OCR + batch (invoices, InvoiceBatch/Job/Item, integracja Compare/CIPL), PO + import ETD/SAP (purchase_orders, purchasing, imports, PurchaseOrder, SapOrder).
- Master data (MasterDataPage, dictionaries, materials, Supplier/Forwarder/Carrier/Port/ContainerType).
- Portal klienta + linki share (portal, share, PortalPage, SharePage, CustomerShareLink/ContainerShareLink/SentLink, DriverLink).
- Analityka/dashboard/prognoza (analytics, AnalitykaPage, DashboardPage, ForecastTab, StatsCharts), kalendarz kolejki (queue_calendar, CalendarDay, DailyLimit).
- Powiadomienia + reguły (notifications, Notification/Rule/WatchedContainer), SMS (SmsMessage/Twilio), Power BI (PowerBIToken), digesty (daily/weekly), backup (verify_backup_loop).
- Baza wiedzy/szkolenia/biuletyny (knowledge, KnowledgeNote/Bulletin/TrainingTopic), audyt (AuditLog), bezpieczeństwo (BlockedIP, ClientError, RequestID/CSP, /health).
- Role i izolacja per-zasób (check_container_access, deps.py `_enforce_scope`/`scope_containers`).

---

## 1. ZAKUPY









### 1.1 Monitoring dostawców i cen
- 🔲 **[Python]** Scraper cenników dostawców — dzienny pobór stron/PDF, diff cen, alert >5% zmiany.
- 🔲 **[Python]** Historia cen surowca — pobór notowań (LME/GUS) do bazy, wykres 30/90/365 dni.
- 🔲 **[n8n]** Alert progu cenowego — HTTP poll giełdy, IF < próg → Teams.
- 🔲 **[Excel]** Power Query kurs NBP — auto pobór tabeli, przeliczenie cen importu na PLN.
- 🔲 **[Python]** Indeks kosztowy koszyka TOP20 — ważona średnia, alert m/m.
- 🔲 **[Python]** Alert kursu FX vs kurs budżetowy — ryzyko na PO w USD/EUR.
- 🔲 **[Python]** Wykrywanie anomalii cenowych (z-score) na pozycjach zakupu.
- 🔲 **[Python]** Kalkulator TCO/landed cost importu — cena+fracht+cło+ubezp.+magazyn, ranking ofert.
- 🔲 **[PowerBI]** Dashboard trendów cen zakupu — price index per kategoria, drill-down dostawca.
- 🔲 **[n8n]** Watcher zmiany cennika PDF w SharePoint → OCR → diff na mail.
- 🔲 **[Python]** Monitoring kondycji finansowej dostawcy — alert przy pogorszeniu scoringu z wywiadowni.
- 🔲 **[API]** Integracja API dostawcy hurtowego — ceny/dostępność przez REST, cache do bazy.
- 🔲 **[Python]** Rozproszenie cen tej samej pozycji u dostawców — wykrycie przepłacania.
- 🔲 **[Python]** Alert dostawcy na liście sankcyjnej/OFAC przy dodaniu i płatności.
- 🔲 **[Python]** Symulator wpływu ceny surowca na koszt wyrobu (BOM przelicznik).

### 1.2 Zamówienia zakupowe (PO)
- ✅ **[Feature]** Rejestr PurchaseOrder + panel PO (PurchaseOrdersPanel/OrdersPage) — powiązanie z kontenerami.
- ✅ **[Python]** Import PO z pliku (ImportModal/imports) — masowe wczytanie zamówień/ETD.
- ✅ **[API]** Import SAP zamówień (SapOrder, imports) — LFA1/EKKO do systemu.
- 🔲 **[Python]** Silnik reorder point — stan < ROP → propozycja PO.
- 🔲 **[Python]** ROP z lead time — `śr_zużycie*lead + zapas_bezp`, tygodniowa aktualizacja.
- 🔲 **[Python]** EOQ kalkulator — ekonomiczna wielkość zamówienia.
- 🔲 **[Python]** Prognoza zapotrzebowania (Holt-Winters) per SKU → wielkość i termin PO.
- 🔲 **[n8n]** Auto-draft PO z webhooka stanu SAP → do akceptacji.
- 🔲 **[Feature]** Workflow zatwierdzania PO — approval wg kwoty/centrum kosztów.
- 🔲 **[Python]** Grupowanie PO wg dostawcy — jedno zamówienie, mniej fraktu.
- 🔲 **[Python]** Optymalizacja pod próg darmowej dostawy — dobór pozycji.
- 🔲 **[Python]** Auto-split zamówienia między dostawców wg alokacji/ceny.
- 🔲 **[n8n]** Cykliczne call-off z umowy ramowej — harmonogram.
- 🔲 **[Python]** Blokada reorder martwych zapasów (>180 dni bez rotacji).
- 🔲 **[Feature]** Eskalacja niezatwierdzonego PO — >24h przypomnienie, >48h wyżej.
- 🔲 **[Python]** Konsolidacja zapotrzebowań z wielu działów w jedno PO.
- 🔲 **[Excel]** Kalkulator pokrycia zapotrzebowania — ile dni starczy zapas.
- 🔲 **[Feature]** Statusy realizacji PO na osi (potwierdzone/w drodze/dostarczone) w karcie zamówienia.
- 🔲 **[Python]** Sugestia terminu zamówienia wstecz od potrzeby (backward scheduling).
- 🔲 **[Python]** Netting: potrzeba − stan − zamówienia w drodze.

### 1.3 Faktury vs PO (3-way match)
- ✅ **[OCR]** Ekstrakcja danych z faktury PDF (InvoiceBatch/Job/Item) — pozycje/kwoty do rejestru.
- ✅ **[API]** Integracja z Compare (CIPL) — parsowanie faktur handlowych do TIMPORYE.
- ✅ **[Feature]** Rejestr faktur z jobami i itemami (InvoicesPage) — podgląd i status.
- 🔲 **[Python]** 3-way match faktura↔PO↔przyjęcie — flagowanie rozbieżności.
- 🔲 **[Python]** Kontrola ceny na fakturze vs PO (±X%) → hold + mail.
- 🔲 **[Python]** Walidacja sum i VAT (netto+VAT=brutto, stawka poprawna).
- 🔲 **[Python]** Wykrywanie duplikatów faktur — hash dostawca+nr+kwota.
- 🔲 **[Python]** Faktura bez PO (maverick buying) — flaga.
- 🔲 **[API]** Weryfikacja NIP w VIES/białej liście MF przed księgowaniem.
- 🔲 **[OCR]** Odczyt numeru rachunku z faktury + porównanie z białą listą.
- 🔲 **[Python]** Fuzzy dopasowanie pozycji faktury do PO (`rapidfuzz`).
- 🔲 **[Excel]** Zestawienie rozbieżności cenowych do reklamacji z kwotą różnicy.
- 🔲 **[Python]** Termin płatności na fakturze vs warunki umowy.
- 🔲 **[Feature]** Routing faktury do akceptanta wg kwoty i centrum kosztów.
- 🔲 **[Python]** Auto-nota korygująca przy błędzie formalnym — szkic do dostawcy.

### 1.4 ETA / potwierdzenia / maile dostawców
- ✅ **[Feature]** Import ETD i dat z zamówień (PurchaseOrder + import) — zasilanie kolejki.
- 🔲 **[Python]** Parser potwierdzeń PO z maila (imap+LLM) — nr PO, ETA, ilości do bazy.
- 🔲 **[n8n]** Ekstrakcja ETA z maila dostawcy → aktualizacja zamówienia.
- 🔲 **[Python]** Klasyfikacja maili zakupowych (potwierdzenie/oferta/reklamacja/awizacja).
- 🔲 **[Python]** Wykrywanie zmiany ceny w potwierdzeniu vs zamówienie → alert.
- 🔲 **[n8n]** Auto-odpowiedź na potwierdzenie — zgodność→akcept, rozbieżność→eskalacja.
- 🔲 **[Python]** Detekcja opóźnienia z treści maila (słowa „delay/opóźnienie").
- 🔲 **[Python]** Follow-up niepotwierdzonego zamówienia po 2 dniach — auto-ponaglenie.
- 🔲 **[Python]** Ekstrakcja awizacji dostawy z maila → kalendarz przyjęć.
- 🔲 **[Python]** Tłumaczenie korespondencji zakupowej (LLM) dla dostawców zagranicznych.

### 1.5 Cła i dokumenty importowe (zakupowe)
- ✅ **[Feature]** Moduł celny (customs, CustomsPage, CustomsAgency, CustomsCaseStatus) — statusy odpraw.
- ✅ **[Python]** Alert opóźnienia odprawy (customs_delay_loop) — pętla tła.
- 🔲 **[Python]** Tracker kompletności dokumentów importu (CIPL/BL/CoO/EUR.1) — checklist.
- 🔲 **[OCR]** Odczyt SAD/faktury handlowej — pozycje, kody HS, wartości.
- 🔲 **[Python]** Walidacja kodów HS/CN i stawki cła.
- 🔲 **[API]** Pobór stawek celnych z TARIC → cło i VAT importowy per pozycja.
- 🔲 **[Python]** Rozliczenie kosztów frachtu na pozycje (alokacja wg wagi/wartości).
- 🔲 **[OCR]** Ekstrakcja Certificate of Origin do rejestru pochodzenia.
- 🔲 **[Python]** Rekoncyliacja: zamówienie vs BL vs przyjęcie (trójstronne).
- 🔲 **[n8n]** Powiadomienie agencji celnej po skompletowaniu paczki dokumentów.

### 1.6 Master data dostawców i materiałów
- ✅ **[Feature]** Kartoteka dostawców/forwarderów/przewoźników (Supplier/Forwarder/Carrier, MasterDataPage).
- ✅ **[Feature]** Kartoteka materiałów + przeliczniki (Material/UomConversion/MaterialUnit, materials).
- ✅ **[Feature]** Overrides materiału (MaterialOverride) — lokalne nadpisania danych.
- 🔲 **[Python]** Deduplikacja dostawców (fuzzy po nazwie/NIP/adresie).
- 🔲 **[API]** Wzbogacanie dostawcy z GUS/KRS po NIP (PKD, status, kapitał).
- 🔲 **[Python]** Walidacja kompletności kartoteki (IBAN, kontakt, warunki płatności).
- 🔲 **[Python]** Scoring dostawców (OTIF+jakość+cena+reklamacje) — ranking.
- 🔲 **[PowerBI]** Scorecard dostawcy — KPI, trend 12M, benchmark.
- 🔲 **[Python]** OTIF (On-Time-In-Full) z danych dostaw.
- 🔲 **[Python]** Deduplikacja indeksów materiałowych — ten sam towar pod różnymi kodami.
- 🔲 **[Python]** Kontrola przeliczników UoM (zakup vs magazyn) — błędne wartości.
- 🔲 **[API]** Wzbogacenie kartoteki o GTIN/EAN z GS1.
- 🔲 **[Excel]** Macierz Kraljica — klasyfikacja pozycji wg ryzyka i wartości.
- 🔲 **[SharePoint]** Formularz onboardingu dostawcy + workflow akceptacji.
- 🔲 **[Python]** Ankieta ESG dostawcy — auto-wysyłka i zbiór do scoringu.

### 1.7 Analityka i compliance zakupów
- 🔲 **[PowerBI]** Spend analysis — wydatki per kategoria/dostawca/miesiąc, drill-down.
- 🔲 **[Python]** Analiza ABC pozycji zakupowych — priorytetyzacja.
- 🔲 **[Python]** Raport savings — cena bieżąca vs bazowa, kwota oszczędności.
- 🔲 **[Python]** PO cycle time — czas od zapotrzebowania do dostawy, wąskie gardła.
- 🔲 **[Python]** Analiza tail spend — rozdrobnione drobne zakupy do konsolidacji.
- 🔲 **[Python]** Biała lista VAT batch — masowa weryfikacja rachunków (API MF).
- 🔲 **[Python]** Screening sankcyjny dostawców/odbiorców (OFAC/UE).
- 🔲 **[Python]** Prognoza cash flow zobowiązań — kalendarz płatności AP.
- 🔲 **[Excel]** Aging zobowiązań (AP) — koszyki wymagalności.
- 🔲 **[Python]** Early payment discount — faktury z rabatem za wcześniejszą płatność.
- 🔲 **[Python]** Kontrola limitów budżetu per centrum kosztów.
- 🔲 **[Python]** Wykrywanie maverick buying — zakupy poza kontraktem do audytu.
- 🔲 **[Python]** Analiza koncentracji zakupów (Pareto TOP dostawców) — ryzyko uzależnienia.
- 🔲 **[Python]** Generator RFQ z listy pozycji do dostawców.
- 🔲 **[Python]** Porównywarka ofert (bid comparison) — ranking cena/termin/warunki.

### 1.8 Walidacja pól importu (per pole)
- 🔲 **[Python]** Walidacja pola importu: numer kontenera — kontrola formatu/obecności pola „numer kontenera” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: numer BL — kontrola formatu/obecności pola „numer BL” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: ETD — kontrola formatu/obecności pola „ETD” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: ETA — kontrola formatu/obecności pola „ETA” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: numer PO — kontrola formatu/obecności pola „numer PO” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: dostawca — kontrola formatu/obecności pola „dostawca” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: port załadunku — kontrola formatu/obecności pola „port załadunku” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: port rozładunku — kontrola formatu/obecności pola „port rozładunku” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: typ kontenera — kontrola formatu/obecności pola „typ kontenera” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: waga brutto — kontrola formatu/obecności pola „waga brutto” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: waga netto — kontrola formatu/obecności pola „waga netto” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: liczba palet — kontrola formatu/obecności pola „liczba palet” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: liczba kartonów — kontrola formatu/obecności pola „liczba kartonów” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: kod HS/CN — kontrola formatu/obecności pola „kod HS/CN” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: wartość CIF — kontrola formatu/obecności pola „wartość CIF” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: waluta — kontrola formatu/obecności pola „waluta” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: Incoterms — kontrola formatu/obecności pola „Incoterms” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: numer faktury — kontrola formatu/obecności pola „numer faktury” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: data faktury — kontrola formatu/obecności pola „data faktury” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: numer SENT — kontrola formatu/obecności pola „numer SENT” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: kod materiału — kontrola formatu/obecności pola „kod materiału” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: ilość — kontrola formatu/obecności pola „ilość” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: jednostka miary — kontrola formatu/obecności pola „jednostka miary” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: kraj pochodzenia — kontrola formatu/obecności pola „kraj pochodzenia” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: numer plomby — kontrola formatu/obecności pola „numer plomby” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: armator — kontrola formatu/obecności pola „armator” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: nazwa statku — kontrola formatu/obecności pola „nazwa statku” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: numer rezerwacji — kontrola formatu/obecności pola „numer rezerwacji” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: termin free-time — kontrola formatu/obecności pola „termin free-time” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: numer NIP dostawcy — kontrola formatu/obecności pola „numer NIP dostawcy” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: IBAN dostawcy — kontrola formatu/obecności pola „IBAN dostawcy” przy wczytaniu pliku → flaga błędu.
- 🔲 **[Python]** Walidacja pola importu: stawka VAT — kontrola formatu/obecności pola „stawka VAT” przy wczytaniu pliku → flaga błędu.

### 1.9 Raporty wydatków (wymiar × okres)
- 🔲 **[PowerBI]** Raport wydatków dzienny per dostawcy — zestawienie dzienny kosztów zakupu w podziale na dostawcy.
- 🔲 **[PowerBI]** Raport wydatków tygodniowy per dostawcy — zestawienie tygodniowy kosztów zakupu w podziale na dostawcy.
- 🔲 **[PowerBI]** Raport wydatków miesięczny per dostawcy — zestawienie miesięczny kosztów zakupu w podziale na dostawcy.
- 🔲 **[PowerBI]** Raport wydatków kwartalny per dostawcy — zestawienie kwartalny kosztów zakupu w podziale na dostawcy.
- 🔲 **[PowerBI]** Raport wydatków roczny per dostawcy — zestawienie roczny kosztów zakupu w podziale na dostawcy.
- 🔲 **[PowerBI]** Raport wydatków dzienny per spedytora — zestawienie dzienny kosztów zakupu w podziale na spedytora.
- 🔲 **[PowerBI]** Raport wydatków tygodniowy per spedytora — zestawienie tygodniowy kosztów zakupu w podziale na spedytora.
- 🔲 **[PowerBI]** Raport wydatków miesięczny per spedytora — zestawienie miesięczny kosztów zakupu w podziale na spedytora.
- 🔲 **[PowerBI]** Raport wydatków kwartalny per spedytora — zestawienie kwartalny kosztów zakupu w podziale na spedytora.
- 🔲 **[PowerBI]** Raport wydatków roczny per spedytora — zestawienie roczny kosztów zakupu w podziale na spedytora.
- 🔲 **[PowerBI]** Raport wydatków dzienny per przewoźnika — zestawienie dzienny kosztów zakupu w podziale na przewoźnika.
- 🔲 **[PowerBI]** Raport wydatków tygodniowy per przewoźnika — zestawienie tygodniowy kosztów zakupu w podziale na przewoźnika.
- 🔲 **[PowerBI]** Raport wydatków miesięczny per przewoźnika — zestawienie miesięczny kosztów zakupu w podziale na przewoźnika.
- 🔲 **[PowerBI]** Raport wydatków kwartalny per przewoźnika — zestawienie kwartalny kosztów zakupu w podziale na przewoźnika.
- 🔲 **[PowerBI]** Raport wydatków roczny per przewoźnika — zestawienie roczny kosztów zakupu w podziale na przewoźnika.
- 🔲 **[PowerBI]** Raport wydatków dzienny per armatora — zestawienie dzienny kosztów zakupu w podziale na armatora.
- 🔲 **[PowerBI]** Raport wydatków tygodniowy per armatora — zestawienie tygodniowy kosztów zakupu w podziale na armatora.
- 🔲 **[PowerBI]** Raport wydatków miesięczny per armatora — zestawienie miesięczny kosztów zakupu w podziale na armatora.
- 🔲 **[PowerBI]** Raport wydatków kwartalny per armatora — zestawienie kwartalny kosztów zakupu w podziale na armatora.
- 🔲 **[PowerBI]** Raport wydatków roczny per armatora — zestawienie roczny kosztów zakupu w podziale na armatora.
- 🔲 **[PowerBI]** Raport wydatków dzienny per portu — zestawienie dzienny kosztów zakupu w podziale na portu.
- 🔲 **[PowerBI]** Raport wydatków tygodniowy per portu — zestawienie tygodniowy kosztów zakupu w podziale na portu.
- 🔲 **[PowerBI]** Raport wydatków miesięczny per portu — zestawienie miesięczny kosztów zakupu w podziale na portu.
- 🔲 **[PowerBI]** Raport wydatków kwartalny per portu — zestawienie kwartalny kosztów zakupu w podziale na portu.
- 🔲 **[PowerBI]** Raport wydatków roczny per portu — zestawienie roczny kosztów zakupu w podziale na portu.
- 🔲 **[PowerBI]** Raport wydatków dzienny per magazynu — zestawienie dzienny kosztów zakupu w podziale na magazynu.
- 🔲 **[PowerBI]** Raport wydatków tygodniowy per magazynu — zestawienie tygodniowy kosztów zakupu w podziale na magazynu.
- 🔲 **[PowerBI]** Raport wydatków miesięczny per magazynu — zestawienie miesięczny kosztów zakupu w podziale na magazynu.
- 🔲 **[PowerBI]** Raport wydatków kwartalny per magazynu — zestawienie kwartalny kosztów zakupu w podziale na magazynu.
- 🔲 **[PowerBI]** Raport wydatków roczny per magazynu — zestawienie roczny kosztów zakupu w podziale na magazynu.
- 🔲 **[PowerBI]** Raport wydatków dzienny per klienta — zestawienie dzienny kosztów zakupu w podziale na klienta.
- 🔲 **[PowerBI]** Raport wydatków tygodniowy per klienta — zestawienie tygodniowy kosztów zakupu w podziale na klienta.
- 🔲 **[PowerBI]** Raport wydatków miesięczny per klienta — zestawienie miesięczny kosztów zakupu w podziale na klienta.
- 🔲 **[PowerBI]** Raport wydatków kwartalny per klienta — zestawienie kwartalny kosztów zakupu w podziale na klienta.
- 🔲 **[PowerBI]** Raport wydatków roczny per klienta — zestawienie roczny kosztów zakupu w podziale na klienta.
- 🔲 **[PowerBI]** Raport wydatków dzienny per materiału — zestawienie dzienny kosztów zakupu w podziale na materiału.
- 🔲 **[PowerBI]** Raport wydatków tygodniowy per materiału — zestawienie tygodniowy kosztów zakupu w podziale na materiału.
- 🔲 **[PowerBI]** Raport wydatków miesięczny per materiału — zestawienie miesięczny kosztów zakupu w podziale na materiału.
- 🔲 **[PowerBI]** Raport wydatków kwartalny per materiału — zestawienie kwartalny kosztów zakupu w podziale na materiału.
- 🔲 **[PowerBI]** Raport wydatków roczny per materiału — zestawienie roczny kosztów zakupu w podziale na materiału.

### 1.10 Scoring per wymiar
- 🔲 **[Python]** Scoring i ranking per dostawcy — wskaźnik jakości współpracy (OTIF/cena/reklamacje) w podziale na dostawcy.
- 🔲 **[Python]** Scoring i ranking per spedytora — wskaźnik jakości współpracy (OTIF/cena/reklamacje) w podziale na spedytora.
- 🔲 **[Python]** Scoring i ranking per przewoźnika — wskaźnik jakości współpracy (OTIF/cena/reklamacje) w podziale na przewoźnika.
- 🔲 **[Python]** Scoring i ranking per armatora — wskaźnik jakości współpracy (OTIF/cena/reklamacje) w podziale na armatora.
- 🔲 **[Python]** Scoring i ranking per portu — wskaźnik jakości współpracy (OTIF/cena/reklamacje) w podziale na portu.
- 🔲 **[Python]** Scoring i ranking per magazynu — wskaźnik jakości współpracy (OTIF/cena/reklamacje) w podziale na magazynu.
- 🔲 **[Python]** Scoring i ranking per klienta — wskaźnik jakości współpracy (OTIF/cena/reklamacje) w podziale na klienta.
- 🔲 **[Python]** Scoring i ranking per materiału — wskaźnik jakości współpracy (OTIF/cena/reklamacje) w podziale na materiału.
- 🔲 **[Python]** Scoring i ranking per kraju — wskaźnik jakości współpracy (OTIF/cena/reklamacje) w podziale na kraju.
- 🔲 **[Python]** Scoring i ranking per trasy — wskaźnik jakości współpracy (OTIF/cena/reklamacje) w podziale na trasy.
- 🔲 **[Python]** Scoring i ranking per typu kontenera — wskaźnik jakości współpracy (OTIF/cena/reklamacje) w podziale na typu kontenera.
- 🔲 **[Python]** Scoring i ranking per agencji celnej — wskaźnik jakości współpracy (OTIF/cena/reklamacje) w podziale na agencji celnej.

### 1.11 Mapowanie kolumn importu (per pole)
- 🔲 **[Python]** Mapowanie kolumny importu → numer kontenera — konfiguracja dopasowania nagłówka pliku dostawcy do pola „numer kontenera”.
- 🔲 **[Python]** Mapowanie kolumny importu → numer BL — konfiguracja dopasowania nagłówka pliku dostawcy do pola „numer BL”.
- 🔲 **[Python]** Mapowanie kolumny importu → ETD — konfiguracja dopasowania nagłówka pliku dostawcy do pola „ETD”.
- 🔲 **[Python]** Mapowanie kolumny importu → ETA — konfiguracja dopasowania nagłówka pliku dostawcy do pola „ETA”.
- 🔲 **[Python]** Mapowanie kolumny importu → numer PO — konfiguracja dopasowania nagłówka pliku dostawcy do pola „numer PO”.
- 🔲 **[Python]** Mapowanie kolumny importu → dostawca — konfiguracja dopasowania nagłówka pliku dostawcy do pola „dostawca”.
- 🔲 **[Python]** Mapowanie kolumny importu → port załadunku — konfiguracja dopasowania nagłówka pliku dostawcy do pola „port załadunku”.
- 🔲 **[Python]** Mapowanie kolumny importu → port rozładunku — konfiguracja dopasowania nagłówka pliku dostawcy do pola „port rozładunku”.
- 🔲 **[Python]** Mapowanie kolumny importu → typ kontenera — konfiguracja dopasowania nagłówka pliku dostawcy do pola „typ kontenera”.
- 🔲 **[Python]** Mapowanie kolumny importu → waga brutto — konfiguracja dopasowania nagłówka pliku dostawcy do pola „waga brutto”.
- 🔲 **[Python]** Mapowanie kolumny importu → waga netto — konfiguracja dopasowania nagłówka pliku dostawcy do pola „waga netto”.
- 🔲 **[Python]** Mapowanie kolumny importu → liczba palet — konfiguracja dopasowania nagłówka pliku dostawcy do pola „liczba palet”.
- 🔲 **[Python]** Mapowanie kolumny importu → liczba kartonów — konfiguracja dopasowania nagłówka pliku dostawcy do pola „liczba kartonów”.
- 🔲 **[Python]** Mapowanie kolumny importu → kod HS/CN — konfiguracja dopasowania nagłówka pliku dostawcy do pola „kod HS/CN”.
- 🔲 **[Python]** Mapowanie kolumny importu → wartość CIF — konfiguracja dopasowania nagłówka pliku dostawcy do pola „wartość CIF”.
- 🔲 **[Python]** Mapowanie kolumny importu → waluta — konfiguracja dopasowania nagłówka pliku dostawcy do pola „waluta”.
- 🔲 **[Python]** Mapowanie kolumny importu → Incoterms — konfiguracja dopasowania nagłówka pliku dostawcy do pola „Incoterms”.
- 🔲 **[Python]** Mapowanie kolumny importu → numer faktury — konfiguracja dopasowania nagłówka pliku dostawcy do pola „numer faktury”.
- 🔲 **[Python]** Mapowanie kolumny importu → data faktury — konfiguracja dopasowania nagłówka pliku dostawcy do pola „data faktury”.
- 🔲 **[Python]** Mapowanie kolumny importu → numer SENT — konfiguracja dopasowania nagłówka pliku dostawcy do pola „numer SENT”.
- 🔲 **[Python]** Mapowanie kolumny importu → kod materiału — konfiguracja dopasowania nagłówka pliku dostawcy do pola „kod materiału”.
- 🔲 **[Python]** Mapowanie kolumny importu → ilość — konfiguracja dopasowania nagłówka pliku dostawcy do pola „ilość”.
- 🔲 **[Python]** Mapowanie kolumny importu → jednostka miary — konfiguracja dopasowania nagłówka pliku dostawcy do pola „jednostka miary”.
- 🔲 **[Python]** Mapowanie kolumny importu → kraj pochodzenia — konfiguracja dopasowania nagłówka pliku dostawcy do pola „kraj pochodzenia”.
- 🔲 **[Python]** Mapowanie kolumny importu → numer plomby — konfiguracja dopasowania nagłówka pliku dostawcy do pola „numer plomby”.
- 🔲 **[Python]** Mapowanie kolumny importu → armator — konfiguracja dopasowania nagłówka pliku dostawcy do pola „armator”.
- 🔲 **[Python]** Mapowanie kolumny importu → nazwa statku — konfiguracja dopasowania nagłówka pliku dostawcy do pola „nazwa statku”.
- 🔲 **[Python]** Mapowanie kolumny importu → numer rezerwacji — konfiguracja dopasowania nagłówka pliku dostawcy do pola „numer rezerwacji”.
- 🔲 **[Python]** Mapowanie kolumny importu → termin free-time — konfiguracja dopasowania nagłówka pliku dostawcy do pola „termin free-time”.
- 🔲 **[Python]** Mapowanie kolumny importu → numer NIP dostawcy — konfiguracja dopasowania nagłówka pliku dostawcy do pola „numer NIP dostawcy”.
- 🔲 **[Python]** Mapowanie kolumny importu → IBAN dostawcy — konfiguracja dopasowania nagłówka pliku dostawcy do pola „IBAN dostawcy”.
- 🔲 **[Python]** Mapowanie kolumny importu → stawka VAT — konfiguracja dopasowania nagłówka pliku dostawcy do pola „stawka VAT”.

### 1.12 Transformacje pól importu (per pole)
- 🔲 **[Python]** Reguła transformacji pola numer kontenera — normalizacja/parsowanie wartości „numer kontenera” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola numer BL — normalizacja/parsowanie wartości „numer BL” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola ETD — normalizacja/parsowanie wartości „ETD” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola ETA — normalizacja/parsowanie wartości „ETA” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola numer PO — normalizacja/parsowanie wartości „numer PO” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola dostawca — normalizacja/parsowanie wartości „dostawca” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola port załadunku — normalizacja/parsowanie wartości „port załadunku” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola port rozładunku — normalizacja/parsowanie wartości „port rozładunku” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola typ kontenera — normalizacja/parsowanie wartości „typ kontenera” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola waga brutto — normalizacja/parsowanie wartości „waga brutto” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola waga netto — normalizacja/parsowanie wartości „waga netto” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola liczba palet — normalizacja/parsowanie wartości „liczba palet” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola liczba kartonów — normalizacja/parsowanie wartości „liczba kartonów” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola kod HS/CN — normalizacja/parsowanie wartości „kod HS/CN” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola wartość CIF — normalizacja/parsowanie wartości „wartość CIF” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola waluta — normalizacja/parsowanie wartości „waluta” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola Incoterms — normalizacja/parsowanie wartości „Incoterms” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola numer faktury — normalizacja/parsowanie wartości „numer faktury” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola data faktury — normalizacja/parsowanie wartości „data faktury” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola numer SENT — normalizacja/parsowanie wartości „numer SENT” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola kod materiału — normalizacja/parsowanie wartości „kod materiału” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola ilość — normalizacja/parsowanie wartości „ilość” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola jednostka miary — normalizacja/parsowanie wartości „jednostka miary” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola kraj pochodzenia — normalizacja/parsowanie wartości „kraj pochodzenia” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola numer plomby — normalizacja/parsowanie wartości „numer plomby” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola armator — normalizacja/parsowanie wartości „armator” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola nazwa statku — normalizacja/parsowanie wartości „nazwa statku” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola numer rezerwacji — normalizacja/parsowanie wartości „numer rezerwacji” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola termin free-time — normalizacja/parsowanie wartości „termin free-time” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola numer NIP dostawcy — normalizacja/parsowanie wartości „numer NIP dostawcy” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola IBAN dostawcy — normalizacja/parsowanie wartości „IBAN dostawcy” przy imporcie (trim, format, jednostki).
- 🔲 **[Python]** Reguła transformacji pola stawka VAT — normalizacja/parsowanie wartości „stawka VAT” przy imporcie (trim, format, jednostki).

### 1.13 Słowniki wartości pól
- 🔲 **[Feature]** Słownik dozwolonych wartości pola numer kontenera — lista wartości i walidacja słownikowa pola „numer kontenera” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola numer BL — lista wartości i walidacja słownikowa pola „numer BL” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola ETD — lista wartości i walidacja słownikowa pola „ETD” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola ETA — lista wartości i walidacja słownikowa pola „ETA” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola numer PO — lista wartości i walidacja słownikowa pola „numer PO” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola dostawca — lista wartości i walidacja słownikowa pola „dostawca” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola port załadunku — lista wartości i walidacja słownikowa pola „port załadunku” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola port rozładunku — lista wartości i walidacja słownikowa pola „port rozładunku” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola typ kontenera — lista wartości i walidacja słownikowa pola „typ kontenera” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola waga brutto — lista wartości i walidacja słownikowa pola „waga brutto” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola waga netto — lista wartości i walidacja słownikowa pola „waga netto” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola liczba palet — lista wartości i walidacja słownikowa pola „liczba palet” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola liczba kartonów — lista wartości i walidacja słownikowa pola „liczba kartonów” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola kod HS/CN — lista wartości i walidacja słownikowa pola „kod HS/CN” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola wartość CIF — lista wartości i walidacja słownikowa pola „wartość CIF” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola waluta — lista wartości i walidacja słownikowa pola „waluta” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola Incoterms — lista wartości i walidacja słownikowa pola „Incoterms” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola numer faktury — lista wartości i walidacja słownikowa pola „numer faktury” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola data faktury — lista wartości i walidacja słownikowa pola „data faktury” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola numer SENT — lista wartości i walidacja słownikowa pola „numer SENT” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola kod materiału — lista wartości i walidacja słownikowa pola „kod materiału” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola ilość — lista wartości i walidacja słownikowa pola „ilość” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola jednostka miary — lista wartości i walidacja słownikowa pola „jednostka miary” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola kraj pochodzenia — lista wartości i walidacja słownikowa pola „kraj pochodzenia” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola numer plomby — lista wartości i walidacja słownikowa pola „numer plomby” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola armator — lista wartości i walidacja słownikowa pola „armator” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola nazwa statku — lista wartości i walidacja słownikowa pola „nazwa statku” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola numer rezerwacji — lista wartości i walidacja słownikowa pola „numer rezerwacji” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola termin free-time — lista wartości i walidacja słownikowa pola „termin free-time” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola numer NIP dostawcy — lista wartości i walidacja słownikowa pola „numer NIP dostawcy” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola IBAN dostawcy — lista wartości i walidacja słownikowa pola „IBAN dostawcy” w imporcie/formularzach.
- 🔲 **[Feature]** Słownik dozwolonych wartości pola stawka VAT — lista wartości i walidacja słownikowa pola „stawka VAT” w imporcie/formularzach.

## 2. LOGISTYKA / KONTENERY









### 2.1 Cykl życia i kolejka kontenera
- ✅ **[Feature]** Model Container + cykl życia — centralny hub systemu.
- ✅ **[Feature]** Kolejka kontenerów (QueuePage) — statusy, pilność, wiersze wh-*.
- ✅ **[Feature]** Kolejka na TV (QueueTvPage) — widok dużoformatowy dla hali.
- ✅ **[Feature]** Kolejka magazynu (WarehouseQueuePage) — perspektywa przyjęć.
- ✅ **[Feature]** Pasek podsumowania kolejki (QueueSummaryBar/queueSummary) — liczniki stanów.
- ✅ **[Feature]** Wypełnienie/gęstość wierszy kolejki (queueFill/queueRows) — czytelność.
- ✅ **[Feature]** Czyszczenie kolejki (ClearQueueModal) — masowe kasowanie po imporcie.
- ✅ **[Feature]** Kalendarz kolejki + limity dzienne (queue_calendar, CalendarDay, DailyLimit, CalendarPage).
- ✅ **[Feature]** Karta kontenera z osią czasu (ContainerPage, ContainerItems, ContainerTimeline).
- ✅ **[Feature]** Porty i czasy tranzytu (Port/PortTransitTime/ContainerPort) — planowanie.
- ✅ **[Feature]** Typy kontenerów (ContainerType) — słownik.
- ✅ **[Feature]** Izolacja per-zasób kontenerów (scope_containers/check_container_access).
- 🔲 **[Feature]** Widok „mapa drogi kontenera" — geo od portu załadunku do magazynu.
- 🔲 **[Feature]** Filtr kolejki po pilności + zapisane widoki użytkownika.
- 🔲 **[Feature]** Bulk-edycja statusów wielu kontenerów naraz z kolejki.
- 🔲 **[Feature]** Oznaczanie kontenerów „VIP/priorytet" z regułą sortowania.
- 🔲 **[Feature]** Grupowanie kontenerów w „batch przyjęcia" wg dnia/rampy.
- 🔲 **[Python]** Auto-priorytet kontenera wg demurrage + ETA + wartości ładunku.
- 🔲 **[Feature]** Historia zmian statusu kontenera (kto/kiedy) w karcie.
- 🔲 **[Feature]** Notatki i załączniki per kontener z tagami.

### 2.2 Tracking, ETA/ETD, statki
- ✅ **[Python]** Pętla trackingu (tracking_loop) — cykliczne odświeżanie statusów.
- ✅ **[Feature]** Ekran trackingu (TrackingPage) + zdarzenia (TrackingEvent).
- ✅ **[Python]** AIS kolektor pozycji statków (ais_loop, aisstream) — VesselPosition.
- ✅ **[Feature]** Śledzone statki i zawinięcia (TrackedVessel/VesselPortCall).
- ✅ **[Feature]** Kongestia portów (PortCongestion) — sygnał opóźnień.
- ✅ **[Feature]** Obserwowane kontenery (WatchedContainer) — subskrypcja zmian.
- 🔲 **[API]** Tracking po nr BL u agregatora (Searates/Project44) — uzupełnienie AIS.
- 🔲 **[Python]** Alert zmiany ETA >X dni — powiadomienie do spedycji/magazynu.
- 🔲 **[Python]** Predykcja realnej ETA z historii opóźnień na trasie/porcie.
- 🔲 **[Python]** Alert „statek zmienił port/rotację" — wpływ na plan.
- 🔲 **[PowerBI]** Timeline kontenerów w drodze — ETA, ryzyka, kongestia.
- 🔲 **[Feature]** Wykres opóźnień per armator/trasa (benchmarking przewoźników morskich).
- 🔲 **[Python]** Wykrywanie „statek utknął" (brak ruchu AIS >X h) — sygnał W5.
- 🔲 **[n8n]** Webhook „kontener w porcie" → awizacja do magazynu.
- 🔲 **[Python]** Auto-uzupełnienie ATA (faktyczne przybycie) z AIS zawinięcia.

### 2.3 Demurrage / free-time / koszty postoju
- ✅ **[Python]** Pętla demurrage (demurrage_loop) — nadzór dni wolnych.
- ✅ **[Feature]** Czasy tranzytu/free-time per port (PortTransitTime).
- 🔲 **[Python]** Kalkulator demurrage/detention — dni wolne vs upływające, alert przed opłatą.
- 🔲 **[Python]** Prognoza kosztu postoju per kontener przy bieżącym tempie odbioru.
- 🔲 **[Python]** Alert zbliżającej się granicy free-time (7/3/1 dzień).
- 🔲 **[PowerBI]** Dashboard kosztów demurrage — trend, per port, per armator.
- 🔲 **[Python]** Demurrage kalendarzowy z domyślną liczbą dni wolnych (konfigurowalny).
- 🔲 **[Python]** Ranking kontenerów wg ryzyka opłat — kolejność odbioru.
- 🔲 **[Excel]** Rozliczenie faktur demurrage vs własne wyliczenie — kontrola armatora.

### 2.4 Awizacja i planowanie dostaw
- ✅ **[Feature]** Awizacja dostaw (avizo, AvizoRequest/Item, AvizoFormPage) — zgłoszenia okien.
- ✅ **[Feature]** Propozycje zmian awizacji (AvizoChangeProposal, AvizoProposalsPage).
- ✅ **[Feature]** Wysyłka awizacji mailem (AvizoSendModal, QueueEmailModal).
- ✅ **[Feature]** Limity dzienne przyjęć (DailyLimit) — bramka planowania.
- 🔲 **[Python]** Optymalizator okien rampy — rozkłada dostawy bez kolizji (greedy/OR-Tools).
- 🔲 **[n8n]** Przypomnienie o awizacji dzień przed — mail/SMS do przewoźnika.
- 🔲 **[Python]** Wyrównanie obciążenia magazynu — bilans przyjęć/wydań, alert peak.
- 🔲 **[SharePoint]** Self-booking okna dostawy przez przewoźnika (formularz).
- 🔲 **[Python]** Prognoza wolumenu przyjęć z kontenerów w drodze → obsada.
- 🔲 **[PowerBI]** KPI terminowości awizacji — % dostaw w oknie.
- 🔲 **[Feature]** Auto-sugestia najbliższego wolnego slotu przy tworzeniu awizacji.

### 2.5 Paletyzacja i wywołania DLT/palet
- ✅ **[Feature]** Wywołania palet (pallets, PalletCall/Line/Truck/Link, PalletCallsPage).
- ✅ **[Python]** Pętla pilnych wywołań palet (pallet_urgent_loop) — eskalacja.
- ✅ **[Feature]** Stany DLT (dlt, DltStock, DltPage) — wywołania z magazynu DLT.
- ✅ **[Feature]** Cele stanów materiału (MaterialStockTarget) — progi wywołań.
- ✅ **[Feature]** Cache stanu paletowego (PalletStockCache) — szybki odczyt.
- ✅ **[Feature]** Produkty PAZ (paz, ProductPaz) — dane paletyzacji.
- ✅ **[Feature]** Wydania materiału (MaterialIssue) — rozchód powiązany z wywołaniem.
- ✅ **[Feature]** Ciężarówki wywołań palet (PalletCallTruck) — przypisanie transportu.
- 🔲 **[Python]** Kalkulator paletyzacji (py3dbp) — kartony/paletę EU, warstwy.
- 🔲 **[Python]** Optymalizacja załadunku kontenera/auta — bin packing 3D.
- 🔲 **[Python]** Generator etykiety palety SSCC (GS1-128) do PDF.
- 🔲 **[Python]** Reorder point palet/opakowań — nie zabraknie palet/folii.
- 🔲 **[Python]** Rejestr obrotu paletowego EU — saldo z dostawcami/klientami.
- 🔲 **[Python]** Alert deficytu palet — saldo poniżej progu operacyjnego.
- 🔲 **[Python]** Pakowanie kontenera pod pełne palety — minimalizacja resztek.

### 2.6 Planowanie dostaw (rozwinięcie)
- ✅ **[Feature]** Planowanie dostaw z limitem dziennym i kalendarzem (dekompozycja B-G częściowo).
- 🔲 **[Python]** Stała PLAN_LEAD_DAYS w planowaniu (nie licz z transit_time_days) — spójne daty.
- 🔲 **[Python]** Transit time sezonowy — korekta prognozy ETA wg miesiąca.
- 🔲 **[Python]** Wyrównanie kolejki pod przepustowość rozładunku (dzienny throughput).
- 🔲 **[Feature]** Symulator „co jak" — przesuń kontener, zobacz wpływ na kolejkę.
- 🔲 **[Python]** Auto-rozłożenie spiętrzenia kontenerów na kolejne dni w ramach limitu.
- 🔲 **[Feature]** Widok tygodniowy planu dostaw z drag&drop między dniami.

### 2.7 Alerty per status kontenera (kanał)
- 🔲 **[Python]** Alert statusu „potwierdzenie bookingu u armatora” mailem — wyzwalacz: wejście kontenera w status potwierdzenie bookingu u armatora → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „potwierdzenie bookingu u armatora” kartą w Teams — wyzwalacz: wejście kontenera w status potwierdzenie bookingu u armatora → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „potwierdzenie bookingu u armatora” SMS-em — wyzwalacz: wejście kontenera w status potwierdzenie bookingu u armatora → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „potwierdzenie bookingu u armatora” na dashboardzie — wyzwalacz: wejście kontenera w status potwierdzenie bookingu u armatora → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „potwierdzenie bookingu u armatora” powiadomieniem push — wyzwalacz: wejście kontenera w status potwierdzenie bookingu u armatora → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „załadunek w porcie nadania” mailem — wyzwalacz: wejście kontenera w status załadunek w porcie nadania → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „załadunek w porcie nadania” kartą w Teams — wyzwalacz: wejście kontenera w status załadunek w porcie nadania → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „załadunek w porcie nadania” SMS-em — wyzwalacz: wejście kontenera w status załadunek w porcie nadania → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „załadunek w porcie nadania” na dashboardzie — wyzwalacz: wejście kontenera w status załadunek w porcie nadania → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „załadunek w porcie nadania” powiadomieniem push — wyzwalacz: wejście kontenera w status załadunek w porcie nadania → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „wypłynięcie statku (ETD)” mailem — wyzwalacz: wejście kontenera w status wypłynięcie statku (ETD) → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „wypłynięcie statku (ETD)” kartą w Teams — wyzwalacz: wejście kontenera w status wypłynięcie statku (ETD) → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „wypłynięcie statku (ETD)” SMS-em — wyzwalacz: wejście kontenera w status wypłynięcie statku (ETD) → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „wypłynięcie statku (ETD)” na dashboardzie — wyzwalacz: wejście kontenera w status wypłynięcie statku (ETD) → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „wypłynięcie statku (ETD)” powiadomieniem push — wyzwalacz: wejście kontenera w status wypłynięcie statku (ETD) → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „w tranzycie morskim” mailem — wyzwalacz: wejście kontenera w status w tranzycie morskim → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „w tranzycie morskim” kartą w Teams — wyzwalacz: wejście kontenera w status w tranzycie morskim → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „w tranzycie morskim” SMS-em — wyzwalacz: wejście kontenera w status w tranzycie morskim → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „w tranzycie morskim” na dashboardzie — wyzwalacz: wejście kontenera w status w tranzycie morskim → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „w tranzycie morskim” powiadomieniem push — wyzwalacz: wejście kontenera w status w tranzycie morskim → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „przeładunek/transshipment” mailem — wyzwalacz: wejście kontenera w status przeładunek/transshipment → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „przeładunek/transshipment” kartą w Teams — wyzwalacz: wejście kontenera w status przeładunek/transshipment → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „przeładunek/transshipment” SMS-em — wyzwalacz: wejście kontenera w status przeładunek/transshipment → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „przeładunek/transshipment” na dashboardzie — wyzwalacz: wejście kontenera w status przeładunek/transshipment → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „przeładunek/transshipment” powiadomieniem push — wyzwalacz: wejście kontenera w status przeładunek/transshipment → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „przybycie do portu (ETA)” mailem — wyzwalacz: wejście kontenera w status przybycie do portu (ETA) → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „przybycie do portu (ETA)” kartą w Teams — wyzwalacz: wejście kontenera w status przybycie do portu (ETA) → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „przybycie do portu (ETA)” SMS-em — wyzwalacz: wejście kontenera w status przybycie do portu (ETA) → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „przybycie do portu (ETA)” na dashboardzie — wyzwalacz: wejście kontenera w status przybycie do portu (ETA) → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „przybycie do portu (ETA)” powiadomieniem push — wyzwalacz: wejście kontenera w status przybycie do portu (ETA) → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „wyładunek ze statku” mailem — wyzwalacz: wejście kontenera w status wyładunek ze statku → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „wyładunek ze statku” kartą w Teams — wyzwalacz: wejście kontenera w status wyładunek ze statku → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „wyładunek ze statku” SMS-em — wyzwalacz: wejście kontenera w status wyładunek ze statku → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „wyładunek ze statku” na dashboardzie — wyzwalacz: wejście kontenera w status wyładunek ze statku → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „wyładunek ze statku” powiadomieniem push — wyzwalacz: wejście kontenera w status wyładunek ze statku → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „składowanie w porcie” mailem — wyzwalacz: wejście kontenera w status składowanie w porcie → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „składowanie w porcie” kartą w Teams — wyzwalacz: wejście kontenera w status składowanie w porcie → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „składowanie w porcie” SMS-em — wyzwalacz: wejście kontenera w status składowanie w porcie → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „składowanie w porcie” na dashboardzie — wyzwalacz: wejście kontenera w status składowanie w porcie → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „składowanie w porcie” powiadomieniem push — wyzwalacz: wejście kontenera w status składowanie w porcie → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „zgłoszenie celne” mailem — wyzwalacz: wejście kontenera w status zgłoszenie celne → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „zgłoszenie celne” kartą w Teams — wyzwalacz: wejście kontenera w status zgłoszenie celne → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „zgłoszenie celne” SMS-em — wyzwalacz: wejście kontenera w status zgłoszenie celne → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „zgłoszenie celne” na dashboardzie — wyzwalacz: wejście kontenera w status zgłoszenie celne → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „zgłoszenie celne” powiadomieniem push — wyzwalacz: wejście kontenera w status zgłoszenie celne → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „odprawa celna w toku” mailem — wyzwalacz: wejście kontenera w status odprawa celna w toku → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „odprawa celna w toku” kartą w Teams — wyzwalacz: wejście kontenera w status odprawa celna w toku → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „odprawa celna w toku” SMS-em — wyzwalacz: wejście kontenera w status odprawa celna w toku → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „odprawa celna w toku” na dashboardzie — wyzwalacz: wejście kontenera w status odprawa celna w toku → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „odprawa celna w toku” powiadomieniem push — wyzwalacz: wejście kontenera w status odprawa celna w toku → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „zwolnienie celne” mailem — wyzwalacz: wejście kontenera w status zwolnienie celne → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „zwolnienie celne” kartą w Teams — wyzwalacz: wejście kontenera w status zwolnienie celne → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „zwolnienie celne” SMS-em — wyzwalacz: wejście kontenera w status zwolnienie celne → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „zwolnienie celne” na dashboardzie — wyzwalacz: wejście kontenera w status zwolnienie celne → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „zwolnienie celne” powiadomieniem push — wyzwalacz: wejście kontenera w status zwolnienie celne → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „awizacja dostawy” mailem — wyzwalacz: wejście kontenera w status awizacja dostawy → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „awizacja dostawy” kartą w Teams — wyzwalacz: wejście kontenera w status awizacja dostawy → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „awizacja dostawy” SMS-em — wyzwalacz: wejście kontenera w status awizacja dostawy → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „awizacja dostawy” na dashboardzie — wyzwalacz: wejście kontenera w status awizacja dostawy → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „awizacja dostawy” powiadomieniem push — wyzwalacz: wejście kontenera w status awizacja dostawy → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „transport z portu do magazynu” mailem — wyzwalacz: wejście kontenera w status transport z portu do magazynu → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „transport z portu do magazynu” kartą w Teams — wyzwalacz: wejście kontenera w status transport z portu do magazynu → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „transport z portu do magazynu” SMS-em — wyzwalacz: wejście kontenera w status transport z portu do magazynu → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „transport z portu do magazynu” na dashboardzie — wyzwalacz: wejście kontenera w status transport z portu do magazynu → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „transport z portu do magazynu” powiadomieniem push — wyzwalacz: wejście kontenera w status transport z portu do magazynu → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „zgłoszenie na bramie magazynu” mailem — wyzwalacz: wejście kontenera w status zgłoszenie na bramie magazynu → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „zgłoszenie na bramie magazynu” kartą w Teams — wyzwalacz: wejście kontenera w status zgłoszenie na bramie magazynu → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „zgłoszenie na bramie magazynu” SMS-em — wyzwalacz: wejście kontenera w status zgłoszenie na bramie magazynu → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „zgłoszenie na bramie magazynu” na dashboardzie — wyzwalacz: wejście kontenera w status zgłoszenie na bramie magazynu → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „zgłoszenie na bramie magazynu” powiadomieniem push — wyzwalacz: wejście kontenera w status zgłoszenie na bramie magazynu → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „rozładunek kontenera” mailem — wyzwalacz: wejście kontenera w status rozładunek kontenera → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „rozładunek kontenera” kartą w Teams — wyzwalacz: wejście kontenera w status rozładunek kontenera → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „rozładunek kontenera” SMS-em — wyzwalacz: wejście kontenera w status rozładunek kontenera → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „rozładunek kontenera” na dashboardzie — wyzwalacz: wejście kontenera w status rozładunek kontenera → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „rozładunek kontenera” powiadomieniem push — wyzwalacz: wejście kontenera w status rozładunek kontenera → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „kontrola jakości towaru” mailem — wyzwalacz: wejście kontenera w status kontrola jakości towaru → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „kontrola jakości towaru” kartą w Teams — wyzwalacz: wejście kontenera w status kontrola jakości towaru → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „kontrola jakości towaru” SMS-em — wyzwalacz: wejście kontenera w status kontrola jakości towaru → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „kontrola jakości towaru” na dashboardzie — wyzwalacz: wejście kontenera w status kontrola jakości towaru → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „kontrola jakości towaru” powiadomieniem push — wyzwalacz: wejście kontenera w status kontrola jakości towaru → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „przyjęcie na stan” mailem — wyzwalacz: wejście kontenera w status przyjęcie na stan → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „przyjęcie na stan” kartą w Teams — wyzwalacz: wejście kontenera w status przyjęcie na stan → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „przyjęcie na stan” SMS-em — wyzwalacz: wejście kontenera w status przyjęcie na stan → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „przyjęcie na stan” na dashboardzie — wyzwalacz: wejście kontenera w status przyjęcie na stan → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „przyjęcie na stan” powiadomieniem push — wyzwalacz: wejście kontenera w status przyjęcie na stan → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „zwrot pustego kontenera” mailem — wyzwalacz: wejście kontenera w status zwrot pustego kontenera → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „zwrot pustego kontenera” kartą w Teams — wyzwalacz: wejście kontenera w status zwrot pustego kontenera → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „zwrot pustego kontenera” SMS-em — wyzwalacz: wejście kontenera w status zwrot pustego kontenera → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „zwrot pustego kontenera” na dashboardzie — wyzwalacz: wejście kontenera w status zwrot pustego kontenera → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „zwrot pustego kontenera” powiadomieniem push — wyzwalacz: wejście kontenera w status zwrot pustego kontenera → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „rozliczenie kosztów kontenera” mailem — wyzwalacz: wejście kontenera w status rozliczenie kosztów kontenera → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „rozliczenie kosztów kontenera” kartą w Teams — wyzwalacz: wejście kontenera w status rozliczenie kosztów kontenera → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „rozliczenie kosztów kontenera” SMS-em — wyzwalacz: wejście kontenera w status rozliczenie kosztów kontenera → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „rozliczenie kosztów kontenera” na dashboardzie — wyzwalacz: wejście kontenera w status rozliczenie kosztów kontenera → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „rozliczenie kosztów kontenera” powiadomieniem push — wyzwalacz: wejście kontenera w status rozliczenie kosztów kontenera → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert statusu „zamknięcie sprawy kontenera” mailem — wyzwalacz: wejście kontenera w status zamknięcie sprawy kontenera → powiadomienie mailem.
- 🔲 **[Teams]** Alert statusu „zamknięcie sprawy kontenera” kartą w Teams — wyzwalacz: wejście kontenera w status zamknięcie sprawy kontenera → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert statusu „zamknięcie sprawy kontenera” SMS-em — wyzwalacz: wejście kontenera w status zamknięcie sprawy kontenera → powiadomienie SMS-em.
- 🔲 **[Python]** Alert statusu „zamknięcie sprawy kontenera” na dashboardzie — wyzwalacz: wejście kontenera w status zamknięcie sprawy kontenera → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert statusu „zamknięcie sprawy kontenera” powiadomieniem push — wyzwalacz: wejście kontenera w status zamknięcie sprawy kontenera → powiadomienie powiadomieniem push.

### 2.8 Metryki i widoki per etap cyklu
- 🔲 **[Feature]** Widok kontenerów w statusie „potwierdzenie bookingu u armatora” — filtr kolejki pokazujący wyłącznie kontenery na etapie potwierdzenie bookingu u armatora z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „potwierdzenie bookingu u armatora” — ile dni kontener tkwi na etapie potwierdzenie bookingu u armatora; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „potwierdzenie bookingu u armatora” — KPI: mediana i p90 czasu trwania etapu potwierdzenie bookingu u armatora per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „załadunek w porcie nadania” — filtr kolejki pokazujący wyłącznie kontenery na etapie załadunek w porcie nadania z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „załadunek w porcie nadania” — ile dni kontener tkwi na etapie załadunek w porcie nadania; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „załadunek w porcie nadania” — KPI: mediana i p90 czasu trwania etapu załadunek w porcie nadania per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „wypłynięcie statku (ETD)” — filtr kolejki pokazujący wyłącznie kontenery na etapie wypłynięcie statku (ETD) z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „wypłynięcie statku (ETD)” — ile dni kontener tkwi na etapie wypłynięcie statku (ETD); alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „wypłynięcie statku (ETD)” — KPI: mediana i p90 czasu trwania etapu wypłynięcie statku (ETD) per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „w tranzycie morskim” — filtr kolejki pokazujący wyłącznie kontenery na etapie w tranzycie morskim z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „w tranzycie morskim” — ile dni kontener tkwi na etapie w tranzycie morskim; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „w tranzycie morskim” — KPI: mediana i p90 czasu trwania etapu w tranzycie morskim per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „przeładunek/transshipment” — filtr kolejki pokazujący wyłącznie kontenery na etapie przeładunek/transshipment z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „przeładunek/transshipment” — ile dni kontener tkwi na etapie przeładunek/transshipment; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „przeładunek/transshipment” — KPI: mediana i p90 czasu trwania etapu przeładunek/transshipment per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „przybycie do portu (ETA)” — filtr kolejki pokazujący wyłącznie kontenery na etapie przybycie do portu (ETA) z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „przybycie do portu (ETA)” — ile dni kontener tkwi na etapie przybycie do portu (ETA); alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „przybycie do portu (ETA)” — KPI: mediana i p90 czasu trwania etapu przybycie do portu (ETA) per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „wyładunek ze statku” — filtr kolejki pokazujący wyłącznie kontenery na etapie wyładunek ze statku z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „wyładunek ze statku” — ile dni kontener tkwi na etapie wyładunek ze statku; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „wyładunek ze statku” — KPI: mediana i p90 czasu trwania etapu wyładunek ze statku per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „składowanie w porcie” — filtr kolejki pokazujący wyłącznie kontenery na etapie składowanie w porcie z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „składowanie w porcie” — ile dni kontener tkwi na etapie składowanie w porcie; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „składowanie w porcie” — KPI: mediana i p90 czasu trwania etapu składowanie w porcie per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „zgłoszenie celne” — filtr kolejki pokazujący wyłącznie kontenery na etapie zgłoszenie celne z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „zgłoszenie celne” — ile dni kontener tkwi na etapie zgłoszenie celne; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „zgłoszenie celne” — KPI: mediana i p90 czasu trwania etapu zgłoszenie celne per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „odprawa celna w toku” — filtr kolejki pokazujący wyłącznie kontenery na etapie odprawa celna w toku z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „odprawa celna w toku” — ile dni kontener tkwi na etapie odprawa celna w toku; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „odprawa celna w toku” — KPI: mediana i p90 czasu trwania etapu odprawa celna w toku per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „zwolnienie celne” — filtr kolejki pokazujący wyłącznie kontenery na etapie zwolnienie celne z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „zwolnienie celne” — ile dni kontener tkwi na etapie zwolnienie celne; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „zwolnienie celne” — KPI: mediana i p90 czasu trwania etapu zwolnienie celne per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „awizacja dostawy” — filtr kolejki pokazujący wyłącznie kontenery na etapie awizacja dostawy z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „awizacja dostawy” — ile dni kontener tkwi na etapie awizacja dostawy; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „awizacja dostawy” — KPI: mediana i p90 czasu trwania etapu awizacja dostawy per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „transport z portu do magazynu” — filtr kolejki pokazujący wyłącznie kontenery na etapie transport z portu do magazynu z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „transport z portu do magazynu” — ile dni kontener tkwi na etapie transport z portu do magazynu; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „transport z portu do magazynu” — KPI: mediana i p90 czasu trwania etapu transport z portu do magazynu per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „zgłoszenie na bramie magazynu” — filtr kolejki pokazujący wyłącznie kontenery na etapie zgłoszenie na bramie magazynu z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „zgłoszenie na bramie magazynu” — ile dni kontener tkwi na etapie zgłoszenie na bramie magazynu; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „zgłoszenie na bramie magazynu” — KPI: mediana i p90 czasu trwania etapu zgłoszenie na bramie magazynu per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „rozładunek kontenera” — filtr kolejki pokazujący wyłącznie kontenery na etapie rozładunek kontenera z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „rozładunek kontenera” — ile dni kontener tkwi na etapie rozładunek kontenera; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „rozładunek kontenera” — KPI: mediana i p90 czasu trwania etapu rozładunek kontenera per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „kontrola jakości towaru” — filtr kolejki pokazujący wyłącznie kontenery na etapie kontrola jakości towaru z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „kontrola jakości towaru” — ile dni kontener tkwi na etapie kontrola jakości towaru; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „kontrola jakości towaru” — KPI: mediana i p90 czasu trwania etapu kontrola jakości towaru per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „przyjęcie na stan” — filtr kolejki pokazujący wyłącznie kontenery na etapie przyjęcie na stan z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „przyjęcie na stan” — ile dni kontener tkwi na etapie przyjęcie na stan; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „przyjęcie na stan” — KPI: mediana i p90 czasu trwania etapu przyjęcie na stan per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „zwrot pustego kontenera” — filtr kolejki pokazujący wyłącznie kontenery na etapie zwrot pustego kontenera z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „zwrot pustego kontenera” — ile dni kontener tkwi na etapie zwrot pustego kontenera; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „zwrot pustego kontenera” — KPI: mediana i p90 czasu trwania etapu zwrot pustego kontenera per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „rozliczenie kosztów kontenera” — filtr kolejki pokazujący wyłącznie kontenery na etapie rozliczenie kosztów kontenera z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „rozliczenie kosztów kontenera” — ile dni kontener tkwi na etapie rozliczenie kosztów kontenera; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „rozliczenie kosztów kontenera” — KPI: mediana i p90 czasu trwania etapu rozliczenie kosztów kontenera per trasa.
- 🔲 **[Feature]** Widok kontenerów w statusie „zamknięcie sprawy kontenera” — filtr kolejki pokazujący wyłącznie kontenery na etapie zamknięcie sprawy kontenera z licznikiem.
- 🔲 **[Python]** Licznik dni w statusie „zamknięcie sprawy kontenera” — ile dni kontener tkwi na etapie zamknięcie sprawy kontenera; alert po przekroczeniu normy.
- 🔲 **[Python]** Średni czas etapu „zamknięcie sprawy kontenera” — KPI: mediana i p90 czasu trwania etapu zamknięcie sprawy kontenera per trasa.

### 2.9 Benchmarking i ryzyko per wymiar
- 🔲 **[PowerBI]** Benchmarking opóźnień per dostawcy — ranking średniego opóźnienia ETA w podziale na dostawcy.
- 🔲 **[Python]** Ryzyko demurrage per dostawcy — agregacja ekspozycji na koszty postoju w podziale na dostawcy.
- 🔲 **[PowerBI]** Benchmarking opóźnień per spedytora — ranking średniego opóźnienia ETA w podziale na spedytora.
- 🔲 **[Python]** Ryzyko demurrage per spedytora — agregacja ekspozycji na koszty postoju w podziale na spedytora.
- 🔲 **[PowerBI]** Benchmarking opóźnień per przewoźnika — ranking średniego opóźnienia ETA w podziale na przewoźnika.
- 🔲 **[Python]** Ryzyko demurrage per przewoźnika — agregacja ekspozycji na koszty postoju w podziale na przewoźnika.
- 🔲 **[PowerBI]** Benchmarking opóźnień per armatora — ranking średniego opóźnienia ETA w podziale na armatora.
- 🔲 **[Python]** Ryzyko demurrage per armatora — agregacja ekspozycji na koszty postoju w podziale na armatora.
- 🔲 **[PowerBI]** Benchmarking opóźnień per portu — ranking średniego opóźnienia ETA w podziale na portu.
- 🔲 **[Python]** Ryzyko demurrage per portu — agregacja ekspozycji na koszty postoju w podziale na portu.
- 🔲 **[PowerBI]** Benchmarking opóźnień per magazynu — ranking średniego opóźnienia ETA w podziale na magazynu.
- 🔲 **[Python]** Ryzyko demurrage per magazynu — agregacja ekspozycji na koszty postoju w podziale na magazynu.
- 🔲 **[PowerBI]** Benchmarking opóźnień per klienta — ranking średniego opóźnienia ETA w podziale na klienta.
- 🔲 **[Python]** Ryzyko demurrage per klienta — agregacja ekspozycji na koszty postoju w podziale na klienta.
- 🔲 **[PowerBI]** Benchmarking opóźnień per materiału — ranking średniego opóźnienia ETA w podziale na materiału.
- 🔲 **[Python]** Ryzyko demurrage per materiału — agregacja ekspozycji na koszty postoju w podziale na materiału.
- 🔲 **[PowerBI]** Benchmarking opóźnień per kraju — ranking średniego opóźnienia ETA w podziale na kraju.
- 🔲 **[Python]** Ryzyko demurrage per kraju — agregacja ekspozycji na koszty postoju w podziale na kraju.
- 🔲 **[PowerBI]** Benchmarking opóźnień per trasy — ranking średniego opóźnienia ETA w podziale na trasy.
- 🔲 **[Python]** Ryzyko demurrage per trasy — agregacja ekspozycji na koszty postoju w podziale na trasy.
- 🔲 **[PowerBI]** Benchmarking opóźnień per typu kontenera — ranking średniego opóźnienia ETA w podziale na typu kontenera.
- 🔲 **[Python]** Ryzyko demurrage per typu kontenera — agregacja ekspozycji na koszty postoju w podziale na typu kontenera.
- 🔲 **[PowerBI]** Benchmarking opóźnień per agencji celnej — ranking średniego opóźnienia ETA w podziale na agencji celnej.
- 🔲 **[Python]** Ryzyko demurrage per agencji celnej — agregacja ekspozycji na koszty postoju w podziale na agencji celnej.

### 2.10 Alerty free-time (próg × kanał)
- 🔲 **[Python]** Alert free-time T-7 dnia mailem — na 7 dni przed końcem dni wolnych → powiadomienie mailem.
- 🔲 **[Python]** Alert free-time T-3 dnia mailem — na 3 dni przed końcem dni wolnych → powiadomienie mailem.
- 🔲 **[Python]** Alert free-time T-1 dnia mailem — na 1 dni przed końcem dni wolnych → powiadomienie mailem.
- 🔲 **[Teams]** Alert free-time T-7 dnia kartą w Teams — na 7 dni przed końcem dni wolnych → powiadomienie kartą w Teams.
- 🔲 **[Teams]** Alert free-time T-3 dnia kartą w Teams — na 3 dni przed końcem dni wolnych → powiadomienie kartą w Teams.
- 🔲 **[Teams]** Alert free-time T-1 dnia kartą w Teams — na 1 dni przed końcem dni wolnych → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert free-time T-7 dnia SMS-em — na 7 dni przed końcem dni wolnych → powiadomienie SMS-em.
- 🔲 **[Python]** Alert free-time T-3 dnia SMS-em — na 3 dni przed końcem dni wolnych → powiadomienie SMS-em.
- 🔲 **[Python]** Alert free-time T-1 dnia SMS-em — na 1 dni przed końcem dni wolnych → powiadomienie SMS-em.
- 🔲 **[Python]** Alert free-time T-7 dnia na dashboardzie — na 7 dni przed końcem dni wolnych → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert free-time T-3 dnia na dashboardzie — na 3 dni przed końcem dni wolnych → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert free-time T-1 dnia na dashboardzie — na 1 dni przed końcem dni wolnych → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert free-time T-7 dnia powiadomieniem push — na 7 dni przed końcem dni wolnych → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert free-time T-3 dnia powiadomieniem push — na 3 dni przed końcem dni wolnych → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert free-time T-1 dnia powiadomieniem push — na 1 dni przed końcem dni wolnych → powiadomienie powiadomieniem push.

### 2.11 Adresaci alertów per status (rola)
- 🔲 **[Feature]** Adresowanie alertu „potwierdzenie bookingu u armatora” do zakupowca — reguła: przy wejściu w etap potwierdzenie bookingu u armatora powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „potwierdzenie bookingu u armatora” do spedytora — reguła: przy wejściu w etap potwierdzenie bookingu u armatora powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „potwierdzenie bookingu u armatora” do magazyniera — reguła: przy wejściu w etap potwierdzenie bookingu u armatora powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „potwierdzenie bookingu u armatora” do agencji celnej — reguła: przy wejściu w etap potwierdzenie bookingu u armatora powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „potwierdzenie bookingu u armatora” do kierownika — reguła: przy wejściu w etap potwierdzenie bookingu u armatora powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „potwierdzenie bookingu u armatora” do klienta — reguła: przy wejściu w etap potwierdzenie bookingu u armatora powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „potwierdzenie bookingu u armatora” do administratora — reguła: przy wejściu w etap potwierdzenie bookingu u armatora powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „załadunek w porcie nadania” do zakupowca — reguła: przy wejściu w etap załadunek w porcie nadania powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „załadunek w porcie nadania” do spedytora — reguła: przy wejściu w etap załadunek w porcie nadania powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „załadunek w porcie nadania” do magazyniera — reguła: przy wejściu w etap załadunek w porcie nadania powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „załadunek w porcie nadania” do agencji celnej — reguła: przy wejściu w etap załadunek w porcie nadania powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „załadunek w porcie nadania” do kierownika — reguła: przy wejściu w etap załadunek w porcie nadania powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „załadunek w porcie nadania” do klienta — reguła: przy wejściu w etap załadunek w porcie nadania powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „załadunek w porcie nadania” do administratora — reguła: przy wejściu w etap załadunek w porcie nadania powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „wypłynięcie statku (ETD)” do zakupowca — reguła: przy wejściu w etap wypłynięcie statku (ETD) powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „wypłynięcie statku (ETD)” do spedytora — reguła: przy wejściu w etap wypłynięcie statku (ETD) powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „wypłynięcie statku (ETD)” do magazyniera — reguła: przy wejściu w etap wypłynięcie statku (ETD) powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „wypłynięcie statku (ETD)” do agencji celnej — reguła: przy wejściu w etap wypłynięcie statku (ETD) powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „wypłynięcie statku (ETD)” do kierownika — reguła: przy wejściu w etap wypłynięcie statku (ETD) powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „wypłynięcie statku (ETD)” do klienta — reguła: przy wejściu w etap wypłynięcie statku (ETD) powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „wypłynięcie statku (ETD)” do administratora — reguła: przy wejściu w etap wypłynięcie statku (ETD) powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „w tranzycie morskim” do zakupowca — reguła: przy wejściu w etap w tranzycie morskim powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „w tranzycie morskim” do spedytora — reguła: przy wejściu w etap w tranzycie morskim powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „w tranzycie morskim” do magazyniera — reguła: przy wejściu w etap w tranzycie morskim powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „w tranzycie morskim” do agencji celnej — reguła: przy wejściu w etap w tranzycie morskim powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „w tranzycie morskim” do kierownika — reguła: przy wejściu w etap w tranzycie morskim powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „w tranzycie morskim” do klienta — reguła: przy wejściu w etap w tranzycie morskim powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „w tranzycie morskim” do administratora — reguła: przy wejściu w etap w tranzycie morskim powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „przeładunek/transshipment” do zakupowca — reguła: przy wejściu w etap przeładunek/transshipment powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „przeładunek/transshipment” do spedytora — reguła: przy wejściu w etap przeładunek/transshipment powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „przeładunek/transshipment” do magazyniera — reguła: przy wejściu w etap przeładunek/transshipment powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „przeładunek/transshipment” do agencji celnej — reguła: przy wejściu w etap przeładunek/transshipment powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „przeładunek/transshipment” do kierownika — reguła: przy wejściu w etap przeładunek/transshipment powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „przeładunek/transshipment” do klienta — reguła: przy wejściu w etap przeładunek/transshipment powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „przeładunek/transshipment” do administratora — reguła: przy wejściu w etap przeładunek/transshipment powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „przybycie do portu (ETA)” do zakupowca — reguła: przy wejściu w etap przybycie do portu (ETA) powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „przybycie do portu (ETA)” do spedytora — reguła: przy wejściu w etap przybycie do portu (ETA) powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „przybycie do portu (ETA)” do magazyniera — reguła: przy wejściu w etap przybycie do portu (ETA) powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „przybycie do portu (ETA)” do agencji celnej — reguła: przy wejściu w etap przybycie do portu (ETA) powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „przybycie do portu (ETA)” do kierownika — reguła: przy wejściu w etap przybycie do portu (ETA) powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „przybycie do portu (ETA)” do klienta — reguła: przy wejściu w etap przybycie do portu (ETA) powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „przybycie do portu (ETA)” do administratora — reguła: przy wejściu w etap przybycie do portu (ETA) powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „wyładunek ze statku” do zakupowca — reguła: przy wejściu w etap wyładunek ze statku powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „wyładunek ze statku” do spedytora — reguła: przy wejściu w etap wyładunek ze statku powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „wyładunek ze statku” do magazyniera — reguła: przy wejściu w etap wyładunek ze statku powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „wyładunek ze statku” do agencji celnej — reguła: przy wejściu w etap wyładunek ze statku powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „wyładunek ze statku” do kierownika — reguła: przy wejściu w etap wyładunek ze statku powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „wyładunek ze statku” do klienta — reguła: przy wejściu w etap wyładunek ze statku powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „wyładunek ze statku” do administratora — reguła: przy wejściu w etap wyładunek ze statku powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „składowanie w porcie” do zakupowca — reguła: przy wejściu w etap składowanie w porcie powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „składowanie w porcie” do spedytora — reguła: przy wejściu w etap składowanie w porcie powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „składowanie w porcie” do magazyniera — reguła: przy wejściu w etap składowanie w porcie powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „składowanie w porcie” do agencji celnej — reguła: przy wejściu w etap składowanie w porcie powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „składowanie w porcie” do kierownika — reguła: przy wejściu w etap składowanie w porcie powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „składowanie w porcie” do klienta — reguła: przy wejściu w etap składowanie w porcie powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „składowanie w porcie” do administratora — reguła: przy wejściu w etap składowanie w porcie powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie celne” do zakupowca — reguła: przy wejściu w etap zgłoszenie celne powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie celne” do spedytora — reguła: przy wejściu w etap zgłoszenie celne powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie celne” do magazyniera — reguła: przy wejściu w etap zgłoszenie celne powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie celne” do agencji celnej — reguła: przy wejściu w etap zgłoszenie celne powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie celne” do kierownika — reguła: przy wejściu w etap zgłoszenie celne powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie celne” do klienta — reguła: przy wejściu w etap zgłoszenie celne powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie celne” do administratora — reguła: przy wejściu w etap zgłoszenie celne powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „odprawa celna w toku” do zakupowca — reguła: przy wejściu w etap odprawa celna w toku powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „odprawa celna w toku” do spedytora — reguła: przy wejściu w etap odprawa celna w toku powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „odprawa celna w toku” do magazyniera — reguła: przy wejściu w etap odprawa celna w toku powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „odprawa celna w toku” do agencji celnej — reguła: przy wejściu w etap odprawa celna w toku powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „odprawa celna w toku” do kierownika — reguła: przy wejściu w etap odprawa celna w toku powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „odprawa celna w toku” do klienta — reguła: przy wejściu w etap odprawa celna w toku powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „odprawa celna w toku” do administratora — reguła: przy wejściu w etap odprawa celna w toku powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „zwolnienie celne” do zakupowca — reguła: przy wejściu w etap zwolnienie celne powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „zwolnienie celne” do spedytora — reguła: przy wejściu w etap zwolnienie celne powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „zwolnienie celne” do magazyniera — reguła: przy wejściu w etap zwolnienie celne powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „zwolnienie celne” do agencji celnej — reguła: przy wejściu w etap zwolnienie celne powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „zwolnienie celne” do kierownika — reguła: przy wejściu w etap zwolnienie celne powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „zwolnienie celne” do klienta — reguła: przy wejściu w etap zwolnienie celne powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „zwolnienie celne” do administratora — reguła: przy wejściu w etap zwolnienie celne powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „awizacja dostawy” do zakupowca — reguła: przy wejściu w etap awizacja dostawy powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „awizacja dostawy” do spedytora — reguła: przy wejściu w etap awizacja dostawy powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „awizacja dostawy” do magazyniera — reguła: przy wejściu w etap awizacja dostawy powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „awizacja dostawy” do agencji celnej — reguła: przy wejściu w etap awizacja dostawy powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „awizacja dostawy” do kierownika — reguła: przy wejściu w etap awizacja dostawy powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „awizacja dostawy” do klienta — reguła: przy wejściu w etap awizacja dostawy powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „awizacja dostawy” do administratora — reguła: przy wejściu w etap awizacja dostawy powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „transport z portu do magazynu” do zakupowca — reguła: przy wejściu w etap transport z portu do magazynu powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „transport z portu do magazynu” do spedytora — reguła: przy wejściu w etap transport z portu do magazynu powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „transport z portu do magazynu” do magazyniera — reguła: przy wejściu w etap transport z portu do magazynu powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „transport z portu do magazynu” do agencji celnej — reguła: przy wejściu w etap transport z portu do magazynu powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „transport z portu do magazynu” do kierownika — reguła: przy wejściu w etap transport z portu do magazynu powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „transport z portu do magazynu” do klienta — reguła: przy wejściu w etap transport z portu do magazynu powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „transport z portu do magazynu” do administratora — reguła: przy wejściu w etap transport z portu do magazynu powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie na bramie magazynu” do zakupowca — reguła: przy wejściu w etap zgłoszenie na bramie magazynu powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie na bramie magazynu” do spedytora — reguła: przy wejściu w etap zgłoszenie na bramie magazynu powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie na bramie magazynu” do magazyniera — reguła: przy wejściu w etap zgłoszenie na bramie magazynu powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie na bramie magazynu” do agencji celnej — reguła: przy wejściu w etap zgłoszenie na bramie magazynu powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie na bramie magazynu” do kierownika — reguła: przy wejściu w etap zgłoszenie na bramie magazynu powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie na bramie magazynu” do klienta — reguła: przy wejściu w etap zgłoszenie na bramie magazynu powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „zgłoszenie na bramie magazynu” do administratora — reguła: przy wejściu w etap zgłoszenie na bramie magazynu powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „rozładunek kontenera” do zakupowca — reguła: przy wejściu w etap rozładunek kontenera powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „rozładunek kontenera” do spedytora — reguła: przy wejściu w etap rozładunek kontenera powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „rozładunek kontenera” do magazyniera — reguła: przy wejściu w etap rozładunek kontenera powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „rozładunek kontenera” do agencji celnej — reguła: przy wejściu w etap rozładunek kontenera powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „rozładunek kontenera” do kierownika — reguła: przy wejściu w etap rozładunek kontenera powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „rozładunek kontenera” do klienta — reguła: przy wejściu w etap rozładunek kontenera powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „rozładunek kontenera” do administratora — reguła: przy wejściu w etap rozładunek kontenera powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „kontrola jakości towaru” do zakupowca — reguła: przy wejściu w etap kontrola jakości towaru powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „kontrola jakości towaru” do spedytora — reguła: przy wejściu w etap kontrola jakości towaru powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „kontrola jakości towaru” do magazyniera — reguła: przy wejściu w etap kontrola jakości towaru powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „kontrola jakości towaru” do agencji celnej — reguła: przy wejściu w etap kontrola jakości towaru powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „kontrola jakości towaru” do kierownika — reguła: przy wejściu w etap kontrola jakości towaru powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „kontrola jakości towaru” do klienta — reguła: przy wejściu w etap kontrola jakości towaru powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „kontrola jakości towaru” do administratora — reguła: przy wejściu w etap kontrola jakości towaru powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „przyjęcie na stan” do zakupowca — reguła: przy wejściu w etap przyjęcie na stan powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „przyjęcie na stan” do spedytora — reguła: przy wejściu w etap przyjęcie na stan powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „przyjęcie na stan” do magazyniera — reguła: przy wejściu w etap przyjęcie na stan powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „przyjęcie na stan” do agencji celnej — reguła: przy wejściu w etap przyjęcie na stan powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „przyjęcie na stan” do kierownika — reguła: przy wejściu w etap przyjęcie na stan powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „przyjęcie na stan” do klienta — reguła: przy wejściu w etap przyjęcie na stan powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „przyjęcie na stan” do administratora — reguła: przy wejściu w etap przyjęcie na stan powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „zwrot pustego kontenera” do zakupowca — reguła: przy wejściu w etap zwrot pustego kontenera powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „zwrot pustego kontenera” do spedytora — reguła: przy wejściu w etap zwrot pustego kontenera powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „zwrot pustego kontenera” do magazyniera — reguła: przy wejściu w etap zwrot pustego kontenera powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „zwrot pustego kontenera” do agencji celnej — reguła: przy wejściu w etap zwrot pustego kontenera powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „zwrot pustego kontenera” do kierownika — reguła: przy wejściu w etap zwrot pustego kontenera powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „zwrot pustego kontenera” do klienta — reguła: przy wejściu w etap zwrot pustego kontenera powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „zwrot pustego kontenera” do administratora — reguła: przy wejściu w etap zwrot pustego kontenera powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „rozliczenie kosztów kontenera” do zakupowca — reguła: przy wejściu w etap rozliczenie kosztów kontenera powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „rozliczenie kosztów kontenera” do spedytora — reguła: przy wejściu w etap rozliczenie kosztów kontenera powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „rozliczenie kosztów kontenera” do magazyniera — reguła: przy wejściu w etap rozliczenie kosztów kontenera powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „rozliczenie kosztów kontenera” do agencji celnej — reguła: przy wejściu w etap rozliczenie kosztów kontenera powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „rozliczenie kosztów kontenera” do kierownika — reguła: przy wejściu w etap rozliczenie kosztów kontenera powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „rozliczenie kosztów kontenera” do klienta — reguła: przy wejściu w etap rozliczenie kosztów kontenera powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „rozliczenie kosztów kontenera” do administratora — reguła: przy wejściu w etap rozliczenie kosztów kontenera powiadom administratora.
- 🔲 **[Feature]** Adresowanie alertu „zamknięcie sprawy kontenera” do zakupowca — reguła: przy wejściu w etap zamknięcie sprawy kontenera powiadom zakupowca.
- 🔲 **[Feature]** Adresowanie alertu „zamknięcie sprawy kontenera” do spedytora — reguła: przy wejściu w etap zamknięcie sprawy kontenera powiadom spedytora.
- 🔲 **[Feature]** Adresowanie alertu „zamknięcie sprawy kontenera” do magazyniera — reguła: przy wejściu w etap zamknięcie sprawy kontenera powiadom magazyniera.
- 🔲 **[Feature]** Adresowanie alertu „zamknięcie sprawy kontenera” do agencji celnej — reguła: przy wejściu w etap zamknięcie sprawy kontenera powiadom agencji celnej.
- 🔲 **[Feature]** Adresowanie alertu „zamknięcie sprawy kontenera” do kierownika — reguła: przy wejściu w etap zamknięcie sprawy kontenera powiadom kierownika.
- 🔲 **[Feature]** Adresowanie alertu „zamknięcie sprawy kontenera” do klienta — reguła: przy wejściu w etap zamknięcie sprawy kontenera powiadom klienta.
- 🔲 **[Feature]** Adresowanie alertu „zamknięcie sprawy kontenera” do administratora — reguła: przy wejściu w etap zamknięcie sprawy kontenera powiadom administratora.

### 2.12 Auto-akcje per etap
- 🔲 **[Python]** Auto-akcja przy etapie „potwierdzenie bookingu”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap potwierdzenie bookingu → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „potwierdzenie bookingu”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap potwierdzenie bookingu → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „potwierdzenie bookingu”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap potwierdzenie bookingu → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „załadunek”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap załadunek → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „załadunek”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap załadunek → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „załadunek”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap załadunek → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „wypłynięcie (ETD)”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap wypłynięcie (ETD) → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „wypłynięcie (ETD)”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap wypłynięcie (ETD) → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „wypłynięcie (ETD)”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap wypłynięcie (ETD) → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „tranzyt morski”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap tranzyt morski → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „tranzyt morski”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap tranzyt morski → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „tranzyt morski”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap tranzyt morski → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „przeładunek”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap przeładunek → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „przeładunek”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap przeładunek → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „przeładunek”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap przeładunek → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „przybycie (ETA)”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap przybycie (ETA) → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „przybycie (ETA)”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap przybycie (ETA) → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „przybycie (ETA)”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap przybycie (ETA) → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „wyładunek ze statku”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap wyładunek ze statku → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „wyładunek ze statku”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap wyładunek ze statku → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „wyładunek ze statku”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap wyładunek ze statku → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „składowanie w porcie”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap składowanie w porcie → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „składowanie w porcie”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap składowanie w porcie → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „składowanie w porcie”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap składowanie w porcie → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „zgłoszenie celne”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap zgłoszenie celne → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „zgłoszenie celne”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap zgłoszenie celne → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „zgłoszenie celne”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap zgłoszenie celne → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „odprawa w toku”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap odprawa w toku → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „odprawa w toku”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap odprawa w toku → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „odprawa w toku”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap odprawa w toku → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „zwolnienie celne”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap zwolnienie celne → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „zwolnienie celne”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap zwolnienie celne → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „zwolnienie celne”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap zwolnienie celne → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „awizacja”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap awizacja → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „awizacja”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap awizacja → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „awizacja”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap awizacja → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „transport z portu”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap transport z portu → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „transport z portu”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap transport z portu → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „transport z portu”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap transport z portu → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „brama magazynu”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap brama magazynu → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „brama magazynu”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap brama magazynu → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „brama magazynu”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap brama magazynu → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „rozładunek”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap rozładunek → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „rozładunek”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap rozładunek → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „rozładunek”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap rozładunek → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „kontrola jakości”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap kontrola jakości → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „kontrola jakości”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap kontrola jakości → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „kontrola jakości”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap kontrola jakości → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „przyjęcie na stan”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap przyjęcie na stan → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „przyjęcie na stan”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap przyjęcie na stan → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „przyjęcie na stan”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap przyjęcie na stan → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „zwrot pustego”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap zwrot pustego → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „zwrot pustego”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap zwrot pustego → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „zwrot pustego”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap zwrot pustego → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „rozliczenie”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap rozliczenie → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „rozliczenie”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap rozliczenie → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „rozliczenie”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap rozliczenie → przelicz ryzyko demurrage.
- 🔲 **[Python]** Auto-akcja przy etapie „zamknięcie”: utwórz zadanie operacyjne — wyzwalacz wejścia w etap zamknięcie → utwórz zadanie operacyjne.
- 🔲 **[Python]** Auto-akcja przy etapie „zamknięcie”: zaktualizuj ETA w portalu klienta — wyzwalacz wejścia w etap zamknięcie → zaktualizuj ETA w portalu klienta.
- 🔲 **[Python]** Auto-akcja przy etapie „zamknięcie”: przelicz ryzyko demurrage — wyzwalacz wejścia w etap zamknięcie → przelicz ryzyko demurrage.

### 2.13 Konfiguracja SLA per etap
- 🔲 **[Feature]** Konfiguracja SLA etapu „potwierdzenie bookingu” — ustaw dopuszczalny czas trwania etapu potwierdzenie bookingu i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „załadunek” — ustaw dopuszczalny czas trwania etapu załadunek i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „wypłynięcie (ETD)” — ustaw dopuszczalny czas trwania etapu wypłynięcie (ETD) i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „tranzyt morski” — ustaw dopuszczalny czas trwania etapu tranzyt morski i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „przeładunek” — ustaw dopuszczalny czas trwania etapu przeładunek i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „przybycie (ETA)” — ustaw dopuszczalny czas trwania etapu przybycie (ETA) i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „wyładunek ze statku” — ustaw dopuszczalny czas trwania etapu wyładunek ze statku i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „składowanie w porcie” — ustaw dopuszczalny czas trwania etapu składowanie w porcie i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „zgłoszenie celne” — ustaw dopuszczalny czas trwania etapu zgłoszenie celne i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „odprawa w toku” — ustaw dopuszczalny czas trwania etapu odprawa w toku i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „zwolnienie celne” — ustaw dopuszczalny czas trwania etapu zwolnienie celne i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „awizacja” — ustaw dopuszczalny czas trwania etapu awizacja i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „transport z portu” — ustaw dopuszczalny czas trwania etapu transport z portu i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „brama magazynu” — ustaw dopuszczalny czas trwania etapu brama magazynu i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „rozładunek” — ustaw dopuszczalny czas trwania etapu rozładunek i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „kontrola jakości” — ustaw dopuszczalny czas trwania etapu kontrola jakości i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „przyjęcie na stan” — ustaw dopuszczalny czas trwania etapu przyjęcie na stan i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „zwrot pustego” — ustaw dopuszczalny czas trwania etapu zwrot pustego i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „rozliczenie” — ustaw dopuszczalny czas trwania etapu rozliczenie i próg alertu.
- 🔲 **[Feature]** Konfiguracja SLA etapu „zamknięcie” — ustaw dopuszczalny czas trwania etapu zamknięcie i próg alertu.

### 2.14 Znaczniki czasu przejść etapów
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „potwierdzenie bookingu” — zapis timestampu przejścia kontenera do etapu potwierdzenie bookingu w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „załadunek” — zapis timestampu przejścia kontenera do etapu załadunek w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „wypłynięcie (ETD)” — zapis timestampu przejścia kontenera do etapu wypłynięcie (ETD) w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „tranzyt morski” — zapis timestampu przejścia kontenera do etapu tranzyt morski w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „przeładunek” — zapis timestampu przejścia kontenera do etapu przeładunek w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „przybycie (ETA)” — zapis timestampu przejścia kontenera do etapu przybycie (ETA) w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „wyładunek ze statku” — zapis timestampu przejścia kontenera do etapu wyładunek ze statku w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „składowanie w porcie” — zapis timestampu przejścia kontenera do etapu składowanie w porcie w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „zgłoszenie celne” — zapis timestampu przejścia kontenera do etapu zgłoszenie celne w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „odprawa w toku” — zapis timestampu przejścia kontenera do etapu odprawa w toku w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „zwolnienie celne” — zapis timestampu przejścia kontenera do etapu zwolnienie celne w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „awizacja” — zapis timestampu przejścia kontenera do etapu awizacja w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „transport z portu” — zapis timestampu przejścia kontenera do etapu transport z portu w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „brama magazynu” — zapis timestampu przejścia kontenera do etapu brama magazynu w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „rozładunek” — zapis timestampu przejścia kontenera do etapu rozładunek w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „kontrola jakości” — zapis timestampu przejścia kontenera do etapu kontrola jakości w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „przyjęcie na stan” — zapis timestampu przejścia kontenera do etapu przyjęcie na stan w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „zwrot pustego” — zapis timestampu przejścia kontenera do etapu zwrot pustego w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „rozliczenie” — zapis timestampu przejścia kontenera do etapu rozliczenie w historii.
- 🔲 **[Feature]** Znacznik czasu wejścia w etap „zamknięcie” — zapis timestampu przejścia kontenera do etapu zamknięcie w historii.

### 2.15 Auto-notatki dziennika per etap
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „potwierdzenie bookingu” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap potwierdzenie bookingu.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „załadunek” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap załadunek.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „wypłynięcie (ETD)” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap wypłynięcie (ETD).
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „tranzyt morski” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap tranzyt morski.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „przeładunek” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap przeładunek.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „przybycie (ETA)” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap przybycie (ETA).
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „wyładunek ze statku” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap wyładunek ze statku.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „składowanie w porcie” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap składowanie w porcie.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „zgłoszenie celne” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap zgłoszenie celne.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „odprawa w toku” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap odprawa w toku.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „zwolnienie celne” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap zwolnienie celne.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „awizacja” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap awizacja.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „transport z portu” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap transport z portu.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „brama magazynu” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap brama magazynu.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „rozładunek” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap rozładunek.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „kontrola jakości” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap kontrola jakości.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „przyjęcie na stan” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap przyjęcie na stan.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „zwrot pustego” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap zwrot pustego.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „rozliczenie” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap rozliczenie.
- 🔲 **[Feature]** Auto-notatka w karcie przy etapie „zamknięcie” — dopisanie wpisu w dzienniku kontenera przy wejściu w etap zamknięcie.

## 3. SPEDYCJA









### 3.1 Zlecenia transportowe
- ✅ **[Feature]** Zlecenia transportowe (forwarding, TransportOrder, ForwardingPage).
- ✅ **[Feature]** Zadania transportowe + kontenery (TransportJob/TransportJobContainer).
- ✅ **[Feature]** Zapytania spedycyjne (ForwardingRequestsPage) — plaster 1 reużywa TransportJob.
- ✅ **[Feature]** Reużycie TransportJob dla zleceń spedycyjnych — jeden model wiele użyć.
- 🔲 **[Python]** Generator zlecenia transportowego PDF z danych kontenera.
- 🔲 **[Feature]** Statusy zlecenia (zlecone/potwierdzone/w drodze/rozliczone) na osi.
- 🔲 **[Python]** Auto-dobór przewoźnika wg trasy/ceny/dostępności.
- 🔲 **[Feature]** Przypisanie kierowcy/auta do zlecenia + powiadomienie.
- 🔲 **[Python]** Konsolidacja zleceń na jedną trasę (kierunek/termin).
- 🔲 **[n8n]** Auto-awizacja transportu do klienta po nadaniu (nr śledzenia).

### 3.2 Spedytorzy / forwarderzy
- ✅ **[Feature]** Kartoteka forwarderów (Forwarder) + izolacja (scope_transport_orders).
- 🔲 **[Python]** Scoring spedytorów — terminowość, cena, szkody, responsywność.
- 🔲 **[PowerBI]** Scorecard spedytora — KPI, trend, benchmark.
- 🔲 **[Python]** Rozdział wolumenu między spedytorów wg alokacji/ceny.
- 🔲 **[SMTP]** Szablonowe zapytanie o stawkę do puli spedytorów.
- 🔲 **[Python]** Porównywarka odpowiedzi spedytorów — ranking stawka/termin.

### 3.3 Wyceny / quotes
- ✅ **[Feature]** Wyceny transportowe (quotes, Quote, QuoteRevision, QuotesPage).
- ✅ **[Feature]** Rewizje wyceny (QuoteRevision) — historia wersji.
- ✅ **[Feature]** Modal zapytania o wycenę (QuoteRequestModal).
- 🔲 **[Python]** Auto-wycena prostych zleceń z tabeli stawek.
- 🔲 **[Python]** Wykrywanie wyceny odstającej od historii dla trasy.
- 🔲 **[Excel]** Macierz stawek per trasa/typ kontenera z historią.

### 3.4 Koszty i KPI spedycji
- 🔲 **[Python]** Alokacja kosztów frachtu/spedycji na kontenery i pozycje.
- 🔲 **[PowerBI]** KPI transportu — koszt/kontener, terminowość, szkody.
- 🔲 **[Python]** Rekoncyliacja faktury spedytora vs zlecenie/wycena.
- 🔲 **[Python]** Trend kosztu transportu per trasa/miesiąc — negocjacje.
- 🔲 **[Excel]** Raport rozliczenia zleceń transportowych za okres.
- 🔲 **[Python]** Alert przekroczenia budżetu transportowego na kontener.

### 3.5 KPI transportu (wymiar × okres)
- 🔲 **[PowerBI]** KPI transportu miesięczny per dostawcy — koszt/kontener i terminowość miesięczny w podziale na dostawcy.
- 🔲 **[PowerBI]** KPI transportu kwartalny per dostawcy — koszt/kontener i terminowość kwartalny w podziale na dostawcy.
- 🔲 **[PowerBI]** KPI transportu miesięczny per spedytora — koszt/kontener i terminowość miesięczny w podziale na spedytora.
- 🔲 **[PowerBI]** KPI transportu kwartalny per spedytora — koszt/kontener i terminowość kwartalny w podziale na spedytora.
- 🔲 **[PowerBI]** KPI transportu miesięczny per przewoźnika — koszt/kontener i terminowość miesięczny w podziale na przewoźnika.
- 🔲 **[PowerBI]** KPI transportu kwartalny per przewoźnika — koszt/kontener i terminowość kwartalny w podziale na przewoźnika.
- 🔲 **[PowerBI]** KPI transportu miesięczny per armatora — koszt/kontener i terminowość miesięczny w podziale na armatora.
- 🔲 **[PowerBI]** KPI transportu kwartalny per armatora — koszt/kontener i terminowość kwartalny w podziale na armatora.
- 🔲 **[PowerBI]** KPI transportu miesięczny per portu — koszt/kontener i terminowość miesięczny w podziale na portu.
- 🔲 **[PowerBI]** KPI transportu kwartalny per portu — koszt/kontener i terminowość kwartalny w podziale na portu.
- 🔲 **[PowerBI]** KPI transportu miesięczny per magazynu — koszt/kontener i terminowość miesięczny w podziale na magazynu.
- 🔲 **[PowerBI]** KPI transportu kwartalny per magazynu — koszt/kontener i terminowość kwartalny w podziale na magazynu.
- 🔲 **[PowerBI]** KPI transportu miesięczny per klienta — koszt/kontener i terminowość miesięczny w podziale na klienta.
- 🔲 **[PowerBI]** KPI transportu kwartalny per klienta — koszt/kontener i terminowość kwartalny w podziale na klienta.
- 🔲 **[PowerBI]** KPI transportu miesięczny per materiału — koszt/kontener i terminowość miesięczny w podziale na materiału.
- 🔲 **[PowerBI]** KPI transportu kwartalny per materiału — koszt/kontener i terminowość kwartalny w podziale na materiału.
- 🔲 **[PowerBI]** KPI transportu miesięczny per kraju — koszt/kontener i terminowość miesięczny w podziale na kraju.
- 🔲 **[PowerBI]** KPI transportu kwartalny per kraju — koszt/kontener i terminowość kwartalny w podziale na kraju.
- 🔲 **[PowerBI]** KPI transportu miesięczny per trasy — koszt/kontener i terminowość miesięczny w podziale na trasy.
- 🔲 **[PowerBI]** KPI transportu kwartalny per trasy — koszt/kontener i terminowość kwartalny w podziale na trasy.
- 🔲 **[PowerBI]** KPI transportu miesięczny per typu kontenera — koszt/kontener i terminowość miesięczny w podziale na typu kontenera.
- 🔲 **[PowerBI]** KPI transportu kwartalny per typu kontenera — koszt/kontener i terminowość kwartalny w podziale na typu kontenera.
- 🔲 **[PowerBI]** KPI transportu miesięczny per agencji celnej — koszt/kontener i terminowość miesięczny w podziale na agencji celnej.
- 🔲 **[PowerBI]** KPI transportu kwartalny per agencji celnej — koszt/kontener i terminowość kwartalny w podziale na agencji celnej.

### 3.6 Statusy zleceń sprzężone z cyklem
- 🔲 **[Feature]** Status zlecenia sped. sprzężony z etapem „potwierdzenie bookingu u armatora” — auto-aktualizacja statusu zlecenia gdy kontener wchodzi w etap potwierdzenie bookingu u armatora.
- 🔲 **[Feature]** Status zlecenia sped. sprzężony z etapem „załadunek w porcie nadania” — auto-aktualizacja statusu zlecenia gdy kontener wchodzi w etap załadunek w porcie nadania.
- 🔲 **[Feature]** Status zlecenia sped. sprzężony z etapem „wypłynięcie statku (ETD)” — auto-aktualizacja statusu zlecenia gdy kontener wchodzi w etap wypłynięcie statku (ETD).
- 🔲 **[Feature]** Status zlecenia sped. sprzężony z etapem „w tranzycie morskim” — auto-aktualizacja statusu zlecenia gdy kontener wchodzi w etap w tranzycie morskim.
- 🔲 **[Feature]** Status zlecenia sped. sprzężony z etapem „przeładunek/transshipment” — auto-aktualizacja statusu zlecenia gdy kontener wchodzi w etap przeładunek/transshipment.
- 🔲 **[Feature]** Status zlecenia sped. sprzężony z etapem „przybycie do portu (ETA)” — auto-aktualizacja statusu zlecenia gdy kontener wchodzi w etap przybycie do portu (ETA).
- 🔲 **[Feature]** Status zlecenia sped. sprzężony z etapem „wyładunek ze statku” — auto-aktualizacja statusu zlecenia gdy kontener wchodzi w etap wyładunek ze statku.
- 🔲 **[Feature]** Status zlecenia sped. sprzężony z etapem „składowanie w porcie” — auto-aktualizacja statusu zlecenia gdy kontener wchodzi w etap składowanie w porcie.
- 🔲 **[Feature]** Status zlecenia sped. sprzężony z etapem „zgłoszenie celne” — auto-aktualizacja statusu zlecenia gdy kontener wchodzi w etap zgłoszenie celne.
- 🔲 **[Feature]** Status zlecenia sped. sprzężony z etapem „odprawa celna w toku” — auto-aktualizacja statusu zlecenia gdy kontener wchodzi w etap odprawa celna w toku.
- 🔲 **[Feature]** Status zlecenia sped. sprzężony z etapem „zwolnienie celne” — auto-aktualizacja statusu zlecenia gdy kontener wchodzi w etap zwolnienie celne.
- 🔲 **[Feature]** Status zlecenia sped. sprzężony z etapem „awizacja dostawy” — auto-aktualizacja statusu zlecenia gdy kontener wchodzi w etap awizacja dostawy.

## 4. MAGAZYN









### 4.1 Przyjęcia / rozładunki
- ✅ **[Feature]** Operacje magazynowe (warehouse_ops) — obsługa przyjęć.
- ✅ **[Feature]** Karta rozładunku (KartaRozladunkuPage, W10) — protokół rozładunku.
- ✅ **[Feature]** Brama/gate (GatePage) — wjazd/rejestracja auta.
- ✅ **[Feature]** Zdjęcia rozładunku (UnloadPhoto) — dokumentacja stanu towaru.
- ✅ **[Feature]** Checklist rozładunku (checklist, ChecklistPoint/Result, ChecklistPanel).
- ✅ **[Feature]** Portal kierowcy (driver, DriverLink, DriverPage) — samoobsługa na bramie.
- ✅ **[Feature]** Kolejka magazynu (WarehouseQueuePage) — co przyjąć dziś.
- 🔲 **[Python]** Dwell time przyjęć — czas od dostawy do dostępności, alert.
- 🔲 **[Feature]** Skan kontenera na bramie → auto-podpięcie do karty rozładunku.
- 🔲 **[Python]** Rekomendacja put-away wg cech towaru (waga/rotacja/warunki).
- 🔲 **[Feature]** Podpis elektroniczny kierowcy/magazyniera na karcie rozładunku.
- 🔲 **[Python]** Wykrywanie niekompletnego rozładunku (checklist nie 100%) → blokada zamknięcia.

### 4.2 Stany i inwentaryzacja
- ✅ **[Feature]** Cache stanów paletowych i DLT (PalletStockCache/DltStock).
- 🔲 **[Python]** Alert stanu minimalnego — pozycje poniżej min.
- 🔲 **[Python]** Detektor slow-moving/dead stock (>90/180/365 dni).
- 🔲 **[Python]** Analiza rotacji zapasów (turnover) per kategoria.
- 🔲 **[Python]** Generator arkuszy cycle count (próbka ABC).
- 🔲 **[Python]** Rekoncyliacja spisu z systemem — raport różnic.
- 🔲 **[PowerBI]** Dokładność inwentaryzacji (IRA) — % zgodności, per strefa.
- 🔲 **[Excel]** Aging zapasu — koszyki 0-30/31-60/61-90/>90, wartość.
- 🔲 **[Python]** Bilans ATP — stan − rezerwacje + w drodze.

### 4.3 Skanery i etykiety
- 🔲 **[Python]** Masowy generator etykiet Code128/QR z listy (reportlab).
- 🔲 **[Python]** Generator etykiet GS1 DataMatrix (GTIN, partia, data, ilość).
- 🔲 **[Python]** Walidacja cyfry kontrolnej EAN przy wprowadzaniu.
- 🔲 **[API]** Endpoint skanera — skan → dane pozycji/lokalizacji.
- 🔲 **[Feature]** PWA skanera rozładunku (MC330L: brak importmap, PWA scope, P1/P2).
- 🔲 **[Python]** Konwerter ZPL dla drukarek Zebra z danych pozycji.
- 🔲 **[Feature]** Bramka skanu — wymuszenie skanu kontenera przed potwierdzeniem.

### 4.4 KPI magazynu i procesy
- 🔲 **[PowerBI]** Dashboard KPI magazynu — przyjęcia, dokładność, dwell time.
- 🔲 **[Python]** Order fulfillment cycle time — percentyle.
- 🔲 **[Python]** Analiza szczytów obciążenia — godziny/dni peak.
- 🔲 **[Python]** Wykrywanie utknięcia zlecenia (>X h bez postępu) → eskalacja.
- 🔲 **[Excel]** Raport dzienny operacji magazynu o 6:00.
- 🔲 **[Python]** Genealogia partii — recall readiness (partia→wydania).
- 🔲 **[OCR]** Odczyt numerów partii z etykiet przyjęcia do traceability.

### 4.5 Powiadomienia magazynu (kanał)
- 🔲 **[Python]** Powiadomienie o przyjęciu mailem — po zamknięciu rozładunku → info mailem do zainteresowanych.
- 🔲 **[Python]** Alert niekompletnego rozładunku mailem — checklist <100% → eskalacja mailem.
- 🔲 **[Teams]** Powiadomienie o przyjęciu kartą w Teams — po zamknięciu rozładunku → info kartą w Teams do zainteresowanych.
- 🔲 **[Teams]** Alert niekompletnego rozładunku kartą w Teams — checklist <100% → eskalacja kartą w Teams.
- 🔲 **[Python]** Powiadomienie o przyjęciu SMS-em — po zamknięciu rozładunku → info SMS-em do zainteresowanych.
- 🔲 **[Python]** Alert niekompletnego rozładunku SMS-em — checklist <100% → eskalacja SMS-em.
- 🔲 **[Python]** Powiadomienie o przyjęciu na dashboardzie — po zamknięciu rozładunku → info na dashboardzie do zainteresowanych.
- 🔲 **[Python]** Alert niekompletnego rozładunku na dashboardzie — checklist <100% → eskalacja na dashboardzie.
- 🔲 **[Python]** Powiadomienie o przyjęciu powiadomieniem push — po zamknięciu rozładunku → info powiadomieniem push do zainteresowanych.
- 🔲 **[Python]** Alert niekompletnego rozładunku powiadomieniem push — checklist <100% → eskalacja powiadomieniem push.

### 4.6 KPI magazynu per wymiar
- 🔲 **[PowerBI]** Dwell time per dostawcy — czas od dostawy do dostępności na stanie w podziale na dostawcy.
- 🔲 **[Python]** Rotacja zapasu per dostawcy — wskaźnik obrotu (turnover) w podziale na dostawcy.
- 🔲 **[PowerBI]** Dwell time per spedytora — czas od dostawy do dostępności na stanie w podziale na spedytora.
- 🔲 **[Python]** Rotacja zapasu per spedytora — wskaźnik obrotu (turnover) w podziale na spedytora.
- 🔲 **[PowerBI]** Dwell time per przewoźnika — czas od dostawy do dostępności na stanie w podziale na przewoźnika.
- 🔲 **[Python]** Rotacja zapasu per przewoźnika — wskaźnik obrotu (turnover) w podziale na przewoźnika.
- 🔲 **[PowerBI]** Dwell time per armatora — czas od dostawy do dostępności na stanie w podziale na armatora.
- 🔲 **[Python]** Rotacja zapasu per armatora — wskaźnik obrotu (turnover) w podziale na armatora.
- 🔲 **[PowerBI]** Dwell time per portu — czas od dostawy do dostępności na stanie w podziale na portu.
- 🔲 **[Python]** Rotacja zapasu per portu — wskaźnik obrotu (turnover) w podziale na portu.
- 🔲 **[PowerBI]** Dwell time per magazynu — czas od dostawy do dostępności na stanie w podziale na magazynu.
- 🔲 **[Python]** Rotacja zapasu per magazynu — wskaźnik obrotu (turnover) w podziale na magazynu.
- 🔲 **[PowerBI]** Dwell time per klienta — czas od dostawy do dostępności na stanie w podziale na klienta.
- 🔲 **[Python]** Rotacja zapasu per klienta — wskaźnik obrotu (turnover) w podziale na klienta.
- 🔲 **[PowerBI]** Dwell time per materiału — czas od dostawy do dostępności na stanie w podziale na materiału.
- 🔲 **[Python]** Rotacja zapasu per materiału — wskaźnik obrotu (turnover) w podziale na materiału.
- 🔲 **[PowerBI]** Dwell time per kraju — czas od dostawy do dostępności na stanie w podziale na kraju.
- 🔲 **[Python]** Rotacja zapasu per kraju — wskaźnik obrotu (turnover) w podziale na kraju.
- 🔲 **[PowerBI]** Dwell time per trasy — czas od dostawy do dostępności na stanie w podziale na trasy.
- 🔲 **[Python]** Rotacja zapasu per trasy — wskaźnik obrotu (turnover) w podziale na trasy.
- 🔲 **[PowerBI]** Dwell time per typu kontenera — czas od dostawy do dostępności na stanie w podziale na typu kontenera.
- 🔲 **[Python]** Rotacja zapasu per typu kontenera — wskaźnik obrotu (turnover) w podziale na typu kontenera.
- 🔲 **[PowerBI]** Dwell time per agencji celnej — czas od dostawy do dostępności na stanie w podziale na agencji celnej.
- 🔲 **[Python]** Rotacja zapasu per agencji celnej — wskaźnik obrotu (turnover) w podziale na agencji celnej.

### 4.7 Alerty stanów (typ × kanał)
- 🔲 **[Python]** Alert stanu min mailem — wykrycie stanu „min” → powiadomienie mailem.
- 🔲 **[Teams]** Alert stanu min kartą w Teams — wykrycie stanu „min” → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert stanu min SMS-em — wykrycie stanu „min” → powiadomienie SMS-em.
- 🔲 **[Python]** Alert stanu min na dashboardzie — wykrycie stanu „min” → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert stanu min powiadomieniem push — wykrycie stanu „min” → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert stanu max mailem — wykrycie stanu „max” → powiadomienie mailem.
- 🔲 **[Teams]** Alert stanu max kartą w Teams — wykrycie stanu „max” → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert stanu max SMS-em — wykrycie stanu „max” → powiadomienie SMS-em.
- 🔲 **[Python]** Alert stanu max na dashboardzie — wykrycie stanu „max” → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert stanu max powiadomieniem push — wykrycie stanu „max” → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert stanu poniżej celu mailem — wykrycie stanu „poniżej celu” → powiadomienie mailem.
- 🔲 **[Teams]** Alert stanu poniżej celu kartą w Teams — wykrycie stanu „poniżej celu” → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert stanu poniżej celu SMS-em — wykrycie stanu „poniżej celu” → powiadomienie SMS-em.
- 🔲 **[Python]** Alert stanu poniżej celu na dashboardzie — wykrycie stanu „poniżej celu” → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert stanu poniżej celu powiadomieniem push — wykrycie stanu „poniżej celu” → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert stanu dead stock >180 dni mailem — wykrycie stanu „dead stock >180 dni” → powiadomienie mailem.
- 🔲 **[Teams]** Alert stanu dead stock >180 dni kartą w Teams — wykrycie stanu „dead stock >180 dni” → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert stanu dead stock >180 dni SMS-em — wykrycie stanu „dead stock >180 dni” → powiadomienie SMS-em.
- 🔲 **[Python]** Alert stanu dead stock >180 dni na dashboardzie — wykrycie stanu „dead stock >180 dni” → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert stanu dead stock >180 dni powiadomieniem push — wykrycie stanu „dead stock >180 dni” → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert stanu slow-mover >90 dni mailem — wykrycie stanu „slow-mover >90 dni” → powiadomienie mailem.
- 🔲 **[Teams]** Alert stanu slow-mover >90 dni kartą w Teams — wykrycie stanu „slow-mover >90 dni” → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert stanu slow-mover >90 dni SMS-em — wykrycie stanu „slow-mover >90 dni” → powiadomienie SMS-em.
- 🔲 **[Python]** Alert stanu slow-mover >90 dni na dashboardzie — wykrycie stanu „slow-mover >90 dni” → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert stanu slow-mover >90 dni powiadomieniem push — wykrycie stanu „slow-mover >90 dni” → powiadomienie powiadomieniem push.

### 4.8 Etykiety i skanowanie (per typ)
- 🔲 **[Python]** Generator etykiety: paleta EU — PDF/ZPL etykiety dla „paleta EU” z kodem kreskowym/QR.
- 🔲 **[Feature]** Skan i weryfikacja: paleta EU — skan kodu „paleta EU” → walidacja i podpięcie do operacji.
- 🔲 **[Python]** Generator etykiety: karton zbiorczy — PDF/ZPL etykiety dla „karton zbiorczy” z kodem kreskowym/QR.
- 🔲 **[Feature]** Skan i weryfikacja: karton zbiorczy — skan kodu „karton zbiorczy” → walidacja i podpięcie do operacji.
- 🔲 **[Python]** Generator etykiety: sztuka — PDF/ZPL etykiety dla „sztuka” z kodem kreskowym/QR.
- 🔲 **[Feature]** Skan i weryfikacja: sztuka — skan kodu „sztuka” → walidacja i podpięcie do operacji.
- 🔲 **[Python]** Generator etykiety: lokalizacja regału — PDF/ZPL etykiety dla „lokalizacja regału” z kodem kreskowym/QR.
- 🔲 **[Feature]** Skan i weryfikacja: lokalizacja regału — skan kodu „lokalizacja regału” → walidacja i podpięcie do operacji.
- 🔲 **[Python]** Generator etykiety: strefa przyjęć — PDF/ZPL etykiety dla „strefa przyjęć” z kodem kreskowym/QR.
- 🔲 **[Feature]** Skan i weryfikacja: strefa przyjęć — skan kodu „strefa przyjęć” → walidacja i podpięcie do operacji.
- 🔲 **[Python]** Generator etykiety: kontener — PDF/ZPL etykiety dla „kontener” z kodem kreskowym/QR.
- 🔲 **[Feature]** Skan i weryfikacja: kontener — skan kodu „kontener” → walidacja i podpięcie do operacji.
- 🔲 **[Python]** Generator etykiety: partia produkcyjna — PDF/ZPL etykiety dla „partia produkcyjna” z kodem kreskowym/QR.
- 🔲 **[Feature]** Skan i weryfikacja: partia produkcyjna — skan kodu „partia produkcyjna” → walidacja i podpięcie do operacji.
- 🔲 **[Python]** Generator etykiety: zwrot — PDF/ZPL etykiety dla „zwrot” z kodem kreskowym/QR.
- 🔲 **[Feature]** Skan i weryfikacja: zwrot — skan kodu „zwrot” → walidacja i podpięcie do operacji.

### 4.9 Kontrola druku etykiet
- 🔲 **[Python]** Weryfikacja druku etykiety: paleta EU — test poprawności i cyfry kontrolnej etykiety „paleta EU”.
- 🔲 **[Python]** Weryfikacja druku etykiety: karton zbiorczy — test poprawności i cyfry kontrolnej etykiety „karton zbiorczy”.
- 🔲 **[Python]** Weryfikacja druku etykiety: sztuka — test poprawności i cyfry kontrolnej etykiety „sztuka”.
- 🔲 **[Python]** Weryfikacja druku etykiety: lokalizacja regału — test poprawności i cyfry kontrolnej etykiety „lokalizacja regału”.
- 🔲 **[Python]** Weryfikacja druku etykiety: strefa przyjęć — test poprawności i cyfry kontrolnej etykiety „strefa przyjęć”.
- 🔲 **[Python]** Weryfikacja druku etykiety: kontener — test poprawności i cyfry kontrolnej etykiety „kontener”.
- 🔲 **[Python]** Weryfikacja druku etykiety: partia produkcyjna — test poprawności i cyfry kontrolnej etykiety „partia produkcyjna”.
- 🔲 **[Python]** Weryfikacja druku etykiety: zwrot — test poprawności i cyfry kontrolnej etykiety „zwrot”.

## 5. CELNE / DOKUMENTY









### 5.1 Agencje i statusy odpraw
- ✅ **[Feature]** Moduł odpraw celnych (customs, CustomsPage) — statusy spraw.
- ✅ **[Feature]** Agencje celne (CustomsAgency) — kartoteka.
- ✅ **[Feature]** Statusy sprawy celnej (CustomsCaseStatus) — cykl odprawy.
- ✅ **[Python]** Alert opóźnienia odprawy (customs_delay_loop).
- 🔲 **[n8n]** Auto-mail paczki dokumentów do agencji po skompletowaniu.
- 🔲 **[Feature]** Portal agencji celnej — self-service statusów spraw.
- 🔲 **[Python]** SLA odprawy — alert gdy sprawa wisi >X dni bez zmiany.
- 🔲 **[PowerBI]** Dashboard odpraw — czas odprawy per agencja, wąskie gardła.

### 5.2 Dokumenty i OCR
- ✅ **[Feature]** Dokumenty i typy (documents, DocumentType, Attachment).
- ✅ **[Feature]** Sugestie podpięcia załączników (AttachmentSuggestion) — auto-match.
- ✅ **[Feature]** Szablony wysyłki dokumentów (DocSendTemplate).
- ✅ **[OCR]** OCR faktur/CIPL (InvoiceItem, integracja Compare).
- 🔲 **[Python]** Tracker kompletności paczki dokumentów per kontener (CIPL/BL/CoO/EUR.1/SAD).
- 🔲 **[OCR]** Odczyt BL — nr, armator, port, ilość kontenerów.
- 🔲 **[OCR]** Odczyt świadectwa pochodzenia / EUR.1 do rejestru.
- 🔲 **[Python]** Walidacja kodów HS/CN i stawek na dokumentach.
- 🔲 **[Python]** Auto-nazywanie plików wg treści (nr dokumentu, data, kontener).
- 🔲 **[SharePoint]** Repozytorium dokumentów kontenera z metadanymi + wyszukiwanie.
- 🔲 **[Python]** Wykrywanie brakującego dokumentu blokującego odprawę → alert.

### 5.3 SENT i zgodność
- ✅ **[Feature]** Linki SENT (SentLink) — udostępnianie danych do SENT.
- 🔲 **[Python]** Generator zgłoszenia SENT z danych kontenera/pozycji.
- 🔲 **[Python]** Walidacja kompletności danych do SENT przed wysyłką.
- 🔲 **[n8n]** Powiadomienie o wygaśnięciu ważności zgłoszenia SENT.
- 🔲 **[Python]** Kontrola zgodności wagi/pozycji: dokument vs karta rozładunku.

### 5.4 Dokumenty importowe (per typ)
- 🔲 **[Python]** Tracker dokumentu: CIPL — kontrola obecności i ważności dokumentu CIPL per kontener → alert braku.
- 🔲 **[OCR]** OCR dokumentu: CIPL — ekstrakcja kluczowych pól z CIPL do rejestru.
- 🔲 **[Python]** Tracker dokumentu: BL — kontrola obecności i ważności dokumentu BL per kontener → alert braku.
- 🔲 **[OCR]** OCR dokumentu: BL — ekstrakcja kluczowych pól z BL do rejestru.
- 🔲 **[Python]** Tracker dokumentu: świadectwo pochodzenia — kontrola obecności i ważności dokumentu świadectwo pochodzenia per kontener → alert braku.
- 🔲 **[OCR]** OCR dokumentu: świadectwo pochodzenia — ekstrakcja kluczowych pól z świadectwo pochodzenia do rejestru.
- 🔲 **[Python]** Tracker dokumentu: EUR.1 — kontrola obecności i ważności dokumentu EUR.1 per kontener → alert braku.
- 🔲 **[OCR]** OCR dokumentu: EUR.1 — ekstrakcja kluczowych pól z EUR.1 do rejestru.
- 🔲 **[Python]** Tracker dokumentu: SAD — kontrola obecności i ważności dokumentu SAD per kontener → alert braku.
- 🔲 **[OCR]** OCR dokumentu: SAD — ekstrakcja kluczowych pól z SAD do rejestru.
- 🔲 **[Python]** Tracker dokumentu: packing list — kontrola obecności i ważności dokumentu packing list per kontener → alert braku.
- 🔲 **[OCR]** OCR dokumentu: packing list — ekstrakcja kluczowych pól z packing list do rejestru.
- 🔲 **[Python]** Tracker dokumentu: MSDS — kontrola obecności i ważności dokumentu MSDS per kontener → alert braku.
- 🔲 **[OCR]** OCR dokumentu: MSDS — ekstrakcja kluczowych pól z MSDS do rejestru.
- 🔲 **[Python]** Tracker dokumentu: certyfikat jakości — kontrola obecności i ważności dokumentu certyfikat jakości per kontener → alert braku.
- 🔲 **[OCR]** OCR dokumentu: certyfikat jakości — ekstrakcja kluczowych pól z certyfikat jakości do rejestru.
- 🔲 **[Python]** Tracker dokumentu: świadectwo fumigacji — kontrola obecności i ważności dokumentu świadectwo fumigacji per kontener → alert braku.
- 🔲 **[OCR]** OCR dokumentu: świadectwo fumigacji — ekstrakcja kluczowych pól z świadectwo fumigacji do rejestru.
- 🔲 **[Python]** Tracker dokumentu: weight certificate — kontrola obecności i ważności dokumentu weight certificate per kontener → alert braku.
- 🔲 **[OCR]** OCR dokumentu: weight certificate — ekstrakcja kluczowych pól z weight certificate do rejestru.
- 🔲 **[Python]** Tracker dokumentu: polisa ubezpieczeniowa — kontrola obecności i ważności dokumentu polisa ubezpieczeniowa per kontener → alert braku.
- 🔲 **[OCR]** OCR dokumentu: polisa ubezpieczeniowa — ekstrakcja kluczowych pól z polisa ubezpieczeniowa do rejestru.
- 🔲 **[Python]** Tracker dokumentu: umowa przewozu — kontrola obecności i ważności dokumentu umowa przewozu per kontener → alert braku.
- 🔲 **[OCR]** OCR dokumentu: umowa przewozu — ekstrakcja kluczowych pól z umowa przewozu do rejestru.

### 5.5 Alerty odpraw (kanał)
- 🔲 **[Python]** Alert opóźnienia odprawy mailem — sprawa celna bez zmiany > SLA → powiadomienie mailem.
- 🔲 **[Teams]** Alert opóźnienia odprawy kartą w Teams — sprawa celna bez zmiany > SLA → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert opóźnienia odprawy SMS-em — sprawa celna bez zmiany > SLA → powiadomienie SMS-em.
- 🔲 **[Python]** Alert opóźnienia odprawy na dashboardzie — sprawa celna bez zmiany > SLA → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert opóźnienia odprawy powiadomieniem push — sprawa celna bez zmiany > SLA → powiadomienie powiadomieniem push.

### 5.6 Cykl życia dokumentów (per typ)
- 🔲 **[Python]** Walidacja spójności CIPL vs kontener — porównanie kluczowych pól CIPL z danymi kontenera → flaga rozbieżności.
- 🔲 **[SharePoint]** Archiwizacja CIPL do SharePoint — auto-upload CIPL do biblioteki z metadanymi kontenera.
- 🔲 **[Python]** Przypomnienie o wygaśnięciu CIPL — alert gdy zbliża się data ważności CIPL.
- 🔲 **[Python]** Walidacja spójności BL vs kontener — porównanie kluczowych pól BL z danymi kontenera → flaga rozbieżności.
- 🔲 **[SharePoint]** Archiwizacja BL do SharePoint — auto-upload BL do biblioteki z metadanymi kontenera.
- 🔲 **[Python]** Przypomnienie o wygaśnięciu BL — alert gdy zbliża się data ważności BL.
- 🔲 **[Python]** Walidacja spójności świadectwo pochodzenia vs kontener — porównanie kluczowych pól świadectwo pochodzenia z danymi kontenera → flaga rozbieżności.
- 🔲 **[SharePoint]** Archiwizacja świadectwo pochodzenia do SharePoint — auto-upload świadectwo pochodzenia do biblioteki z metadanymi kontenera.
- 🔲 **[Python]** Przypomnienie o wygaśnięciu świadectwo pochodzenia — alert gdy zbliża się data ważności świadectwo pochodzenia.
- 🔲 **[Python]** Walidacja spójności EUR.1 vs kontener — porównanie kluczowych pól EUR.1 z danymi kontenera → flaga rozbieżności.
- 🔲 **[SharePoint]** Archiwizacja EUR.1 do SharePoint — auto-upload EUR.1 do biblioteki z metadanymi kontenera.
- 🔲 **[Python]** Przypomnienie o wygaśnięciu EUR.1 — alert gdy zbliża się data ważności EUR.1.
- 🔲 **[Python]** Walidacja spójności SAD vs kontener — porównanie kluczowych pól SAD z danymi kontenera → flaga rozbieżności.
- 🔲 **[SharePoint]** Archiwizacja SAD do SharePoint — auto-upload SAD do biblioteki z metadanymi kontenera.
- 🔲 **[Python]** Przypomnienie o wygaśnięciu SAD — alert gdy zbliża się data ważności SAD.
- 🔲 **[Python]** Walidacja spójności packing list vs kontener — porównanie kluczowych pól packing list z danymi kontenera → flaga rozbieżności.
- 🔲 **[SharePoint]** Archiwizacja packing list do SharePoint — auto-upload packing list do biblioteki z metadanymi kontenera.
- 🔲 **[Python]** Przypomnienie o wygaśnięciu packing list — alert gdy zbliża się data ważności packing list.
- 🔲 **[Python]** Walidacja spójności MSDS vs kontener — porównanie kluczowych pól MSDS z danymi kontenera → flaga rozbieżności.
- 🔲 **[SharePoint]** Archiwizacja MSDS do SharePoint — auto-upload MSDS do biblioteki z metadanymi kontenera.
- 🔲 **[Python]** Przypomnienie o wygaśnięciu MSDS — alert gdy zbliża się data ważności MSDS.
- 🔲 **[Python]** Walidacja spójności certyfikat jakości vs kontener — porównanie kluczowych pól certyfikat jakości z danymi kontenera → flaga rozbieżności.
- 🔲 **[SharePoint]** Archiwizacja certyfikat jakości do SharePoint — auto-upload certyfikat jakości do biblioteki z metadanymi kontenera.
- 🔲 **[Python]** Przypomnienie o wygaśnięciu certyfikat jakości — alert gdy zbliża się data ważności certyfikat jakości.
- 🔲 **[Python]** Walidacja spójności świadectwo fumigacji vs kontener — porównanie kluczowych pól świadectwo fumigacji z danymi kontenera → flaga rozbieżności.
- 🔲 **[SharePoint]** Archiwizacja świadectwo fumigacji do SharePoint — auto-upload świadectwo fumigacji do biblioteki z metadanymi kontenera.
- 🔲 **[Python]** Przypomnienie o wygaśnięciu świadectwo fumigacji — alert gdy zbliża się data ważności świadectwo fumigacji.
- 🔲 **[Python]** Walidacja spójności weight certificate vs kontener — porównanie kluczowych pól weight certificate z danymi kontenera → flaga rozbieżności.
- 🔲 **[SharePoint]** Archiwizacja weight certificate do SharePoint — auto-upload weight certificate do biblioteki z metadanymi kontenera.
- 🔲 **[Python]** Przypomnienie o wygaśnięciu weight certificate — alert gdy zbliża się data ważności weight certificate.
- 🔲 **[Python]** Walidacja spójności polisa ubezpieczeniowa vs kontener — porównanie kluczowych pól polisa ubezpieczeniowa z danymi kontenera → flaga rozbieżności.
- 🔲 **[SharePoint]** Archiwizacja polisa ubezpieczeniowa do SharePoint — auto-upload polisa ubezpieczeniowa do biblioteki z metadanymi kontenera.
- 🔲 **[Python]** Przypomnienie o wygaśnięciu polisa ubezpieczeniowa — alert gdy zbliża się data ważności polisa ubezpieczeniowa.
- 🔲 **[Python]** Walidacja spójności umowa przewozu vs kontener — porównanie kluczowych pól umowa przewozu z danymi kontenera → flaga rozbieżności.
- 🔲 **[SharePoint]** Archiwizacja umowa przewozu do SharePoint — auto-upload umowa przewozu do biblioteki z metadanymi kontenera.
- 🔲 **[Python]** Przypomnienie o wygaśnięciu umowa przewozu — alert gdy zbliża się data ważności umowa przewozu.

### 5.7 Generatory dokumentów (per typ)
- 🔲 **[Python]** Generator dokumentu: CIPL — złożenie CIPL z danych kontenera do PDF.
- 🔲 **[Python]** Generator dokumentu: BL — złożenie BL z danych kontenera do PDF.
- 🔲 **[Python]** Generator dokumentu: świadectwo pochodzenia — złożenie świadectwo pochodzenia z danych kontenera do PDF.
- 🔲 **[Python]** Generator dokumentu: EUR.1 — złożenie EUR.1 z danych kontenera do PDF.
- 🔲 **[Python]** Generator dokumentu: SAD — złożenie SAD z danych kontenera do PDF.
- 🔲 **[Python]** Generator dokumentu: packing list — złożenie packing list z danych kontenera do PDF.
- 🔲 **[Python]** Generator dokumentu: MSDS — złożenie MSDS z danych kontenera do PDF.
- 🔲 **[Python]** Generator dokumentu: certyfikat jakości — złożenie certyfikat jakości z danych kontenera do PDF.
- 🔲 **[Python]** Generator dokumentu: świadectwo fumigacji — złożenie świadectwo fumigacji z danych kontenera do PDF.
- 🔲 **[Python]** Generator dokumentu: weight certificate — złożenie weight certificate z danych kontenera do PDF.
- 🔲 **[Python]** Generator dokumentu: polisa ubezpieczeniowa — złożenie polisa ubezpieczeniowa z danych kontenera do PDF.
- 🔲 **[Python]** Generator dokumentu: umowa przewozu — złożenie umowa przewozu z danych kontenera do PDF.

## 6. SPRZEDAŻ / KLIENCI









### 6.1 Portal klienta i udostępnianie
- ✅ **[Feature]** Portal klienta (portal, PortalPage) — podgląd stanu kontenerów.
- ✅ **[Feature]** Linki share kontenera/klienta (share, ContainerShareLink/CustomerShareLink, SharePage).
- ✅ **[Feature]** Kartoteka klientów (Customer) + izolacja per klient.
- ✅ **[Feature]** Linki dla kierowcy (DriverLink) — dostęp bez logowania.
- 🔲 **[Feature]** Portal klienta plaster 2 — widok kliencki reużywa ContainerTimeline.
- 🔲 **[Feature]** Powiadomienia push/mailowe klienta o zmianie ETA jego kontenera.
- 🔲 **[Feature]** Samoobsługowe pobranie dokumentów kontenera przez klienta.
- 🔲 **[Python]** Auto-raport statusowy dla klienta (tygodniowy PDF jego kontenerów).
- 🔲 **[Feature]** Komentarze/zapytania klienta do kontenera w portalu.

### 6.2 Raporty i follow-up
- 🔲 **[n8n]** Ankieta satysfakcji po dostawie (NPS X dni po rozładunku).
- 🔲 **[Python]** Alert braku aktywności klienta — churn flag.
- 🔲 **[Python]** Segmentacja RFM klientów — akcje per segment.
- 🔲 **[PowerBI]** Analiza koncentracji sprzedaży — udział TOP klientów.
- 🔲 **[Python]** Auto-brief przed spotkaniem z klientem (historia, otwarte kwestie).
- 🔲 **[SMTP]** Podsumowanie miesięczne współpracy do klienta.

### 6.3 Oferty i zamówienia klienta
- 🔲 **[Python]** Generator oferty PDF (jinja2+weasyprint) z danych klienta.
- 🔲 **[OCR]** Odczyt zamówienia klienta z PDF/maila → do systemu.
- 🔲 **[Python]** Walidacja zamówienia — dostępność, cena, limit kredytowy.
- 🔲 **[Python]** Aging należności (AR) per klient — wartość zagrożona.
- 🔲 **[n8n]** Automatyczne monity o płatność (przed/po terminie).

### 6.4 Powiadomienia klienta per etap
- 🔲 **[Feature]** Powiadomienie klienta o etapie „potwierdzenie bookingu u armatora” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap potwierdzenie bookingu u armatora.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „załadunek w porcie nadania” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap załadunek w porcie nadania.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „wypłynięcie statku (ETD)” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap wypłynięcie statku (ETD).
- 🔲 **[Feature]** Powiadomienie klienta o etapie „w tranzycie morskim” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap w tranzycie morskim.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „przeładunek/transshipment” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap przeładunek/transshipment.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „przybycie do portu (ETA)” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap przybycie do portu (ETA).
- 🔲 **[Feature]** Powiadomienie klienta o etapie „wyładunek ze statku” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap wyładunek ze statku.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „składowanie w porcie” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap składowanie w porcie.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „zgłoszenie celne” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap zgłoszenie celne.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „odprawa celna w toku” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap odprawa celna w toku.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „zwolnienie celne” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap zwolnienie celne.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „awizacja dostawy” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap awizacja dostawy.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „transport z portu do magazynu” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap transport z portu do magazynu.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „zgłoszenie na bramie magazynu” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap zgłoszenie na bramie magazynu.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „rozładunek kontenera” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap rozładunek kontenera.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „kontrola jakości towaru” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap kontrola jakości towaru.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „przyjęcie na stan” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap przyjęcie na stan.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „zwrot pustego kontenera” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap zwrot pustego kontenera.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „rozliczenie kosztów kontenera” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap rozliczenie kosztów kontenera.
- 🔲 **[Feature]** Powiadomienie klienta o etapie „zamknięcie sprawy kontenera” — portal/mail: klient dostaje info gdy jego kontener wchodzi w etap zamknięcie sprawy kontenera.

### 6.5 Raporty klienta i sprzedaży
- 🔲 **[Python]** Raport statusowy dzienny dla klienta (PDF) — automatyczny dzienny przegląd kontenerów klienta → PDF mailem.
- 🔲 **[Python]** Raport statusowy tygodniowy dla klienta (PDF) — automatyczny tygodniowy przegląd kontenerów klienta → PDF mailem.
- 🔲 **[Python]** Raport statusowy miesięczny dla klienta (PDF) — automatyczny miesięczny przegląd kontenerów klienta → PDF mailem.
- 🔲 **[Python]** Raport statusowy kwartalny dla klienta (PDF) — automatyczny kwartalny przegląd kontenerów klienta → PDF mailem.
- 🔲 **[Python]** Raport statusowy roczny dla klienta (PDF) — automatyczny roczny przegląd kontenerów klienta → PDF mailem.
- 🔲 **[PowerBI]** Analiza sprzedaży per dostawcy — udział i trend w podziale na dostawcy.
- 🔲 **[PowerBI]** Analiza sprzedaży per spedytora — udział i trend w podziale na spedytora.
- 🔲 **[PowerBI]** Analiza sprzedaży per przewoźnika — udział i trend w podziale na przewoźnika.
- 🔲 **[PowerBI]** Analiza sprzedaży per armatora — udział i trend w podziale na armatora.
- 🔲 **[PowerBI]** Analiza sprzedaży per portu — udział i trend w podziale na portu.
- 🔲 **[PowerBI]** Analiza sprzedaży per magazynu — udział i trend w podziale na magazynu.

### 6.6 Akcje per segment klienta
- 🔲 **[Python]** Segment „VIP”: priorytet w kolejce — auto-akcja „priorytet w kolejce” dla klientów w segmencie VIP.
- 🔲 **[Python]** Segment „VIP”: dedykowany opiekun — auto-akcja „dedykowany opiekun” dla klientów w segmencie VIP.
- 🔲 **[Python]** Segment „VIP”: raport tygodniowy — auto-akcja „raport tygodniowy” dla klientów w segmencie VIP.
- 🔲 **[Python]** Segment „VIP”: przypomnienie płatności — auto-akcja „przypomnienie płatności” dla klientów w segmencie VIP.
- 🔲 **[Python]** Segment „VIP”: oferta specjalna — auto-akcja „oferta specjalna” dla klientów w segmencie VIP.
- 🔲 **[Python]** Segment „VIP”: ankieta satysfakcji — auto-akcja „ankieta satysfakcji” dla klientów w segmencie VIP.
- 🔲 **[Python]** Segment „nowy”: priorytet w kolejce — auto-akcja „priorytet w kolejce” dla klientów w segmencie nowy.
- 🔲 **[Python]** Segment „nowy”: dedykowany opiekun — auto-akcja „dedykowany opiekun” dla klientów w segmencie nowy.
- 🔲 **[Python]** Segment „nowy”: raport tygodniowy — auto-akcja „raport tygodniowy” dla klientów w segmencie nowy.
- 🔲 **[Python]** Segment „nowy”: przypomnienie płatności — auto-akcja „przypomnienie płatności” dla klientów w segmencie nowy.
- 🔲 **[Python]** Segment „nowy”: oferta specjalna — auto-akcja „oferta specjalna” dla klientów w segmencie nowy.
- 🔲 **[Python]** Segment „nowy”: ankieta satysfakcji — auto-akcja „ankieta satysfakcji” dla klientów w segmencie nowy.
- 🔲 **[Python]** Segment „churn-risk”: priorytet w kolejce — auto-akcja „priorytet w kolejce” dla klientów w segmencie churn-risk.
- 🔲 **[Python]** Segment „churn-risk”: dedykowany opiekun — auto-akcja „dedykowany opiekun” dla klientów w segmencie churn-risk.
- 🔲 **[Python]** Segment „churn-risk”: raport tygodniowy — auto-akcja „raport tygodniowy” dla klientów w segmencie churn-risk.
- 🔲 **[Python]** Segment „churn-risk”: przypomnienie płatności — auto-akcja „przypomnienie płatności” dla klientów w segmencie churn-risk.
- 🔲 **[Python]** Segment „churn-risk”: oferta specjalna — auto-akcja „oferta specjalna” dla klientów w segmencie churn-risk.
- 🔲 **[Python]** Segment „churn-risk”: ankieta satysfakcji — auto-akcja „ankieta satysfakcji” dla klientów w segmencie churn-risk.
- 🔲 **[Python]** Segment „wysokomarżowy”: priorytet w kolejce — auto-akcja „priorytet w kolejce” dla klientów w segmencie wysokomarżowy.
- 🔲 **[Python]** Segment „wysokomarżowy”: dedykowany opiekun — auto-akcja „dedykowany opiekun” dla klientów w segmencie wysokomarżowy.
- 🔲 **[Python]** Segment „wysokomarżowy”: raport tygodniowy — auto-akcja „raport tygodniowy” dla klientów w segmencie wysokomarżowy.
- 🔲 **[Python]** Segment „wysokomarżowy”: przypomnienie płatności — auto-akcja „przypomnienie płatności” dla klientów w segmencie wysokomarżowy.
- 🔲 **[Python]** Segment „wysokomarżowy”: oferta specjalna — auto-akcja „oferta specjalna” dla klientów w segmencie wysokomarżowy.
- 🔲 **[Python]** Segment „wysokomarżowy”: ankieta satysfakcji — auto-akcja „ankieta satysfakcji” dla klientów w segmencie wysokomarżowy.
- 🔲 **[Python]** Segment „sezonowy”: priorytet w kolejce — auto-akcja „priorytet w kolejce” dla klientów w segmencie sezonowy.
- 🔲 **[Python]** Segment „sezonowy”: dedykowany opiekun — auto-akcja „dedykowany opiekun” dla klientów w segmencie sezonowy.
- 🔲 **[Python]** Segment „sezonowy”: raport tygodniowy — auto-akcja „raport tygodniowy” dla klientów w segmencie sezonowy.
- 🔲 **[Python]** Segment „sezonowy”: przypomnienie płatności — auto-akcja „przypomnienie płatności” dla klientów w segmencie sezonowy.
- 🔲 **[Python]** Segment „sezonowy”: oferta specjalna — auto-akcja „oferta specjalna” dla klientów w segmencie sezonowy.
- 🔲 **[Python]** Segment „sezonowy”: ankieta satysfakcji — auto-akcja „ankieta satysfakcji” dla klientów w segmencie sezonowy.
- 🔲 **[Python]** Segment „zalegający z płatnością”: priorytet w kolejce — auto-akcja „priorytet w kolejce” dla klientów w segmencie zalegający z płatnością.
- 🔲 **[Python]** Segment „zalegający z płatnością”: dedykowany opiekun — auto-akcja „dedykowany opiekun” dla klientów w segmencie zalegający z płatnością.
- 🔲 **[Python]** Segment „zalegający z płatnością”: raport tygodniowy — auto-akcja „raport tygodniowy” dla klientów w segmencie zalegający z płatnością.
- 🔲 **[Python]** Segment „zalegający z płatnością”: przypomnienie płatności — auto-akcja „przypomnienie płatności” dla klientów w segmencie zalegający z płatnością.
- 🔲 **[Python]** Segment „zalegający z płatnością”: oferta specjalna — auto-akcja „oferta specjalna” dla klientów w segmencie zalegający z płatnością.
- 🔲 **[Python]** Segment „zalegający z płatnością”: ankieta satysfakcji — auto-akcja „ankieta satysfakcji” dla klientów w segmencie zalegający z płatnością.

### 6.7 Kanały kontaktu per segment
- 🔲 **[Python]** Kontakt z segmentem „VIP” mailem — kampania/powiadomienie do segmentu VIP mailem.
- 🔲 **[Teams]** Kontakt z segmentem „VIP” kartą w Teams — kampania/powiadomienie do segmentu VIP kartą w Teams.
- 🔲 **[Python]** Kontakt z segmentem „VIP” SMS-em — kampania/powiadomienie do segmentu VIP SMS-em.
- 🔲 **[Python]** Kontakt z segmentem „VIP” na dashboardzie — kampania/powiadomienie do segmentu VIP na dashboardzie.
- 🔲 **[Python]** Kontakt z segmentem „VIP” powiadomieniem push — kampania/powiadomienie do segmentu VIP powiadomieniem push.
- 🔲 **[Python]** Kontakt z segmentem „nowy” mailem — kampania/powiadomienie do segmentu nowy mailem.
- 🔲 **[Teams]** Kontakt z segmentem „nowy” kartą w Teams — kampania/powiadomienie do segmentu nowy kartą w Teams.
- 🔲 **[Python]** Kontakt z segmentem „nowy” SMS-em — kampania/powiadomienie do segmentu nowy SMS-em.
- 🔲 **[Python]** Kontakt z segmentem „nowy” na dashboardzie — kampania/powiadomienie do segmentu nowy na dashboardzie.
- 🔲 **[Python]** Kontakt z segmentem „nowy” powiadomieniem push — kampania/powiadomienie do segmentu nowy powiadomieniem push.
- 🔲 **[Python]** Kontakt z segmentem „churn-risk” mailem — kampania/powiadomienie do segmentu churn-risk mailem.
- 🔲 **[Teams]** Kontakt z segmentem „churn-risk” kartą w Teams — kampania/powiadomienie do segmentu churn-risk kartą w Teams.
- 🔲 **[Python]** Kontakt z segmentem „churn-risk” SMS-em — kampania/powiadomienie do segmentu churn-risk SMS-em.
- 🔲 **[Python]** Kontakt z segmentem „churn-risk” na dashboardzie — kampania/powiadomienie do segmentu churn-risk na dashboardzie.
- 🔲 **[Python]** Kontakt z segmentem „churn-risk” powiadomieniem push — kampania/powiadomienie do segmentu churn-risk powiadomieniem push.
- 🔲 **[Python]** Kontakt z segmentem „wysokomarżowy” mailem — kampania/powiadomienie do segmentu wysokomarżowy mailem.
- 🔲 **[Teams]** Kontakt z segmentem „wysokomarżowy” kartą w Teams — kampania/powiadomienie do segmentu wysokomarżowy kartą w Teams.
- 🔲 **[Python]** Kontakt z segmentem „wysokomarżowy” SMS-em — kampania/powiadomienie do segmentu wysokomarżowy SMS-em.
- 🔲 **[Python]** Kontakt z segmentem „wysokomarżowy” na dashboardzie — kampania/powiadomienie do segmentu wysokomarżowy na dashboardzie.
- 🔲 **[Python]** Kontakt z segmentem „wysokomarżowy” powiadomieniem push — kampania/powiadomienie do segmentu wysokomarżowy powiadomieniem push.
- 🔲 **[Python]** Kontakt z segmentem „sezonowy” mailem — kampania/powiadomienie do segmentu sezonowy mailem.
- 🔲 **[Teams]** Kontakt z segmentem „sezonowy” kartą w Teams — kampania/powiadomienie do segmentu sezonowy kartą w Teams.
- 🔲 **[Python]** Kontakt z segmentem „sezonowy” SMS-em — kampania/powiadomienie do segmentu sezonowy SMS-em.
- 🔲 **[Python]** Kontakt z segmentem „sezonowy” na dashboardzie — kampania/powiadomienie do segmentu sezonowy na dashboardzie.
- 🔲 **[Python]** Kontakt z segmentem „sezonowy” powiadomieniem push — kampania/powiadomienie do segmentu sezonowy powiadomieniem push.
- 🔲 **[Python]** Kontakt z segmentem „zalegający z płatnością” mailem — kampania/powiadomienie do segmentu zalegający z płatnością mailem.
- 🔲 **[Teams]** Kontakt z segmentem „zalegający z płatnością” kartą w Teams — kampania/powiadomienie do segmentu zalegający z płatnością kartą w Teams.
- 🔲 **[Python]** Kontakt z segmentem „zalegający z płatnością” SMS-em — kampania/powiadomienie do segmentu zalegający z płatnością SMS-em.
- 🔲 **[Python]** Kontakt z segmentem „zalegający z płatnością” na dashboardzie — kampania/powiadomienie do segmentu zalegający z płatnością na dashboardzie.
- 🔲 **[Python]** Kontakt z segmentem „zalegający z płatnością” powiadomieniem push — kampania/powiadomienie do segmentu zalegający z płatnością powiadomieniem push.

## 7. ANALITYKA / RAPORTY / KPI









### 7.1 Dashboardy w aplikacji
- ✅ **[Feature]** Analityka (analytics, AnalitykaPage) — KPI operacyjne.
- ✅ **[Feature]** Pulpit (DashboardPage) — przegląd stanu systemu.
- ✅ **[Feature]** Prognoza (ForecastTab) — projekcja wolumenu.
- ✅ **[Feature]** Wykresy statystyk (StatsCharts, AnalysisTab).
- ✅ **[Feature]** Statystyki reklamacji (ComplaintStatsPage).
- ✅ **[Feature]** Feed zmian (ChangesFeedPage) — dziennik aktywności.
- 🔲 **[Python]** Raport wyjątków — tylko odchylenia wymagające uwagi.
- 🔲 **[Feature]** Konfigurowalne kafelki KPI na pulpicie per rola.
- 🔲 **[Python]** Eksport dowolnego widoku do Excel/CSV jednym kliknięciem.

### 7.2 KPI operacyjne kontenerów
- 🔲 **[PowerBI]** Terminowość dostaw kontenerów — % w oknie, opóźnienia.
- 🔲 **[Python]** Średni czas cyklu kontenera (port→magazyn→rozliczenie).
- 🔲 **[Python]** Wskaźnik kontenerów z demurrage — % i koszt.
- 🔲 **[Python]** Trend reklamacji per dostawca/materiał.
- 🔲 **[PowerBI]** Heatmapa obciążenia kolejki dzień×tydzień.
- 🔲 **[Python]** Prognoza spiętrzeń — kiedy kolejka przekroczy limit.
- 🔲 **[Python]** Alert KPI progowy — powiadomienie gdy wskaźnik poza normą.

### 7.3 Prognozy
- ✅ **[Python]** Prognoza wolumenu (ForecastTab) — istniejąca projekcja.
- 🔲 **[Python]** Prognoza ETA statystyczna z historii opóźnień trasy.
- 🔲 **[Python]** Prognoza obciążenia rozładunku na 2 tygodnie.
- 🔲 **[Python]** Sezonowość przyjęć (Holt-Winters) — planowanie obsady.

### 7.4 KPI (metryka × wymiar)
- 🔲 **[PowerBI]** KPI „terminowość dostaw” per dostawcy — % kontenerów w oknie w podziale na dostawcy, drill-down.
- 🔲 **[PowerBI]** KPI „terminowość dostaw” per spedytora — % kontenerów w oknie w podziale na spedytora, drill-down.
- 🔲 **[PowerBI]** KPI „terminowość dostaw” per przewoźnika — % kontenerów w oknie w podziale na przewoźnika, drill-down.
- 🔲 **[PowerBI]** KPI „terminowość dostaw” per armatora — % kontenerów w oknie w podziale na armatora, drill-down.
- 🔲 **[PowerBI]** KPI „terminowość dostaw” per portu — % kontenerów w oknie w podziale na portu, drill-down.
- 🔲 **[PowerBI]** KPI „terminowość dostaw” per magazynu — % kontenerów w oknie w podziale na magazynu, drill-down.
- 🔲 **[PowerBI]** KPI „terminowość dostaw” per klienta — % kontenerów w oknie w podziale na klienta, drill-down.
- 🔲 **[PowerBI]** KPI „terminowość dostaw” per materiału — % kontenerów w oknie w podziale na materiału, drill-down.
- 🔲 **[PowerBI]** KPI „terminowość dostaw” per kraju — % kontenerów w oknie w podziale na kraju, drill-down.
- 🔲 **[PowerBI]** KPI „terminowość dostaw” per trasy — % kontenerów w oknie w podziale na trasy, drill-down.
- 🔲 **[PowerBI]** KPI „terminowość dostaw” per typu kontenera — % kontenerów w oknie w podziale na typu kontenera, drill-down.
- 🔲 **[PowerBI]** KPI „terminowość dostaw” per agencji celnej — % kontenerów w oknie w podziale na agencji celnej, drill-down.
- 🔲 **[PowerBI]** KPI „średni czas cyklu” per dostawcy — dni port→magazyn w podziale na dostawcy, drill-down.
- 🔲 **[PowerBI]** KPI „średni czas cyklu” per spedytora — dni port→magazyn w podziale na spedytora, drill-down.
- 🔲 **[PowerBI]** KPI „średni czas cyklu” per przewoźnika — dni port→magazyn w podziale na przewoźnika, drill-down.
- 🔲 **[PowerBI]** KPI „średni czas cyklu” per armatora — dni port→magazyn w podziale na armatora, drill-down.
- 🔲 **[PowerBI]** KPI „średni czas cyklu” per portu — dni port→magazyn w podziale na portu, drill-down.
- 🔲 **[PowerBI]** KPI „średni czas cyklu” per magazynu — dni port→magazyn w podziale na magazynu, drill-down.
- 🔲 **[PowerBI]** KPI „średni czas cyklu” per klienta — dni port→magazyn w podziale na klienta, drill-down.
- 🔲 **[PowerBI]** KPI „średni czas cyklu” per materiału — dni port→magazyn w podziale na materiału, drill-down.
- 🔲 **[PowerBI]** KPI „średni czas cyklu” per kraju — dni port→magazyn w podziale na kraju, drill-down.
- 🔲 **[PowerBI]** KPI „średni czas cyklu” per trasy — dni port→magazyn w podziale na trasy, drill-down.
- 🔲 **[PowerBI]** KPI „średni czas cyklu” per typu kontenera — dni port→magazyn w podziale na typu kontenera, drill-down.
- 🔲 **[PowerBI]** KPI „średni czas cyklu” per agencji celnej — dni port→magazyn w podziale na agencji celnej, drill-down.
- 🔲 **[PowerBI]** KPI „koszt demurrage” per dostawcy — suma opłat postoju w podziale na dostawcy, drill-down.
- 🔲 **[PowerBI]** KPI „koszt demurrage” per spedytora — suma opłat postoju w podziale na spedytora, drill-down.
- 🔲 **[PowerBI]** KPI „koszt demurrage” per przewoźnika — suma opłat postoju w podziale na przewoźnika, drill-down.
- 🔲 **[PowerBI]** KPI „koszt demurrage” per armatora — suma opłat postoju w podziale na armatora, drill-down.
- 🔲 **[PowerBI]** KPI „koszt demurrage” per portu — suma opłat postoju w podziale na portu, drill-down.
- 🔲 **[PowerBI]** KPI „koszt demurrage” per magazynu — suma opłat postoju w podziale na magazynu, drill-down.
- 🔲 **[PowerBI]** KPI „koszt demurrage” per klienta — suma opłat postoju w podziale na klienta, drill-down.
- 🔲 **[PowerBI]** KPI „koszt demurrage” per materiału — suma opłat postoju w podziale na materiału, drill-down.
- 🔲 **[PowerBI]** KPI „koszt demurrage” per kraju — suma opłat postoju w podziale na kraju, drill-down.
- 🔲 **[PowerBI]** KPI „koszt demurrage” per trasy — suma opłat postoju w podziale na trasy, drill-down.
- 🔲 **[PowerBI]** KPI „koszt demurrage” per typu kontenera — suma opłat postoju w podziale na typu kontenera, drill-down.
- 🔲 **[PowerBI]** KPI „koszt demurrage” per agencji celnej — suma opłat postoju w podziale na agencji celnej, drill-down.
- 🔲 **[PowerBI]** KPI „liczba reklamacji” per dostawcy — szt. i trend w podziale na dostawcy, drill-down.
- 🔲 **[PowerBI]** KPI „liczba reklamacji” per spedytora — szt. i trend w podziale na spedytora, drill-down.
- 🔲 **[PowerBI]** KPI „liczba reklamacji” per przewoźnika — szt. i trend w podziale na przewoźnika, drill-down.
- 🔲 **[PowerBI]** KPI „liczba reklamacji” per armatora — szt. i trend w podziale na armatora, drill-down.
- 🔲 **[PowerBI]** KPI „liczba reklamacji” per portu — szt. i trend w podziale na portu, drill-down.
- 🔲 **[PowerBI]** KPI „liczba reklamacji” per magazynu — szt. i trend w podziale na magazynu, drill-down.
- 🔲 **[PowerBI]** KPI „liczba reklamacji” per klienta — szt. i trend w podziale na klienta, drill-down.
- 🔲 **[PowerBI]** KPI „liczba reklamacji” per materiału — szt. i trend w podziale na materiału, drill-down.
- 🔲 **[PowerBI]** KPI „liczba reklamacji” per kraju — szt. i trend w podziale na kraju, drill-down.
- 🔲 **[PowerBI]** KPI „liczba reklamacji” per trasy — szt. i trend w podziale na trasy, drill-down.
- 🔲 **[PowerBI]** KPI „liczba reklamacji” per typu kontenera — szt. i trend w podziale na typu kontenera, drill-down.
- 🔲 **[PowerBI]** KPI „liczba reklamacji” per agencji celnej — szt. i trend w podziale na agencji celnej, drill-down.
- 🔲 **[PowerBI]** KPI „dwell time” per dostawcy — czas przyjęcia w podziale na dostawcy, drill-down.
- 🔲 **[PowerBI]** KPI „dwell time” per spedytora — czas przyjęcia w podziale na spedytora, drill-down.
- 🔲 **[PowerBI]** KPI „dwell time” per przewoźnika — czas przyjęcia w podziale na przewoźnika, drill-down.
- 🔲 **[PowerBI]** KPI „dwell time” per armatora — czas przyjęcia w podziale na armatora, drill-down.
- 🔲 **[PowerBI]** KPI „dwell time” per portu — czas przyjęcia w podziale na portu, drill-down.
- 🔲 **[PowerBI]** KPI „dwell time” per magazynu — czas przyjęcia w podziale na magazynu, drill-down.
- 🔲 **[PowerBI]** KPI „dwell time” per klienta — czas przyjęcia w podziale na klienta, drill-down.
- 🔲 **[PowerBI]** KPI „dwell time” per materiału — czas przyjęcia w podziale na materiału, drill-down.
- 🔲 **[PowerBI]** KPI „dwell time” per kraju — czas przyjęcia w podziale na kraju, drill-down.
- 🔲 **[PowerBI]** KPI „dwell time” per trasy — czas przyjęcia w podziale na trasy, drill-down.
- 🔲 **[PowerBI]** KPI „dwell time” per typu kontenera — czas przyjęcia w podziale na typu kontenera, drill-down.
- 🔲 **[PowerBI]** KPI „dwell time” per agencji celnej — czas przyjęcia w podziale na agencji celnej, drill-down.
- 🔲 **[PowerBI]** KPI „koszt transportu” per dostawcy — koszt/kontener w podziale na dostawcy, drill-down.
- 🔲 **[PowerBI]** KPI „koszt transportu” per spedytora — koszt/kontener w podziale na spedytora, drill-down.
- 🔲 **[PowerBI]** KPI „koszt transportu” per przewoźnika — koszt/kontener w podziale na przewoźnika, drill-down.
- 🔲 **[PowerBI]** KPI „koszt transportu” per armatora — koszt/kontener w podziale na armatora, drill-down.
- 🔲 **[PowerBI]** KPI „koszt transportu” per portu — koszt/kontener w podziale na portu, drill-down.
- 🔲 **[PowerBI]** KPI „koszt transportu” per magazynu — koszt/kontener w podziale na magazynu, drill-down.
- 🔲 **[PowerBI]** KPI „koszt transportu” per klienta — koszt/kontener w podziale na klienta, drill-down.
- 🔲 **[PowerBI]** KPI „koszt transportu” per materiału — koszt/kontener w podziale na materiału, drill-down.
- 🔲 **[PowerBI]** KPI „koszt transportu” per kraju — koszt/kontener w podziale na kraju, drill-down.
- 🔲 **[PowerBI]** KPI „koszt transportu” per trasy — koszt/kontener w podziale na trasy, drill-down.
- 🔲 **[PowerBI]** KPI „koszt transportu” per typu kontenera — koszt/kontener w podziale na typu kontenera, drill-down.
- 🔲 **[PowerBI]** KPI „koszt transportu” per agencji celnej — koszt/kontener w podziale na agencji celnej, drill-down.
- 🔲 **[PowerBI]** KPI „dokładność ETA” per dostawcy — odchylenie prognozy w podziale na dostawcy, drill-down.
- 🔲 **[PowerBI]** KPI „dokładność ETA” per spedytora — odchylenie prognozy w podziale na spedytora, drill-down.
- 🔲 **[PowerBI]** KPI „dokładność ETA” per przewoźnika — odchylenie prognozy w podziale na przewoźnika, drill-down.
- 🔲 **[PowerBI]** KPI „dokładność ETA” per armatora — odchylenie prognozy w podziale na armatora, drill-down.
- 🔲 **[PowerBI]** KPI „dokładność ETA” per portu — odchylenie prognozy w podziale na portu, drill-down.
- 🔲 **[PowerBI]** KPI „dokładność ETA” per magazynu — odchylenie prognozy w podziale na magazynu, drill-down.
- 🔲 **[PowerBI]** KPI „dokładność ETA” per klienta — odchylenie prognozy w podziale na klienta, drill-down.
- 🔲 **[PowerBI]** KPI „dokładność ETA” per materiału — odchylenie prognozy w podziale na materiału, drill-down.
- 🔲 **[PowerBI]** KPI „dokładność ETA” per kraju — odchylenie prognozy w podziale na kraju, drill-down.
- 🔲 **[PowerBI]** KPI „dokładność ETA” per trasy — odchylenie prognozy w podziale na trasy, drill-down.
- 🔲 **[PowerBI]** KPI „dokładność ETA” per typu kontenera — odchylenie prognozy w podziale na typu kontenera, drill-down.
- 🔲 **[PowerBI]** KPI „dokładność ETA” per agencji celnej — odchylenie prognozy w podziale na agencji celnej, drill-down.
- 🔲 **[PowerBI]** KPI „wolumen” per dostawcy — liczba kontenerów w podziale na dostawcy, drill-down.
- 🔲 **[PowerBI]** KPI „wolumen” per spedytora — liczba kontenerów w podziale na spedytora, drill-down.
- 🔲 **[PowerBI]** KPI „wolumen” per przewoźnika — liczba kontenerów w podziale na przewoźnika, drill-down.
- 🔲 **[PowerBI]** KPI „wolumen” per armatora — liczba kontenerów w podziale na armatora, drill-down.
- 🔲 **[PowerBI]** KPI „wolumen” per portu — liczba kontenerów w podziale na portu, drill-down.
- 🔲 **[PowerBI]** KPI „wolumen” per magazynu — liczba kontenerów w podziale na magazynu, drill-down.
- 🔲 **[PowerBI]** KPI „wolumen” per klienta — liczba kontenerów w podziale na klienta, drill-down.
- 🔲 **[PowerBI]** KPI „wolumen” per materiału — liczba kontenerów w podziale na materiału, drill-down.
- 🔲 **[PowerBI]** KPI „wolumen” per kraju — liczba kontenerów w podziale na kraju, drill-down.
- 🔲 **[PowerBI]** KPI „wolumen” per trasy — liczba kontenerów w podziale na trasy, drill-down.
- 🔲 **[PowerBI]** KPI „wolumen” per typu kontenera — liczba kontenerów w podziale na typu kontenera, drill-down.
- 🔲 **[PowerBI]** KPI „wolumen” per agencji celnej — liczba kontenerów w podziale na agencji celnej, drill-down.

### 7.5 Raporty okresowe per metryka
- 🔲 **[Python]** Raport tygodniowy: terminowość dostaw — tygodniowy zestawienie % kontenerów w oknie z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport miesięczny: terminowość dostaw — miesięczny zestawienie % kontenerów w oknie z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport tygodniowy: średni czas cyklu — tygodniowy zestawienie dni port→magazyn z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport miesięczny: średni czas cyklu — miesięczny zestawienie dni port→magazyn z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport tygodniowy: koszt demurrage — tygodniowy zestawienie suma opłat postoju z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport miesięczny: koszt demurrage — miesięczny zestawienie suma opłat postoju z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport tygodniowy: liczba reklamacji — tygodniowy zestawienie szt. i trend z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport miesięczny: liczba reklamacji — miesięczny zestawienie szt. i trend z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport tygodniowy: dwell time — tygodniowy zestawienie czas przyjęcia z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport miesięczny: dwell time — miesięczny zestawienie czas przyjęcia z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport tygodniowy: koszt transportu — tygodniowy zestawienie koszt/kontener z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport miesięczny: koszt transportu — miesięczny zestawienie koszt/kontener z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport tygodniowy: dokładność ETA — tygodniowy zestawienie odchylenie prognozy z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport miesięczny: dokładność ETA — miesięczny zestawienie odchylenie prognozy z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport tygodniowy: wolumen — tygodniowy zestawienie liczba kontenerów z porównaniem do poprzedniego okresu.
- 🔲 **[Python]** Raport miesięczny: wolumen — miesięczny zestawienie liczba kontenerów z porównaniem do poprzedniego okresu.

### 7.6 Cele KPI
- 🔲 **[Feature]** Cel (target) dla KPI „terminowość dostaw” — ustawienie wartości docelowej % kontenerów w oknie i wizualizacja odchylenia.
- 🔲 **[Feature]** Cel (target) dla KPI „średni czas cyklu” — ustawienie wartości docelowej dni port→magazyn i wizualizacja odchylenia.
- 🔲 **[Feature]** Cel (target) dla KPI „koszt demurrage” — ustawienie wartości docelowej suma opłat postoju i wizualizacja odchylenia.
- 🔲 **[Feature]** Cel (target) dla KPI „liczba reklamacji” — ustawienie wartości docelowej szt. i trend i wizualizacja odchylenia.
- 🔲 **[Feature]** Cel (target) dla KPI „dwell time” — ustawienie wartości docelowej czas przyjęcia i wizualizacja odchylenia.
- 🔲 **[Feature]** Cel (target) dla KPI „koszt transportu” — ustawienie wartości docelowej koszt/kontener i wizualizacja odchylenia.
- 🔲 **[Feature]** Cel (target) dla KPI „dokładność ETA” — ustawienie wartości docelowej odchylenie prognozy i wizualizacja odchylenia.
- 🔲 **[Feature]** Cel (target) dla KPI „wolumen” — ustawienie wartości docelowej liczba kontenerów i wizualizacja odchylenia.

### 7.7 Alerty progowe KPI (metryka × kanał)
- 🔲 **[Python]** Alert progowy KPI „terminowość dostaw” mailem — gdy % kontenerów w oknie przekracza próg → powiadomienie mailem.
- 🔲 **[Teams]** Alert progowy KPI „terminowość dostaw” kartą w Teams — gdy % kontenerów w oknie przekracza próg → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert progowy KPI „terminowość dostaw” SMS-em — gdy % kontenerów w oknie przekracza próg → powiadomienie SMS-em.
- 🔲 **[Python]** Alert progowy KPI „terminowość dostaw” na dashboardzie — gdy % kontenerów w oknie przekracza próg → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert progowy KPI „terminowość dostaw” powiadomieniem push — gdy % kontenerów w oknie przekracza próg → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert progowy KPI „średni czas cyklu” mailem — gdy dni port→magazyn przekracza próg → powiadomienie mailem.
- 🔲 **[Teams]** Alert progowy KPI „średni czas cyklu” kartą w Teams — gdy dni port→magazyn przekracza próg → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert progowy KPI „średni czas cyklu” SMS-em — gdy dni port→magazyn przekracza próg → powiadomienie SMS-em.
- 🔲 **[Python]** Alert progowy KPI „średni czas cyklu” na dashboardzie — gdy dni port→magazyn przekracza próg → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert progowy KPI „średni czas cyklu” powiadomieniem push — gdy dni port→magazyn przekracza próg → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert progowy KPI „koszt demurrage” mailem — gdy suma opłat postoju przekracza próg → powiadomienie mailem.
- 🔲 **[Teams]** Alert progowy KPI „koszt demurrage” kartą w Teams — gdy suma opłat postoju przekracza próg → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert progowy KPI „koszt demurrage” SMS-em — gdy suma opłat postoju przekracza próg → powiadomienie SMS-em.
- 🔲 **[Python]** Alert progowy KPI „koszt demurrage” na dashboardzie — gdy suma opłat postoju przekracza próg → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert progowy KPI „koszt demurrage” powiadomieniem push — gdy suma opłat postoju przekracza próg → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert progowy KPI „liczba reklamacji” mailem — gdy szt. i trend przekracza próg → powiadomienie mailem.
- 🔲 **[Teams]** Alert progowy KPI „liczba reklamacji” kartą w Teams — gdy szt. i trend przekracza próg → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert progowy KPI „liczba reklamacji” SMS-em — gdy szt. i trend przekracza próg → powiadomienie SMS-em.
- 🔲 **[Python]** Alert progowy KPI „liczba reklamacji” na dashboardzie — gdy szt. i trend przekracza próg → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert progowy KPI „liczba reklamacji” powiadomieniem push — gdy szt. i trend przekracza próg → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert progowy KPI „dwell time” mailem — gdy czas przyjęcia przekracza próg → powiadomienie mailem.
- 🔲 **[Teams]** Alert progowy KPI „dwell time” kartą w Teams — gdy czas przyjęcia przekracza próg → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert progowy KPI „dwell time” SMS-em — gdy czas przyjęcia przekracza próg → powiadomienie SMS-em.
- 🔲 **[Python]** Alert progowy KPI „dwell time” na dashboardzie — gdy czas przyjęcia przekracza próg → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert progowy KPI „dwell time” powiadomieniem push — gdy czas przyjęcia przekracza próg → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert progowy KPI „koszt transportu” mailem — gdy koszt/kontener przekracza próg → powiadomienie mailem.
- 🔲 **[Teams]** Alert progowy KPI „koszt transportu” kartą w Teams — gdy koszt/kontener przekracza próg → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert progowy KPI „koszt transportu” SMS-em — gdy koszt/kontener przekracza próg → powiadomienie SMS-em.
- 🔲 **[Python]** Alert progowy KPI „koszt transportu” na dashboardzie — gdy koszt/kontener przekracza próg → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert progowy KPI „koszt transportu” powiadomieniem push — gdy koszt/kontener przekracza próg → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert progowy KPI „dokładność ETA” mailem — gdy odchylenie prognozy przekracza próg → powiadomienie mailem.
- 🔲 **[Teams]** Alert progowy KPI „dokładność ETA” kartą w Teams — gdy odchylenie prognozy przekracza próg → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert progowy KPI „dokładność ETA” SMS-em — gdy odchylenie prognozy przekracza próg → powiadomienie SMS-em.
- 🔲 **[Python]** Alert progowy KPI „dokładność ETA” na dashboardzie — gdy odchylenie prognozy przekracza próg → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert progowy KPI „dokładność ETA” powiadomieniem push — gdy odchylenie prognozy przekracza próg → powiadomienie powiadomieniem push.
- 🔲 **[Python]** Alert progowy KPI „wolumen” mailem — gdy liczba kontenerów przekracza próg → powiadomienie mailem.
- 🔲 **[Teams]** Alert progowy KPI „wolumen” kartą w Teams — gdy liczba kontenerów przekracza próg → powiadomienie kartą w Teams.
- 🔲 **[Python]** Alert progowy KPI „wolumen” SMS-em — gdy liczba kontenerów przekracza próg → powiadomienie SMS-em.
- 🔲 **[Python]** Alert progowy KPI „wolumen” na dashboardzie — gdy liczba kontenerów przekracza próg → powiadomienie na dashboardzie.
- 🔲 **[Python]** Alert progowy KPI „wolumen” powiadomieniem push — gdy liczba kontenerów przekracza próg → powiadomienie powiadomieniem push.

### 7.8 Prognozy i widgety KPI
- 🔲 **[Python]** Prognoza KPI „terminowość dostaw” — projekcja % w oknie na kolejny okres (statystyczna).
- 🔲 **[Feature]** Widget pulpitu: KPI „terminowość dostaw” — kafelek z bieżącą wartością % w oknie i mini-trendem.
- 🔲 **[Python]** Prognoza KPI „średni czas cyklu” — projekcja dni port→magazyn na kolejny okres (statystyczna).
- 🔲 **[Feature]** Widget pulpitu: KPI „średni czas cyklu” — kafelek z bieżącą wartością dni port→magazyn i mini-trendem.
- 🔲 **[Python]** Prognoza KPI „koszt demurrage” — projekcja suma opłat na kolejny okres (statystyczna).
- 🔲 **[Feature]** Widget pulpitu: KPI „koszt demurrage” — kafelek z bieżącą wartością suma opłat i mini-trendem.
- 🔲 **[Python]** Prognoza KPI „liczba reklamacji” — projekcja szt./trend na kolejny okres (statystyczna).
- 🔲 **[Feature]** Widget pulpitu: KPI „liczba reklamacji” — kafelek z bieżącą wartością szt./trend i mini-trendem.
- 🔲 **[Python]** Prognoza KPI „dwell time” — projekcja czas przyjęcia na kolejny okres (statystyczna).
- 🔲 **[Feature]** Widget pulpitu: KPI „dwell time” — kafelek z bieżącą wartością czas przyjęcia i mini-trendem.
- 🔲 **[Python]** Prognoza KPI „koszt transportu” — projekcja koszt/kontener na kolejny okres (statystyczna).
- 🔲 **[Feature]** Widget pulpitu: KPI „koszt transportu” — kafelek z bieżącą wartością koszt/kontener i mini-trendem.
- 🔲 **[Python]** Prognoza KPI „dokładność ETA” — projekcja odchylenie prognozy na kolejny okres (statystyczna).
- 🔲 **[Feature]** Widget pulpitu: KPI „dokładność ETA” — kafelek z bieżącą wartością odchylenie prognozy i mini-trendem.
- 🔲 **[Python]** Prognoza KPI „wolumen” — projekcja liczba kontenerów na kolejny okres (statystyczna).
- 🔲 **[Feature]** Widget pulpitu: KPI „wolumen” — kafelek z bieżącą wartością liczba kontenerów i mini-trendem.

## 8. INTEGRACJE









### 8.1 SAP
- ✅ **[API]** Import zamówień SAP (SapOrder, imports) — LFA1/EKKO.
- 🔲 **[Python]** Eksport statusów kontenerów do SAP (read-back).
- 🔲 **[Python]** Synchronizacja master data materiałów SAP↔TIMPORYE.
- 🔲 **[Python]** Rekoncyliacja stanów SAP vs cache paletowy.
- 🔲 **[Python]** Parser IDoc (DELVRY/WHSCON) do zdarzeń kontenera.

### 8.2 Power BI / dane
- ✅ **[API]** Token Power BI (PowerBIToken) — integracja raportowa.
- 🔲 **[PowerBI]** Zbiór danych kontenerów do Power BI (endpoint OData/REST).
- 🔲 **[Excel]** Power Query po API TIMPORYE — samoodświeżający raport.
- 🔲 **[Python]** Eksport nocny snapshotu do hurtowni analitycznej.

### 8.3 AIS / tracking zewnętrzny
- ✅ **[API]** AIS aisstream kolektor (ais_loop) — pozycje po nazwie statku.
- 🔲 **[API]** Drugie źródło trackingu (Project44/Searates) — fallback.
- 🔲 **[API]** Rotacja klucza AIS + env w Coolify (operacyjne).

### 8.4 Powiadomienia (Teams/SMTP/SMS)
- ✅ **[Feature]** Powiadomienia + reguły (notifications, Notification/NotificationRule).
- ✅ **[SMTP]** Wysyłka maili (awizacja, digesty, kolejka).
- ✅ **[Feature]** SMS (SmsMessage) — powiadomienia SMS (Twilio).
- 🔲 **[Teams]** Webhook Teams — alerty demurrage/opóźnień na kanał.
- 🔲 **[Teams]** Karta adaptacyjna statusu kontenera w Teams.
- 🔲 **[n8n]** Router powiadomień — jedno zdarzenie → wybór kanału wg reguł.
- 🔲 **[Feature]** Preferencje kanału powiadomień per użytkownik.

### 8.5 n8n / SharePoint
- 🔲 **[n8n]** Most TIMPORYE→n8n — webhook zdarzeń do orkiestracji.
- 🔲 **[SharePoint]** Auto-archiwum dokumentów kontenera do biblioteki SharePoint.
- 🔲 **[SharePoint]** Lista awizacji jako zewnętrzny widok dla partnerów.
- 🔲 **[n8n]** Pipeline maili z załącznikami → OCR → podpięcie do kontenera.

### 8.6 Webhooki zdarzeń per etap (n8n)
- 🔲 **[n8n]** Webhook zdarzenia „potwierdzenie bookingu u armatora” — emit zdarzenia do n8n gdy kontener wchodzi w etap potwierdzenie bookingu u armatora.
- 🔲 **[n8n]** Webhook zdarzenia „załadunek w porcie nadania” — emit zdarzenia do n8n gdy kontener wchodzi w etap załadunek w porcie nadania.
- 🔲 **[n8n]** Webhook zdarzenia „wypłynięcie statku (ETD)” — emit zdarzenia do n8n gdy kontener wchodzi w etap wypłynięcie statku (ETD).
- 🔲 **[n8n]** Webhook zdarzenia „w tranzycie morskim” — emit zdarzenia do n8n gdy kontener wchodzi w etap w tranzycie morskim.
- 🔲 **[n8n]** Webhook zdarzenia „przeładunek/transshipment” — emit zdarzenia do n8n gdy kontener wchodzi w etap przeładunek/transshipment.
- 🔲 **[n8n]** Webhook zdarzenia „przybycie do portu (ETA)” — emit zdarzenia do n8n gdy kontener wchodzi w etap przybycie do portu (ETA).
- 🔲 **[n8n]** Webhook zdarzenia „wyładunek ze statku” — emit zdarzenia do n8n gdy kontener wchodzi w etap wyładunek ze statku.
- 🔲 **[n8n]** Webhook zdarzenia „składowanie w porcie” — emit zdarzenia do n8n gdy kontener wchodzi w etap składowanie w porcie.
- 🔲 **[n8n]** Webhook zdarzenia „zgłoszenie celne” — emit zdarzenia do n8n gdy kontener wchodzi w etap zgłoszenie celne.
- 🔲 **[n8n]** Webhook zdarzenia „odprawa celna w toku” — emit zdarzenia do n8n gdy kontener wchodzi w etap odprawa celna w toku.
- 🔲 **[n8n]** Webhook zdarzenia „zwolnienie celne” — emit zdarzenia do n8n gdy kontener wchodzi w etap zwolnienie celne.
- 🔲 **[n8n]** Webhook zdarzenia „awizacja dostawy” — emit zdarzenia do n8n gdy kontener wchodzi w etap awizacja dostawy.
- 🔲 **[n8n]** Webhook zdarzenia „transport z portu do magazynu” — emit zdarzenia do n8n gdy kontener wchodzi w etap transport z portu do magazynu.
- 🔲 **[n8n]** Webhook zdarzenia „zgłoszenie na bramie magazynu” — emit zdarzenia do n8n gdy kontener wchodzi w etap zgłoszenie na bramie magazynu.
- 🔲 **[n8n]** Webhook zdarzenia „rozładunek kontenera” — emit zdarzenia do n8n gdy kontener wchodzi w etap rozładunek kontenera.
- 🔲 **[n8n]** Webhook zdarzenia „kontrola jakości towaru” — emit zdarzenia do n8n gdy kontener wchodzi w etap kontrola jakości towaru.
- 🔲 **[n8n]** Webhook zdarzenia „przyjęcie na stan” — emit zdarzenia do n8n gdy kontener wchodzi w etap przyjęcie na stan.
- 🔲 **[n8n]** Webhook zdarzenia „zwrot pustego kontenera” — emit zdarzenia do n8n gdy kontener wchodzi w etap zwrot pustego kontenera.
- 🔲 **[n8n]** Webhook zdarzenia „rozliczenie kosztów kontenera” — emit zdarzenia do n8n gdy kontener wchodzi w etap rozliczenie kosztów kontenera.
- 🔲 **[n8n]** Webhook zdarzenia „zamknięcie sprawy kontenera” — emit zdarzenia do n8n gdy kontener wchodzi w etap zamknięcie sprawy kontenera.

### 8.7 Routing alertów (metryka × kanał)
- 🔲 **[Python]** Kanał mail: alert „terminowość dostaw” — routing alertu terminowość dostaw mailem wg reguł powiadomień.
- 🔲 **[Python]** Kanał mail: alert „średni czas cyklu” — routing alertu średni czas cyklu mailem wg reguł powiadomień.
- 🔲 **[Python]** Kanał mail: alert „koszt demurrage” — routing alertu koszt demurrage mailem wg reguł powiadomień.
- 🔲 **[Python]** Kanał mail: alert „liczba reklamacji” — routing alertu liczba reklamacji mailem wg reguł powiadomień.
- 🔲 **[Python]** Kanał mail: alert „dwell time” — routing alertu dwell time mailem wg reguł powiadomień.
- 🔲 **[Teams]** Kanał Teams: alert „terminowość dostaw” — routing alertu terminowość dostaw kartą w Teams wg reguł powiadomień.
- 🔲 **[Teams]** Kanał Teams: alert „średni czas cyklu” — routing alertu średni czas cyklu kartą w Teams wg reguł powiadomień.
- 🔲 **[Teams]** Kanał Teams: alert „koszt demurrage” — routing alertu koszt demurrage kartą w Teams wg reguł powiadomień.
- 🔲 **[Teams]** Kanał Teams: alert „liczba reklamacji” — routing alertu liczba reklamacji kartą w Teams wg reguł powiadomień.
- 🔲 **[Teams]** Kanał Teams: alert „dwell time” — routing alertu dwell time kartą w Teams wg reguł powiadomień.
- 🔲 **[Python]** Kanał SMS: alert „terminowość dostaw” — routing alertu terminowość dostaw SMS-em wg reguł powiadomień.
- 🔲 **[Python]** Kanał SMS: alert „średni czas cyklu” — routing alertu średni czas cyklu SMS-em wg reguł powiadomień.
- 🔲 **[Python]** Kanał SMS: alert „koszt demurrage” — routing alertu koszt demurrage SMS-em wg reguł powiadomień.
- 🔲 **[Python]** Kanał SMS: alert „liczba reklamacji” — routing alertu liczba reklamacji SMS-em wg reguł powiadomień.
- 🔲 **[Python]** Kanał SMS: alert „dwell time” — routing alertu dwell time SMS-em wg reguł powiadomień.
- 🔲 **[Python]** Kanał dashboard: alert „terminowość dostaw” — routing alertu terminowość dostaw na dashboardzie wg reguł powiadomień.
- 🔲 **[Python]** Kanał dashboard: alert „średni czas cyklu” — routing alertu średni czas cyklu na dashboardzie wg reguł powiadomień.
- 🔲 **[Python]** Kanał dashboard: alert „koszt demurrage” — routing alertu koszt demurrage na dashboardzie wg reguł powiadomień.
- 🔲 **[Python]** Kanał dashboard: alert „liczba reklamacji” — routing alertu liczba reklamacji na dashboardzie wg reguł powiadomień.
- 🔲 **[Python]** Kanał dashboard: alert „dwell time” — routing alertu dwell time na dashboardzie wg reguł powiadomień.
- 🔲 **[Python]** Kanał push: alert „terminowość dostaw” — routing alertu terminowość dostaw powiadomieniem push wg reguł powiadomień.
- 🔲 **[Python]** Kanał push: alert „średni czas cyklu” — routing alertu średni czas cyklu powiadomieniem push wg reguł powiadomień.
- 🔲 **[Python]** Kanał push: alert „koszt demurrage” — routing alertu koszt demurrage powiadomieniem push wg reguł powiadomień.
- 🔲 **[Python]** Kanał push: alert „liczba reklamacji” — routing alertu liczba reklamacji powiadomieniem push wg reguł powiadomień.
- 🔲 **[Python]** Kanał push: alert „dwell time” — routing alertu dwell time powiadomieniem push wg reguł powiadomień.

### 8.8 Niezawodność integracji (per system)
- 🔲 **[Python]** Healthcheck integracji SAP — cykliczny ping SAP + alert przy awarii/timeout.
- 🔲 **[Python]** Retry+backoff dla SAP — dekorator ponawiania wywołań SAP z dead-letter.
- 🔲 **[Python]** Healthcheck integracji Compare/CIPL — cykliczny ping Compare/CIPL + alert przy awarii/timeout.
- 🔲 **[Python]** Retry+backoff dla Compare/CIPL — dekorator ponawiania wywołań Compare/CIPL z dead-letter.
- 🔲 **[Python]** Healthcheck integracji AIS — cykliczny ping AIS + alert przy awarii/timeout.
- 🔲 **[Python]** Retry+backoff dla AIS — dekorator ponawiania wywołań AIS z dead-letter.
- 🔲 **[Python]** Healthcheck integracji Power BI — cykliczny ping Power BI + alert przy awarii/timeout.
- 🔲 **[Python]** Retry+backoff dla Power BI — dekorator ponawiania wywołań Power BI z dead-letter.
- 🔲 **[Python]** Healthcheck integracji Twilio SMS — cykliczny ping Twilio SMS + alert przy awarii/timeout.
- 🔲 **[Python]** Retry+backoff dla Twilio SMS — dekorator ponawiania wywołań Twilio SMS z dead-letter.
- 🔲 **[Python]** Healthcheck integracji SMTP — cykliczny ping SMTP + alert przy awarii/timeout.
- 🔲 **[Python]** Retry+backoff dla SMTP — dekorator ponawiania wywołań SMTP z dead-letter.
- 🔲 **[Python]** Healthcheck integracji SharePoint — cykliczny ping SharePoint + alert przy awarii/timeout.
- 🔲 **[Python]** Retry+backoff dla SharePoint — dekorator ponawiania wywołań SharePoint z dead-letter.
- 🔲 **[Python]** Healthcheck integracji n8n — cykliczny ping n8n + alert przy awarii/timeout.
- 🔲 **[Python]** Retry+backoff dla n8n — dekorator ponawiania wywołań n8n z dead-letter.
- 🔲 **[Python]** Healthcheck integracji TARIC — cykliczny ping TARIC + alert przy awarii/timeout.
- 🔲 **[Python]** Retry+backoff dla TARIC — dekorator ponawiania wywołań TARIC z dead-letter.
- 🔲 **[Python]** Healthcheck integracji VIES/biała lista — cykliczny ping VIES/biała lista + alert przy awarii/timeout.
- 🔲 **[Python]** Retry+backoff dla VIES/biała lista — dekorator ponawiania wywołań VIES/biała lista z dead-letter.
- 🔲 **[Python]** Healthcheck integracji GUS/KRS — cykliczny ping GUS/KRS + alert przy awarii/timeout.
- 🔲 **[Python]** Retry+backoff dla GUS/KRS — dekorator ponawiania wywołań GUS/KRS z dead-letter.
- 🔲 **[Python]** Healthcheck integracji aisstream — cykliczny ping aisstream + alert przy awarii/timeout.
- 🔲 **[Python]** Retry+backoff dla aisstream — dekorator ponawiania wywołań aisstream z dead-letter.

### 8.9 Szablony n8n per dokument
- 🔲 **[n8n]** Szablon n8n: obieg dokumentu CIPL — mail z CIPL → OCR → walidacja → podpięcie do kontenera → archiwum.
- 🔲 **[n8n]** Szablon n8n: obieg dokumentu BL — mail z BL → OCR → walidacja → podpięcie do kontenera → archiwum.
- 🔲 **[n8n]** Szablon n8n: obieg dokumentu świadectwo pochodzenia — mail z świadectwo pochodzenia → OCR → walidacja → podpięcie do kontenera → archiwum.
- 🔲 **[n8n]** Szablon n8n: obieg dokumentu EUR.1 — mail z EUR.1 → OCR → walidacja → podpięcie do kontenera → archiwum.
- 🔲 **[n8n]** Szablon n8n: obieg dokumentu SAD — mail z SAD → OCR → walidacja → podpięcie do kontenera → archiwum.
- 🔲 **[n8n]** Szablon n8n: obieg dokumentu packing list — mail z packing list → OCR → walidacja → podpięcie do kontenera → archiwum.
- 🔲 **[n8n]** Szablon n8n: obieg dokumentu MSDS — mail z MSDS → OCR → walidacja → podpięcie do kontenera → archiwum.
- 🔲 **[n8n]** Szablon n8n: obieg dokumentu certyfikat jakości — mail z certyfikat jakości → OCR → walidacja → podpięcie do kontenera → archiwum.
- 🔲 **[n8n]** Szablon n8n: obieg dokumentu świadectwo fumigacji — mail z świadectwo fumigacji → OCR → walidacja → podpięcie do kontenera → archiwum.
- 🔲 **[n8n]** Szablon n8n: obieg dokumentu weight certificate — mail z weight certificate → OCR → walidacja → podpięcie do kontenera → archiwum.
- 🔲 **[n8n]** Szablon n8n: obieg dokumentu polisa ubezpieczeniowa — mail z polisa ubezpieczeniowa → OCR → walidacja → podpięcie do kontenera → archiwum.
- 🔲 **[n8n]** Szablon n8n: obieg dokumentu umowa przewozu — mail z umowa przewozu → OCR → walidacja → podpięcie do kontenera → archiwum.

### 8.10 Szablony n8n per metryka
- 🔲 **[n8n]** Szablon n8n: agregacja KPI „terminowość dostaw” — cron → policz % kontenerów w oknie → wypchnij do dashboardu/Teams.
- 🔲 **[n8n]** Szablon n8n: agregacja KPI „średni czas cyklu” — cron → policz dni port→magazyn → wypchnij do dashboardu/Teams.
- 🔲 **[n8n]** Szablon n8n: agregacja KPI „koszt demurrage” — cron → policz suma opłat postoju → wypchnij do dashboardu/Teams.
- 🔲 **[n8n]** Szablon n8n: agregacja KPI „liczba reklamacji” — cron → policz szt. i trend → wypchnij do dashboardu/Teams.
- 🔲 **[n8n]** Szablon n8n: agregacja KPI „dwell time” — cron → policz czas przyjęcia → wypchnij do dashboardu/Teams.
- 🔲 **[n8n]** Szablon n8n: agregacja KPI „koszt transportu” — cron → policz koszt/kontener → wypchnij do dashboardu/Teams.
- 🔲 **[n8n]** Szablon n8n: agregacja KPI „dokładność ETA” — cron → policz odchylenie prognozy → wypchnij do dashboardu/Teams.
- 🔲 **[n8n]** Szablon n8n: agregacja KPI „wolumen” — cron → policz liczba kontenerów → wypchnij do dashboardu/Teams.

### 8.11 API filtrowane per wymiar
- 🔲 **[API]** Endpoint REST z filtrem per dostawcy — parametryzowane API zwracające dane filtrowane po dostawcy.
- 🔲 **[API]** Endpoint REST z filtrem per spedytora — parametryzowane API zwracające dane filtrowane po spedytora.
- 🔲 **[API]** Endpoint REST z filtrem per przewoźnika — parametryzowane API zwracające dane filtrowane po przewoźnika.
- 🔲 **[API]** Endpoint REST z filtrem per armatora — parametryzowane API zwracające dane filtrowane po armatora.
- 🔲 **[API]** Endpoint REST z filtrem per portu — parametryzowane API zwracające dane filtrowane po portu.
- 🔲 **[API]** Endpoint REST z filtrem per magazynu — parametryzowane API zwracające dane filtrowane po magazynu.
- 🔲 **[API]** Endpoint REST z filtrem per klienta — parametryzowane API zwracające dane filtrowane po klienta.
- 🔲 **[API]** Endpoint REST z filtrem per materiału — parametryzowane API zwracające dane filtrowane po materiału.
- 🔲 **[API]** Endpoint REST z filtrem per kraju — parametryzowane API zwracające dane filtrowane po kraju.
- 🔲 **[API]** Endpoint REST z filtrem per trasy — parametryzowane API zwracające dane filtrowane po trasy.
- 🔲 **[API]** Endpoint REST z filtrem per typu kontenera — parametryzowane API zwracające dane filtrowane po typu kontenera.
- 🔲 **[API]** Endpoint REST z filtrem per agencji celnej — parametryzowane API zwracające dane filtrowane po agencji celnej.

### 8.12 Eksport hurtowniany per wymiar
- 🔲 **[Python]** Eksport do hurtowni per dostawcy — nocny snapshot danych w podziale na dostawcy.
- 🔲 **[Python]** Eksport do hurtowni per spedytora — nocny snapshot danych w podziale na spedytora.
- 🔲 **[Python]** Eksport do hurtowni per przewoźnika — nocny snapshot danych w podziale na przewoźnika.
- 🔲 **[Python]** Eksport do hurtowni per armatora — nocny snapshot danych w podziale na armatora.
- 🔲 **[Python]** Eksport do hurtowni per portu — nocny snapshot danych w podziale na portu.
- 🔲 **[Python]** Eksport do hurtowni per magazynu — nocny snapshot danych w podziale na magazynu.
- 🔲 **[Python]** Eksport do hurtowni per klienta — nocny snapshot danych w podziale na klienta.
- 🔲 **[Python]** Eksport do hurtowni per materiału — nocny snapshot danych w podziale na materiału.
- 🔲 **[Python]** Eksport do hurtowni per kraju — nocny snapshot danych w podziale na kraju.
- 🔲 **[Python]** Eksport do hurtowni per trasy — nocny snapshot danych w podziale na trasy.
- 🔲 **[Python]** Eksport do hurtowni per typu kontenera — nocny snapshot danych w podziale na typu kontenera.
- 🔲 **[Python]** Eksport do hurtowni per agencji celnej — nocny snapshot danych w podziale na agencji celnej.

## 9. AUTOMATYZACJE TŁA (pętle / cron / digesty)









- ✅ **[Python]** Pętla demurrage (demurrage_loop) — alerty postoju.
- ✅ **[Python]** Pętla opóźnień odpraw (customs_delay_loop).
- ✅ **[Python]** Pętla przypomnień reklamacji (complaint_reminder_loop).
- ✅ **[Python]** Pętla pilnych wywołań palet (pallet_urgent_loop).
- ✅ **[Python]** Pętla trackingu (tracking_loop).
- ✅ **[Python]** Pętla AIS (ais_loop).
- ✅ **[Python]** Digest dzienny (daily_digest_loop).
- ✅ **[Python]** Digest tygodniowy (weekly_digest_loop).
- ✅ **[Python]** Weryfikacja backupu (verify_backup_loop).
- 🔲 **[Python]** Pętla alertu ETA — zmiana ETA >X dni → powiadomienie.
- 🔲 **[Python]** Pętla free-time — próg 7/3/1 dzień do końca wolnych dni.
- 🔲 **[Python]** Pętla SLA odpraw — sprawa bez zmiany >X dni.
- 🔲 **[Python]** Pętla „kontener utknął" — brak zmiany statusu >X dni (W5).
- 🔲 **[Python]** Pętla healthcheck integracji (AIS/SAP/Compare) — alert awarii.
- 🔲 **[Python]** Pętla czyszczenia starych ClientError/logów (retencja).
- 🔲 **[Python]** Pętla przypomnień awizacji (dzień przed).
- 🔲 **[Python]** Digest poranny dla magazynu (co przyjąć dziś).
- 🔲 **[Python]** Digest dla spedycji (otwarte zlecenia/wyceny).
- 🔲 **[Python]** Pętla auto-eskalacji niezatwierdzonych PO.
- 🔲 **[Python]** Pętla odświeżania kongestii portów.

### 9.1 Pętle nadzoru per etap
- 🔲 **[Python]** Pętla nadzoru etapu „potwierdzenie bookingu u armatora” — cron: wykryj kontenery zbyt długo w etapie potwierdzenie bookingu u armatora → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „załadunek w porcie nadania” — cron: wykryj kontenery zbyt długo w etapie załadunek w porcie nadania → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „wypłynięcie statku (ETD)” — cron: wykryj kontenery zbyt długo w etapie wypłynięcie statku (ETD) → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „w tranzycie morskim” — cron: wykryj kontenery zbyt długo w etapie w tranzycie morskim → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „przeładunek/transshipment” — cron: wykryj kontenery zbyt długo w etapie przeładunek/transshipment → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „przybycie do portu (ETA)” — cron: wykryj kontenery zbyt długo w etapie przybycie do portu (ETA) → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „wyładunek ze statku” — cron: wykryj kontenery zbyt długo w etapie wyładunek ze statku → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „składowanie w porcie” — cron: wykryj kontenery zbyt długo w etapie składowanie w porcie → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „zgłoszenie celne” — cron: wykryj kontenery zbyt długo w etapie zgłoszenie celne → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „odprawa celna w toku” — cron: wykryj kontenery zbyt długo w etapie odprawa celna w toku → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „zwolnienie celne” — cron: wykryj kontenery zbyt długo w etapie zwolnienie celne → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „awizacja dostawy” — cron: wykryj kontenery zbyt długo w etapie awizacja dostawy → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „transport z portu do magazynu” — cron: wykryj kontenery zbyt długo w etapie transport z portu do magazynu → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „zgłoszenie na bramie magazynu” — cron: wykryj kontenery zbyt długo w etapie zgłoszenie na bramie magazynu → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „rozładunek kontenera” — cron: wykryj kontenery zbyt długo w etapie rozładunek kontenera → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „kontrola jakości towaru” — cron: wykryj kontenery zbyt długo w etapie kontrola jakości towaru → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „przyjęcie na stan” — cron: wykryj kontenery zbyt długo w etapie przyjęcie na stan → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „zwrot pustego kontenera” — cron: wykryj kontenery zbyt długo w etapie zwrot pustego kontenera → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „rozliczenie kosztów kontenera” — cron: wykryj kontenery zbyt długo w etapie rozliczenie kosztów kontenera → alert.
- 🔲 **[Python]** Pętla nadzoru etapu „zamknięcie sprawy kontenera” — cron: wykryj kontenery zbyt długo w etapie zamknięcie sprawy kontenera → alert.

### 9.2 Digesty per rola
- 🔲 **[Python]** Digest poranny dla zakupowca — cron 6:00: spersonalizowane podsumowanie zadań dla zakupowca.
- 🔲 **[Python]** Digest poranny dla spedytora — cron 6:00: spersonalizowane podsumowanie zadań dla spedytora.
- 🔲 **[Python]** Digest poranny dla magazyniera — cron 6:00: spersonalizowane podsumowanie zadań dla magazyniera.
- 🔲 **[Python]** Digest poranny dla agencji celnej — cron 6:00: spersonalizowane podsumowanie zadań dla agencji celnej.
- 🔲 **[Python]** Digest poranny dla kierownika — cron 6:00: spersonalizowane podsumowanie zadań dla kierownika.
- 🔲 **[Python]** Digest poranny dla klienta — cron 6:00: spersonalizowane podsumowanie zadań dla klienta.
- 🔲 **[Python]** Digest poranny dla administratora — cron 6:00: spersonalizowane podsumowanie zadań dla administratora.

### 9.3 Pętle progowe per KPI
- 🔲 **[Python]** Pętla progowa KPI „terminowość dostaw” — cron: przelicz % kontenerów w oknie, alert przy przekroczeniu normy.
- 🔲 **[Python]** Pętla progowa KPI „średni czas cyklu” — cron: przelicz dni port→magazyn, alert przy przekroczeniu normy.
- 🔲 **[Python]** Pętla progowa KPI „koszt demurrage” — cron: przelicz suma opłat postoju, alert przy przekroczeniu normy.
- 🔲 **[Python]** Pętla progowa KPI „liczba reklamacji” — cron: przelicz szt. i trend, alert przy przekroczeniu normy.
- 🔲 **[Python]** Pętla progowa KPI „dwell time” — cron: przelicz czas przyjęcia, alert przy przekroczeniu normy.
- 🔲 **[Python]** Pętla progowa KPI „koszt transportu” — cron: przelicz koszt/kontener, alert przy przekroczeniu normy.
- 🔲 **[Python]** Pętla progowa KPI „dokładność ETA” — cron: przelicz odchylenie prognozy, alert przy przekroczeniu normy.
- 🔲 **[Python]** Pętla progowa KPI „wolumen” — cron: przelicz liczba kontenerów, alert przy przekroczeniu normy.

### 9.4 Raporty aktywności per rola
- 🔲 **[Python]** Raport aktywności: zakupowca — cron: podsumowanie działań i zaległości zakupowca.
- 🔲 **[Python]** Raport aktywności: spedytora — cron: podsumowanie działań i zaległości spedytora.
- 🔲 **[Python]** Raport aktywności: magazyniera — cron: podsumowanie działań i zaległości magazyniera.
- 🔲 **[Python]** Raport aktywności: agencji celnej — cron: podsumowanie działań i zaległości agencji celnej.
- 🔲 **[Python]** Raport aktywności: kierownika — cron: podsumowanie działań i zaległości kierownika.
- 🔲 **[Python]** Raport aktywności: klienta — cron: podsumowanie działań i zaległości klienta.
- 🔲 **[Python]** Raport aktywności: administratora — cron: podsumowanie działań i zaległości administratora.

### 9.5 Higiena danych i retencja
- 🔲 **[Python]** Retencja logów ClientError — cron: usuwanie logów starszych niż N dni.
- 🔲 **[Python]** Retencja pozycji AuditLog — archiwizacja wpisów audytu wg polityki retencji.
- 🔲 **[Python]** Kompresja starych zdjęć rozładunku — downscale UnloadPhoto po X dniach dla oszczędności miejsca.
- 🔲 **[Feature]** Eksport pełnego audytu kontenera do PDF — jeden przycisk: cała historia + dokumenty kontenera.
- 🔲 **[Python]** Backup przyrostowy bazy — nocny dump różnicowy + weryfikacja integralności.

## 10. PER NARZĘDZIE (wzorce)









### 10.1 Python / FastAPI
- ✅ **[Python]** Izolacja per-zasób w deps.py (`_enforce_scope`/`get_scoped`) — wzorzec bezpieczeństwa.
- ✅ **[Python]** check_container_access — cut-vertex kontroli dostępu.
- ✅ **[Python]** Middleware RequestID/CSP — bezpieczeństwo requestów.
- ✅ **[Python]** Strażnik łańcucha migracji (test_migration_chain) — jedna głowa alembica.
- 🔲 **[Python]** Wspólny helper eksportu do Excel (openpyxl) dla wszystkich list.
- 🔲 **[Python]** Dekorator retry+backoff dla wywołań API zewnętrznych.
- 🔲 **[Python]** Cache TTL dla stawek celnych/kursów (lru_cache+ttl).
- 🔲 **[Python]** Generator PDF z jinja2+weasyprint jako wspólny serwis dokumentów.
- 🔲 **[Python]** Kolejka zadań tła (APScheduler/RQ) zamiast luźnych while-loop.
- 🔲 **[Python]** Idempotencja importów (hash pliku) — brak podwójnego wczytania.

### 10.2 n8n
- 🔲 **[n8n]** Szablon: mail→OCR→podpięcie do kontenera po nr BL.
- 🔲 **[n8n]** Szablon: webhook zdarzenia→wybór kanału (Teams/SMS/mail).
- 🔲 **[n8n]** Szablon: cron→pobór ETA z API→PATCH kontenera.
- 🔲 **[n8n]** Szablon: retry z dead-letter dla nieudanych wywołań.
- 🔲 **[n8n]** Szablon: agregacja alertów w jeden digest o 8:00.

### 10.3 Excel / Power Query
- 🔲 **[Excel]** Raport kolejki samoodświeżający z API TIMPORYE.
- 🔲 **[Excel]** Kalkulator landed cost z tabelą alokacji kosztów.
- 🔲 **[Excel]** Kostka demurrage per port/armator z pivota.
- 🔲 **[Excel]** Cockpit KPI ze sparklinami trendów.
- 🔲 **[Excel]** Aging należności/zobowiązań z warunkowym formatowaniem.

### 10.4 SharePoint / Power Automate
- 🔲 **[SharePoint]** Biblioteka dokumentów kontenera z metadanymi.
- 🔲 **[SharePoint]** Lista awizacji dla partnerów zewnętrznych.
- 🔲 **[Feature]** Flow approval PO/rabatu wg progu kwoty.
- 🔲 **[Feature]** Flow eskalacji reklamacji po przekroczeniu SLA.

### 10.5 Power Query per pole
- 🔲 **[Excel]** Power Query: kolumna „numer kontenera” — pobór i normalizacja pola numer kontenera z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „numer BL” — pobór i normalizacja pola numer BL z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „ETD” — pobór i normalizacja pola ETD z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „ETA” — pobór i normalizacja pola ETA z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „numer PO” — pobór i normalizacja pola numer PO z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „dostawca” — pobór i normalizacja pola dostawca z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „port załadunku” — pobór i normalizacja pola port załadunku z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „port rozładunku” — pobór i normalizacja pola port rozładunku z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „typ kontenera” — pobór i normalizacja pola typ kontenera z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „waga brutto” — pobór i normalizacja pola waga brutto z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „waga netto” — pobór i normalizacja pola waga netto z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „liczba palet” — pobór i normalizacja pola liczba palet z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „liczba kartonów” — pobór i normalizacja pola liczba kartonów z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „kod HS/CN” — pobór i normalizacja pola kod HS/CN z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „wartość CIF” — pobór i normalizacja pola wartość CIF z API TIMPORYE do raportu.
- 🔲 **[Excel]** Power Query: kolumna „waluta” — pobór i normalizacja pola waluta z API TIMPORYE do raportu.

### 10.6 Pivoty Excel per metryka
- 🔲 **[Excel]** Kostka pivot: terminowość dostaw — samoodświeżający pivot % kontenerów w oknie z wymiarami dostawca/port/miesiąc.
- 🔲 **[Excel]** Kostka pivot: średni czas cyklu — samoodświeżający pivot dni port→magazyn z wymiarami dostawca/port/miesiąc.
- 🔲 **[Excel]** Kostka pivot: koszt demurrage — samoodświeżający pivot suma opłat postoju z wymiarami dostawca/port/miesiąc.
- 🔲 **[Excel]** Kostka pivot: liczba reklamacji — samoodświeżający pivot szt. i trend z wymiarami dostawca/port/miesiąc.
- 🔲 **[Excel]** Kostka pivot: dwell time — samoodświeżający pivot czas przyjęcia z wymiarami dostawca/port/miesiąc.
- 🔲 **[Excel]** Kostka pivot: koszt transportu — samoodświeżający pivot koszt/kontener z wymiarami dostawca/port/miesiąc.
- 🔲 **[Excel]** Kostka pivot: dokładność ETA — samoodświeżający pivot odchylenie prognozy z wymiarami dostawca/port/miesiąc.
- 🔲 **[Excel]** Kostka pivot: wolumen — samoodświeżający pivot liczba kontenerów z wymiarami dostawca/port/miesiąc.

### 10.7 Widoki SharePoint per wymiar
- 🔲 **[SharePoint]** Lista SharePoint per dostawcy — widok danych operacyjnych filtrowany po dostawcy dla partnerów.
- 🔲 **[SharePoint]** Lista SharePoint per spedytora — widok danych operacyjnych filtrowany po spedytora dla partnerów.
- 🔲 **[SharePoint]** Lista SharePoint per przewoźnika — widok danych operacyjnych filtrowany po przewoźnika dla partnerów.
- 🔲 **[SharePoint]** Lista SharePoint per armatora — widok danych operacyjnych filtrowany po armatora dla partnerów.
- 🔲 **[SharePoint]** Lista SharePoint per portu — widok danych operacyjnych filtrowany po portu dla partnerów.
- 🔲 **[SharePoint]** Lista SharePoint per magazynu — widok danych operacyjnych filtrowany po magazynu dla partnerów.
- 🔲 **[SharePoint]** Lista SharePoint per klienta — widok danych operacyjnych filtrowany po klienta dla partnerów.
- 🔲 **[SharePoint]** Lista SharePoint per materiału — widok danych operacyjnych filtrowany po materiału dla partnerów.
- 🔲 **[SharePoint]** Lista SharePoint per kraju — widok danych operacyjnych filtrowany po kraju dla partnerów.
- 🔲 **[SharePoint]** Lista SharePoint per trasy — widok danych operacyjnych filtrowany po trasy dla partnerów.
- 🔲 **[SharePoint]** Lista SharePoint per typu kontenera — widok danych operacyjnych filtrowany po typu kontenera dla partnerów.
- 🔲 **[SharePoint]** Lista SharePoint per agencji celnej — widok danych operacyjnych filtrowany po agencji celnej dla partnerów.

### 10.8 Monitoring kanałów powiadomień
- 🔲 **[Python]** Test dostarczalności kanału mail — monitor doręczeń i błędów wysyłki mailem.
- 🔲 **[Python]** Test dostarczalności kanału Teams — monitor doręczeń i błędów wysyłki kartą w Teams.
- 🔲 **[Python]** Test dostarczalności kanału SMS — monitor doręczeń i błędów wysyłki SMS-em.
- 🔲 **[Python]** Test dostarczalności kanału dashboard — monitor doręczeń i błędów wysyłki na dashboardzie.
- 🔲 **[Python]** Test dostarczalności kanału push — monitor doręczeń i błędów wysyłki powiadomieniem push.

## 11. FEATURE'Y PRODUKTOWE









### 11.1 UX / UI
- ✅ **[Feature]** Reskin konsola operacyjna (stal+bursztyn) — spójny design system.
- ✅ **[Feature]** Reskin hybryda A+E — gęstość + dane wg makiety.
- ✅ **[Feature]** Design system wg makiet Claude Design (Pulpit/Agencja/Kalendarz).
- ✅ **[Feature]** Landing page (LandingPage) — strona wejściowa.
- ✅ **[Feature]** Profil użytkownika (ProfilePage).
- ✅ **[Feature]** Panel admina (AdminPage, admin router).
- ✅ **[Feature]** Baza wiedzy/szkolenia (WiedzaPage, knowledge, TrainingTopic/Vote, KnowledgeBulletin/Ack).
- 🔲 **[Feature]** Zapisane filtry i widoki per użytkownik na wszystkich listach.
- 🔲 **[Feature]** Globalne wyszukiwanie (kontener/klient/BL/PO) z klawiaturą.
- 🔲 **[Feature]** Tryb ciemny/jasny z zapisem preferencji.
- 🔲 **[Feature]** Skróty klawiszowe dla operacji kolejki.
- 🔲 **[Feature]** Onboarding/tour dla nowych użytkowników.
- 🔲 **[Feature]** Bulk-akcje z zaznaczeniem wielu wierszy w każdej tabeli.

### 11.2 Role i bezpieczeństwo
- ✅ **[Feature]** Role + izolacja per klient/zasób (deps.py, check_container_access).
- ✅ **[Feature]** Auth + refresh token (auth, RefreshToken, PasswordResetToken, AuthPages/LoginPage).
- ✅ **[Feature]** Blokada IP + rejestr błędów klienta (BlockedIP, ClientError).
- ✅ **[Feature]** Audyt zmian (AuditLog) — kto/kiedy/co.
- ✅ **[Feature]** /health + smoke po deployu.
- ✅ **[Feature]** Weryfikacja backupu (verify_backup_loop).
- 🔲 **[Feature]** 2FA/TOTP dla ról administracyjnych.
- 🔲 **[Feature]** Sesyjny log dostępu do dokumentów (kto pobrał).
- 🔲 **[Feature]** Rotacja i wygaszanie linków share z datą ważności.
- 🔲 **[Feature]** Rate-limit na endpointach publicznych (portal/share/driver).

### 11.3 Mobile / skaner / hala
- ✅ **[Feature]** Widok TV kolejki (QueueTvPage) — hala.
- ✅ **[Feature]** Karta rozładunku mobilna (KartaRozladunku) + zdjęcia (UnloadPhoto).
- 🔲 **[Feature]** PWA offline dla karty rozładunku (słabe wifi w hali).
- 🔲 **[Feature]** Tryb skanera na bramie — szybkie skanowanie kontenerów.
- 🔲 **[Feature]** Powiadomienia push na urządzenie magazyniera.

### 11.4 Wydajność / jakość / testy
- ✅ **[Feature]** Testy DOM ekranów (Avizo/Gate/Dlt/Orders/Quotes/Complaints/KartaRozladunku).
- ✅ **[Feature]** E2E Playwright (TS, workers:1) — smoke krytycznych flow.
- ✅ **[Feature]** Strażnik migracji + serializacja merge queue (automerge).
- ✅ **[Feature]** Auto-deploy Coolify (deploy.yml) + smoke.
- 🔲 **[Python]** Wykrywanie i naprawa N+1 w listach kontenerów (eager loading).
- 🔲 **[Feature]** Paginacja + wirtualizacja długich list kolejki.
- 🔲 **[Feature]** Indeksy DB pod najczęstsze filtry (status, klient, ETA).
- 🔲 **[Feature]** Monitoring czasu odpowiedzi endpointów + alert regresji.
- 🔲 **[Python]** Kontrola pokrycia testami krytycznych ścieżek (check_container_access).

---

### 11.5 Widoki i uprawnienia per rola
- 🔲 **[Feature]** Pulpit per rola: zakupowca — dedykowany zestaw kafelków i skrótów dla zakupowca.
- 🔲 **[Feature]** Uprawnienia szczegółowe dla zakupowca — granularny zakres widoczności pól i akcji dla zakupowca.
- 🔲 **[Feature]** Pulpit per rola: spedytora — dedykowany zestaw kafelków i skrótów dla spedytora.
- 🔲 **[Feature]** Uprawnienia szczegółowe dla spedytora — granularny zakres widoczności pól i akcji dla spedytora.
- 🔲 **[Feature]** Pulpit per rola: magazyniera — dedykowany zestaw kafelków i skrótów dla magazyniera.
- 🔲 **[Feature]** Uprawnienia szczegółowe dla magazyniera — granularny zakres widoczności pól i akcji dla magazyniera.
- 🔲 **[Feature]** Pulpit per rola: agencji celnej — dedykowany zestaw kafelków i skrótów dla agencji celnej.
- 🔲 **[Feature]** Uprawnienia szczegółowe dla agencji celnej — granularny zakres widoczności pól i akcji dla agencji celnej.
- 🔲 **[Feature]** Pulpit per rola: kierownika — dedykowany zestaw kafelków i skrótów dla kierownika.
- 🔲 **[Feature]** Uprawnienia szczegółowe dla kierownika — granularny zakres widoczności pól i akcji dla kierownika.
- 🔲 **[Feature]** Pulpit per rola: klienta — dedykowany zestaw kafelków i skrótów dla klienta.
- 🔲 **[Feature]** Uprawnienia szczegółowe dla klienta — granularny zakres widoczności pól i akcji dla klienta.
- 🔲 **[Feature]** Pulpit per rola: administratora — dedykowany zestaw kafelków i skrótów dla administratora.
- 🔲 **[Feature]** Uprawnienia szczegółowe dla administratora — granularny zakres widoczności pól i akcji dla administratora.

### 11.6 i18n
- 🔲 **[Feature]** i18n interfejsu: polski — tłumaczenie UI i powiadomień na polski.
- 🔲 **[Feature]** i18n interfejsu: angielski — tłumaczenie UI i powiadomień na angielski.
- 🔲 **[Feature]** i18n interfejsu: niemiecki — tłumaczenie UI i powiadomień na niemiecki.
- 🔲 **[Feature]** i18n interfejsu: chiński — tłumaczenie UI i powiadomień na chiński.
- 🔲 **[Feature]** i18n interfejsu: hiszpański — tłumaczenie UI i powiadomień na hiszpański.

### 11.7 UX per ekran
- 🔲 **[Feature]** Zapisane filtry na ekranie kolejka — dołóż „zapisane filtry” do widoku kolejka.
- 🔲 **[Feature]** Zapisane filtry na ekranie tracking — dołóż „zapisane filtry” do widoku tracking.
- 🔲 **[Feature]** Zapisane filtry na ekranie spedycja — dołóż „zapisane filtry” do widoku spedycja.
- 🔲 **[Feature]** Zapisane filtry na ekranie magazyn — dołóż „zapisane filtry” do widoku magazyn.
- 🔲 **[Feature]** Zapisane filtry na ekranie faktury — dołóż „zapisane filtry” do widoku faktury.
- 🔲 **[Feature]** Zapisane filtry na ekranie celne — dołóż „zapisane filtry” do widoku celne.
- 🔲 **[Feature]** Eksport do csv na ekranie kolejka — dołóż „eksport do CSV” do widoku kolejka.
- 🔲 **[Feature]** Eksport do csv na ekranie tracking — dołóż „eksport do CSV” do widoku tracking.
- 🔲 **[Feature]** Eksport do csv na ekranie spedycja — dołóż „eksport do CSV” do widoku spedycja.
- 🔲 **[Feature]** Eksport do csv na ekranie magazyn — dołóż „eksport do CSV” do widoku magazyn.
- 🔲 **[Feature]** Eksport do csv na ekranie faktury — dołóż „eksport do CSV” do widoku faktury.
- 🔲 **[Feature]** Eksport do csv na ekranie celne — dołóż „eksport do CSV” do widoku celne.
- 🔲 **[Feature]** Eksport do excel na ekranie kolejka — dołóż „eksport do Excel” do widoku kolejka.
- 🔲 **[Feature]** Eksport do excel na ekranie tracking — dołóż „eksport do Excel” do widoku tracking.
- 🔲 **[Feature]** Eksport do excel na ekranie spedycja — dołóż „eksport do Excel” do widoku spedycja.
- 🔲 **[Feature]** Eksport do excel na ekranie magazyn — dołóż „eksport do Excel” do widoku magazyn.
- 🔲 **[Feature]** Eksport do excel na ekranie faktury — dołóż „eksport do Excel” do widoku faktury.
- 🔲 **[Feature]** Eksport do excel na ekranie celne — dołóż „eksport do Excel” do widoku celne.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie kolejka — dołóż „konfigurowalne kolumny” do widoku kolejka.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie tracking — dołóż „konfigurowalne kolumny” do widoku tracking.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie spedycja — dołóż „konfigurowalne kolumny” do widoku spedycja.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie magazyn — dołóż „konfigurowalne kolumny” do widoku magazyn.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie faktury — dołóż „konfigurowalne kolumny” do widoku faktury.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie celne — dołóż „konfigurowalne kolumny” do widoku celne.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie kolejka — dołóż „sortowanie wielopoziomowe” do widoku kolejka.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie tracking — dołóż „sortowanie wielopoziomowe” do widoku tracking.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie spedycja — dołóż „sortowanie wielopoziomowe” do widoku spedycja.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie magazyn — dołóż „sortowanie wielopoziomowe” do widoku magazyn.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie faktury — dołóż „sortowanie wielopoziomowe” do widoku faktury.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie celne — dołóż „sortowanie wielopoziomowe” do widoku celne.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie kolejka — dołóż „zaznaczanie wielu wierszy” do widoku kolejka.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie tracking — dołóż „zaznaczanie wielu wierszy” do widoku tracking.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie spedycja — dołóż „zaznaczanie wielu wierszy” do widoku spedycja.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie magazyn — dołóż „zaznaczanie wielu wierszy” do widoku magazyn.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie faktury — dołóż „zaznaczanie wielu wierszy” do widoku faktury.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie celne — dołóż „zaznaczanie wielu wierszy” do widoku celne.
- 🔲 **[Feature]** Bulk-akcje na ekranie kolejka — dołóż „bulk-akcje” do widoku kolejka.
- 🔲 **[Feature]** Bulk-akcje na ekranie tracking — dołóż „bulk-akcje” do widoku tracking.
- 🔲 **[Feature]** Bulk-akcje na ekranie spedycja — dołóż „bulk-akcje” do widoku spedycja.
- 🔲 **[Feature]** Bulk-akcje na ekranie magazyn — dołóż „bulk-akcje” do widoku magazyn.
- 🔲 **[Feature]** Bulk-akcje na ekranie faktury — dołóż „bulk-akcje” do widoku faktury.
- 🔲 **[Feature]** Bulk-akcje na ekranie celne — dołóż „bulk-akcje” do widoku celne.
- 🔲 **[Feature]** Szybki podgląd na ekranie kolejka — dołóż „szybki podgląd” do widoku kolejka.
- 🔲 **[Feature]** Szybki podgląd na ekranie tracking — dołóż „szybki podgląd” do widoku tracking.
- 🔲 **[Feature]** Szybki podgląd na ekranie spedycja — dołóż „szybki podgląd” do widoku spedycja.
- 🔲 **[Feature]** Szybki podgląd na ekranie magazyn — dołóż „szybki podgląd” do widoku magazyn.
- 🔲 **[Feature]** Szybki podgląd na ekranie faktury — dołóż „szybki podgląd” do widoku faktury.
- 🔲 **[Feature]** Szybki podgląd na ekranie celne — dołóż „szybki podgląd” do widoku celne.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie kolejka — dołóż „kopiowanie linku do rekordu” do widoku kolejka.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie tracking — dołóż „kopiowanie linku do rekordu” do widoku tracking.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie spedycja — dołóż „kopiowanie linku do rekordu” do widoku spedycja.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie magazyn — dołóż „kopiowanie linku do rekordu” do widoku magazyn.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie faktury — dołóż „kopiowanie linku do rekordu” do widoku faktury.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie celne — dołóż „kopiowanie linku do rekordu” do widoku celne.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie kolejka — dołóż „historia zmian rekordu” do widoku kolejka.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie tracking — dołóż „historia zmian rekordu” do widoku tracking.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie spedycja — dołóż „historia zmian rekordu” do widoku spedycja.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie magazyn — dołóż „historia zmian rekordu” do widoku magazyn.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie faktury — dołóż „historia zmian rekordu” do widoku faktury.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie celne — dołóż „historia zmian rekordu” do widoku celne.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie kolejka — dołóż „komentarze do rekordu” do widoku kolejka.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie tracking — dołóż „komentarze do rekordu” do widoku tracking.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie spedycja — dołóż „komentarze do rekordu” do widoku spedycja.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie magazyn — dołóż „komentarze do rekordu” do widoku magazyn.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie faktury — dołóż „komentarze do rekordu” do widoku faktury.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie celne — dołóż „komentarze do rekordu” do widoku celne.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie kolejka — dołóż „załączniki do rekordu” do widoku kolejka.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie tracking — dołóż „załączniki do rekordu” do widoku tracking.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie spedycja — dołóż „załączniki do rekordu” do widoku spedycja.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie magazyn — dołóż „załączniki do rekordu” do widoku magazyn.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie faktury — dołóż „załączniki do rekordu” do widoku faktury.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie celne — dołóż „załączniki do rekordu” do widoku celne.
- 🔲 **[Feature]** Tagi/etykiety na ekranie kolejka — dołóż „tagi/etykiety” do widoku kolejka.
- 🔲 **[Feature]** Tagi/etykiety na ekranie tracking — dołóż „tagi/etykiety” do widoku tracking.
- 🔲 **[Feature]** Tagi/etykiety na ekranie spedycja — dołóż „tagi/etykiety” do widoku spedycja.
- 🔲 **[Feature]** Tagi/etykiety na ekranie magazyn — dołóż „tagi/etykiety” do widoku magazyn.
- 🔲 **[Feature]** Tagi/etykiety na ekranie faktury — dołóż „tagi/etykiety” do widoku faktury.
- 🔲 **[Feature]** Tagi/etykiety na ekranie celne — dołóż „tagi/etykiety” do widoku celne.
- 🔲 **[Feature]** Ulubione na ekranie kolejka — dołóż „ulubione” do widoku kolejka.
- 🔲 **[Feature]** Ulubione na ekranie tracking — dołóż „ulubione” do widoku tracking.
- 🔲 **[Feature]** Ulubione na ekranie spedycja — dołóż „ulubione” do widoku spedycja.
- 🔲 **[Feature]** Ulubione na ekranie magazyn — dołóż „ulubione” do widoku magazyn.
- 🔲 **[Feature]** Ulubione na ekranie faktury — dołóż „ulubione” do widoku faktury.
- 🔲 **[Feature]** Ulubione na ekranie celne — dołóż „ulubione” do widoku celne.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie kolejka — dołóż „ostatnio oglądane” do widoku kolejka.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie tracking — dołóż „ostatnio oglądane” do widoku tracking.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie spedycja — dołóż „ostatnio oglądane” do widoku spedycja.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie magazyn — dołóż „ostatnio oglądane” do widoku magazyn.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie faktury — dołóż „ostatnio oglądane” do widoku faktury.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie celne — dołóż „ostatnio oglądane” do widoku celne.

---

### 11.8 UX per ekran (rozszerzenie)
- 🔲 **[Feature]** Zapisane filtry na ekranie awizacja — dołóż „zapisane filtry” do widoku awizacja.
- 🔲 **[Feature]** Zapisane filtry na ekranie wywołania palet — dołóż „zapisane filtry” do widoku wywołania palet.
- 🔲 **[Feature]** Zapisane filtry na ekranie DLT — dołóż „zapisane filtry” do widoku DLT.
- 🔲 **[Feature]** Zapisane filtry na ekranie portal klienta — dołóż „zapisane filtry” do widoku portal klienta.
- 🔲 **[Feature]** Zapisane filtry na ekranie reklamacje — dołóż „zapisane filtry” do widoku reklamacje.
- 🔲 **[Feature]** Zapisane filtry na ekranie analityka — dołóż „zapisane filtry” do widoku analityka.
- 🔲 **[Feature]** Zapisane filtry na ekranie kalendarz kolejki — dołóż „zapisane filtry” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Zapisane filtry na ekranie brama — dołóż „zapisane filtry” do widoku brama.
- 🔲 **[Feature]** Eksport do csv na ekranie awizacja — dołóż „eksport do CSV” do widoku awizacja.
- 🔲 **[Feature]** Eksport do csv na ekranie wywołania palet — dołóż „eksport do CSV” do widoku wywołania palet.
- 🔲 **[Feature]** Eksport do csv na ekranie DLT — dołóż „eksport do CSV” do widoku DLT.
- 🔲 **[Feature]** Eksport do csv na ekranie portal klienta — dołóż „eksport do CSV” do widoku portal klienta.
- 🔲 **[Feature]** Eksport do csv na ekranie reklamacje — dołóż „eksport do CSV” do widoku reklamacje.
- 🔲 **[Feature]** Eksport do csv na ekranie analityka — dołóż „eksport do CSV” do widoku analityka.
- 🔲 **[Feature]** Eksport do csv na ekranie kalendarz kolejki — dołóż „eksport do CSV” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Eksport do csv na ekranie brama — dołóż „eksport do CSV” do widoku brama.
- 🔲 **[Feature]** Eksport do excel na ekranie awizacja — dołóż „eksport do Excel” do widoku awizacja.
- 🔲 **[Feature]** Eksport do excel na ekranie wywołania palet — dołóż „eksport do Excel” do widoku wywołania palet.
- 🔲 **[Feature]** Eksport do excel na ekranie DLT — dołóż „eksport do Excel” do widoku DLT.
- 🔲 **[Feature]** Eksport do excel na ekranie portal klienta — dołóż „eksport do Excel” do widoku portal klienta.
- 🔲 **[Feature]** Eksport do excel na ekranie reklamacje — dołóż „eksport do Excel” do widoku reklamacje.
- 🔲 **[Feature]** Eksport do excel na ekranie analityka — dołóż „eksport do Excel” do widoku analityka.
- 🔲 **[Feature]** Eksport do excel na ekranie kalendarz kolejki — dołóż „eksport do Excel” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Eksport do excel na ekranie brama — dołóż „eksport do Excel” do widoku brama.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie awizacja — dołóż „konfigurowalne kolumny” do widoku awizacja.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie wywołania palet — dołóż „konfigurowalne kolumny” do widoku wywołania palet.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie DLT — dołóż „konfigurowalne kolumny” do widoku DLT.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie portal klienta — dołóż „konfigurowalne kolumny” do widoku portal klienta.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie reklamacje — dołóż „konfigurowalne kolumny” do widoku reklamacje.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie analityka — dołóż „konfigurowalne kolumny” do widoku analityka.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie kalendarz kolejki — dołóż „konfigurowalne kolumny” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Konfigurowalne kolumny na ekranie brama — dołóż „konfigurowalne kolumny” do widoku brama.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie awizacja — dołóż „sortowanie wielopoziomowe” do widoku awizacja.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie wywołania palet — dołóż „sortowanie wielopoziomowe” do widoku wywołania palet.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie DLT — dołóż „sortowanie wielopoziomowe” do widoku DLT.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie portal klienta — dołóż „sortowanie wielopoziomowe” do widoku portal klienta.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie reklamacje — dołóż „sortowanie wielopoziomowe” do widoku reklamacje.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie analityka — dołóż „sortowanie wielopoziomowe” do widoku analityka.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie kalendarz kolejki — dołóż „sortowanie wielopoziomowe” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Sortowanie wielopoziomowe na ekranie brama — dołóż „sortowanie wielopoziomowe” do widoku brama.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie awizacja — dołóż „zaznaczanie wielu wierszy” do widoku awizacja.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie wywołania palet — dołóż „zaznaczanie wielu wierszy” do widoku wywołania palet.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie DLT — dołóż „zaznaczanie wielu wierszy” do widoku DLT.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie portal klienta — dołóż „zaznaczanie wielu wierszy” do widoku portal klienta.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie reklamacje — dołóż „zaznaczanie wielu wierszy” do widoku reklamacje.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie analityka — dołóż „zaznaczanie wielu wierszy” do widoku analityka.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie kalendarz kolejki — dołóż „zaznaczanie wielu wierszy” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Zaznaczanie wielu wierszy na ekranie brama — dołóż „zaznaczanie wielu wierszy” do widoku brama.
- 🔲 **[Feature]** Bulk-akcje na ekranie awizacja — dołóż „bulk-akcje” do widoku awizacja.
- 🔲 **[Feature]** Bulk-akcje na ekranie wywołania palet — dołóż „bulk-akcje” do widoku wywołania palet.
- 🔲 **[Feature]** Bulk-akcje na ekranie DLT — dołóż „bulk-akcje” do widoku DLT.
- 🔲 **[Feature]** Bulk-akcje na ekranie portal klienta — dołóż „bulk-akcje” do widoku portal klienta.
- 🔲 **[Feature]** Bulk-akcje na ekranie reklamacje — dołóż „bulk-akcje” do widoku reklamacje.
- 🔲 **[Feature]** Bulk-akcje na ekranie analityka — dołóż „bulk-akcje” do widoku analityka.
- 🔲 **[Feature]** Bulk-akcje na ekranie kalendarz kolejki — dołóż „bulk-akcje” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Bulk-akcje na ekranie brama — dołóż „bulk-akcje” do widoku brama.
- 🔲 **[Feature]** Szybki podgląd na ekranie awizacja — dołóż „szybki podgląd” do widoku awizacja.
- 🔲 **[Feature]** Szybki podgląd na ekranie wywołania palet — dołóż „szybki podgląd” do widoku wywołania palet.
- 🔲 **[Feature]** Szybki podgląd na ekranie DLT — dołóż „szybki podgląd” do widoku DLT.
- 🔲 **[Feature]** Szybki podgląd na ekranie portal klienta — dołóż „szybki podgląd” do widoku portal klienta.
- 🔲 **[Feature]** Szybki podgląd na ekranie reklamacje — dołóż „szybki podgląd” do widoku reklamacje.
- 🔲 **[Feature]** Szybki podgląd na ekranie analityka — dołóż „szybki podgląd” do widoku analityka.
- 🔲 **[Feature]** Szybki podgląd na ekranie kalendarz kolejki — dołóż „szybki podgląd” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Szybki podgląd na ekranie brama — dołóż „szybki podgląd” do widoku brama.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie awizacja — dołóż „kopiowanie linku do rekordu” do widoku awizacja.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie wywołania palet — dołóż „kopiowanie linku do rekordu” do widoku wywołania palet.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie DLT — dołóż „kopiowanie linku do rekordu” do widoku DLT.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie portal klienta — dołóż „kopiowanie linku do rekordu” do widoku portal klienta.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie reklamacje — dołóż „kopiowanie linku do rekordu” do widoku reklamacje.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie analityka — dołóż „kopiowanie linku do rekordu” do widoku analityka.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie kalendarz kolejki — dołóż „kopiowanie linku do rekordu” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Kopiowanie linku do rekordu na ekranie brama — dołóż „kopiowanie linku do rekordu” do widoku brama.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie awizacja — dołóż „historia zmian rekordu” do widoku awizacja.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie wywołania palet — dołóż „historia zmian rekordu” do widoku wywołania palet.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie DLT — dołóż „historia zmian rekordu” do widoku DLT.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie portal klienta — dołóż „historia zmian rekordu” do widoku portal klienta.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie reklamacje — dołóż „historia zmian rekordu” do widoku reklamacje.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie analityka — dołóż „historia zmian rekordu” do widoku analityka.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie kalendarz kolejki — dołóż „historia zmian rekordu” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Historia zmian rekordu na ekranie brama — dołóż „historia zmian rekordu” do widoku brama.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie awizacja — dołóż „komentarze do rekordu” do widoku awizacja.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie wywołania palet — dołóż „komentarze do rekordu” do widoku wywołania palet.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie DLT — dołóż „komentarze do rekordu” do widoku DLT.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie portal klienta — dołóż „komentarze do rekordu” do widoku portal klienta.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie reklamacje — dołóż „komentarze do rekordu” do widoku reklamacje.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie analityka — dołóż „komentarze do rekordu” do widoku analityka.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie kalendarz kolejki — dołóż „komentarze do rekordu” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Komentarze do rekordu na ekranie brama — dołóż „komentarze do rekordu” do widoku brama.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie awizacja — dołóż „załączniki do rekordu” do widoku awizacja.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie wywołania palet — dołóż „załączniki do rekordu” do widoku wywołania palet.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie DLT — dołóż „załączniki do rekordu” do widoku DLT.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie portal klienta — dołóż „załączniki do rekordu” do widoku portal klienta.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie reklamacje — dołóż „załączniki do rekordu” do widoku reklamacje.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie analityka — dołóż „załączniki do rekordu” do widoku analityka.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie kalendarz kolejki — dołóż „załączniki do rekordu” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Załączniki do rekordu na ekranie brama — dołóż „załączniki do rekordu” do widoku brama.
- 🔲 **[Feature]** Tagi/etykiety na ekranie awizacja — dołóż „tagi/etykiety” do widoku awizacja.
- 🔲 **[Feature]** Tagi/etykiety na ekranie wywołania palet — dołóż „tagi/etykiety” do widoku wywołania palet.
- 🔲 **[Feature]** Tagi/etykiety na ekranie DLT — dołóż „tagi/etykiety” do widoku DLT.
- 🔲 **[Feature]** Tagi/etykiety na ekranie portal klienta — dołóż „tagi/etykiety” do widoku portal klienta.
- 🔲 **[Feature]** Tagi/etykiety na ekranie reklamacje — dołóż „tagi/etykiety” do widoku reklamacje.
- 🔲 **[Feature]** Tagi/etykiety na ekranie analityka — dołóż „tagi/etykiety” do widoku analityka.
- 🔲 **[Feature]** Tagi/etykiety na ekranie kalendarz kolejki — dołóż „tagi/etykiety” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Tagi/etykiety na ekranie brama — dołóż „tagi/etykiety” do widoku brama.
- 🔲 **[Feature]** Ulubione na ekranie awizacja — dołóż „ulubione” do widoku awizacja.
- 🔲 **[Feature]** Ulubione na ekranie wywołania palet — dołóż „ulubione” do widoku wywołania palet.
- 🔲 **[Feature]** Ulubione na ekranie DLT — dołóż „ulubione” do widoku DLT.
- 🔲 **[Feature]** Ulubione na ekranie portal klienta — dołóż „ulubione” do widoku portal klienta.
- 🔲 **[Feature]** Ulubione na ekranie reklamacje — dołóż „ulubione” do widoku reklamacje.
- 🔲 **[Feature]** Ulubione na ekranie analityka — dołóż „ulubione” do widoku analityka.
- 🔲 **[Feature]** Ulubione na ekranie kalendarz kolejki — dołóż „ulubione” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Ulubione na ekranie brama — dołóż „ulubione” do widoku brama.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie awizacja — dołóż „ostatnio oglądane” do widoku awizacja.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie wywołania palet — dołóż „ostatnio oglądane” do widoku wywołania palet.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie DLT — dołóż „ostatnio oglądane” do widoku DLT.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie portal klienta — dołóż „ostatnio oglądane” do widoku portal klienta.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie reklamacje — dołóż „ostatnio oglądane” do widoku reklamacje.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie analityka — dołóż „ostatnio oglądane” do widoku analityka.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie kalendarz kolejki — dołóż „ostatnio oglądane” do widoku kalendarz kolejki.
- 🔲 **[Feature]** Ostatnio oglądane na ekranie brama — dołóż „ostatnio oglądane” do widoku brama.

---

### 11.9 Dostępność per ekran
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie kolejka — audyt i poprawa dostępności „kontrast WCAG” w widoku kolejka.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie kolejka — audyt i poprawa dostępności „obsługa klawiatury” w widoku kolejka.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie kolejka — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku kolejka.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie kolejka — audyt i poprawa dostępności „widoczny focus” w widoku kolejka.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie tracking — audyt i poprawa dostępności „kontrast WCAG” w widoku tracking.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie tracking — audyt i poprawa dostępności „obsługa klawiatury” w widoku tracking.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie tracking — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku tracking.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie tracking — audyt i poprawa dostępności „widoczny focus” w widoku tracking.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie spedycja — audyt i poprawa dostępności „kontrast WCAG” w widoku spedycja.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie spedycja — audyt i poprawa dostępności „obsługa klawiatury” w widoku spedycja.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie spedycja — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku spedycja.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie spedycja — audyt i poprawa dostępności „widoczny focus” w widoku spedycja.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie magazyn — audyt i poprawa dostępności „kontrast WCAG” w widoku magazyn.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie magazyn — audyt i poprawa dostępności „obsługa klawiatury” w widoku magazyn.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie magazyn — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku magazyn.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie magazyn — audyt i poprawa dostępności „widoczny focus” w widoku magazyn.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie faktury — audyt i poprawa dostępności „kontrast WCAG” w widoku faktury.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie faktury — audyt i poprawa dostępności „obsługa klawiatury” w widoku faktury.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie faktury — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku faktury.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie faktury — audyt i poprawa dostępności „widoczny focus” w widoku faktury.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie celne — audyt i poprawa dostępności „kontrast WCAG” w widoku celne.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie celne — audyt i poprawa dostępności „obsługa klawiatury” w widoku celne.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie celne — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku celne.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie celne — audyt i poprawa dostępności „widoczny focus” w widoku celne.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie awizacja — audyt i poprawa dostępności „kontrast WCAG” w widoku awizacja.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie awizacja — audyt i poprawa dostępności „obsługa klawiatury” w widoku awizacja.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie awizacja — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku awizacja.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie awizacja — audyt i poprawa dostępności „widoczny focus” w widoku awizacja.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie wywołania palet — audyt i poprawa dostępności „kontrast WCAG” w widoku wywołania palet.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie wywołania palet — audyt i poprawa dostępności „obsługa klawiatury” w widoku wywołania palet.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie wywołania palet — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku wywołania palet.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie wywołania palet — audyt i poprawa dostępności „widoczny focus” w widoku wywołania palet.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie DLT — audyt i poprawa dostępności „kontrast WCAG” w widoku DLT.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie DLT — audyt i poprawa dostępności „obsługa klawiatury” w widoku DLT.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie DLT — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku DLT.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie DLT — audyt i poprawa dostępności „widoczny focus” w widoku DLT.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie portal klienta — audyt i poprawa dostępności „kontrast WCAG” w widoku portal klienta.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie portal klienta — audyt i poprawa dostępności „obsługa klawiatury” w widoku portal klienta.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie portal klienta — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku portal klienta.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie portal klienta — audyt i poprawa dostępności „widoczny focus” w widoku portal klienta.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie reklamacje — audyt i poprawa dostępności „kontrast WCAG” w widoku reklamacje.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie reklamacje — audyt i poprawa dostępności „obsługa klawiatury” w widoku reklamacje.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie reklamacje — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku reklamacje.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie reklamacje — audyt i poprawa dostępności „widoczny focus” w widoku reklamacje.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie analityka — audyt i poprawa dostępności „kontrast WCAG” w widoku analityka.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie analityka — audyt i poprawa dostępności „obsługa klawiatury” w widoku analityka.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie analityka — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku analityka.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie analityka — audyt i poprawa dostępności „widoczny focus” w widoku analityka.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie kalendarz kolejki — audyt i poprawa dostępności „kontrast WCAG” w widoku kalendarz kolejki.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie kalendarz kolejki — audyt i poprawa dostępności „obsługa klawiatury” w widoku kalendarz kolejki.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie kalendarz kolejki — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku kalendarz kolejki.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie kalendarz kolejki — audyt i poprawa dostępności „widoczny focus” w widoku kalendarz kolejki.
- 🔲 **[Feature]** A11y „kontrast WCAG” na ekranie brama — audyt i poprawa dostępności „kontrast WCAG” w widoku brama.
- 🔲 **[Feature]** A11y „obsługa klawiatury” na ekranie brama — audyt i poprawa dostępności „obsługa klawiatury” w widoku brama.
- 🔲 **[Feature]** A11y „wsparcie czytnika ekranu” na ekranie brama — audyt i poprawa dostępności „wsparcie czytnika ekranu” w widoku brama.
- 🔲 **[Feature]** A11y „widoczny focus” na ekranie brama — audyt i poprawa dostępności „widoczny focus” w widoku brama.

---

---

## PODSUMOWANIE

- **Łącznie pozycji: 2002** (119 zrobione / 1883 backlog).
- **Zrobione (✅, potwierdzone w repo): 119**.
- **Do zrobienia (🔲 backlog): 1883**.

Rozbicie per sekcja (✅ / 🔲):
1. ZAKUPY — 12 / 268
2. LOGISTYKA / KONTENERY — 33 / 503
3. SPEDYCJA — 8 / 56
4. MAGAZYN — 8 / 110
5. CELNE / DOKUMENTY — 9 / 92
6. SPRZEDAŻ / KLIENCI — 4 / 113
7. ANALITYKA / RAPORTY / KPI — 7 / 189
8. INTEGRACJE — 6 / 130
9. AUTOMATYZACJE TŁA (pętle / cron / digesty) — 9 / 58
10. PER NARZĘDZIE (wzorce) — 4 / 61
11. FEATURE'Y PRODUKTOWE — 19 / 303

> Katalog rozwinięty drobnoziarniście: per-status/per-etap cyklu kontenera, per-pole importu
> (walidacja/mapowanie/transformacja/słownik), per-rola i adresat, per-wymiar (dostawca/
> spedytor/port/klient…), per-kanał (mail/Teams/SMS/dashboard/push), per-metrykę, per-dokument
> i per-segment. Znaczniki ✅ przypięte do realnego stanu repo TIMPORYE; pozycje 🔲 to backlog.

## TOP 30 NASTĘPNYCH KROKÓW (tylko 🔲, największy zwrot / najmniejszy koszt)

1. 🔲 **[Python]** Pętla alertu zmiany ETA (>X dni) — reużywa tracking_loop + notifications.
2. 🔲 **[Python]** Kalkulator demurrage + pętla progu free-time 7/3/1 — bezpośredni koszt firmy.
3. 🔲 **[Python]** Pętla „kontener utknął" (W5) — otwarta decyzja z audytu trackingu.
4. 🔲 **[Feature]** Portal klienta plaster 2 (ContainerTimeline kliencki) — zaplanowane, model gotowy.
5. 🔲 **[Python]** Tracker kompletności dokumentów kontenera (CIPL/BL/CoO/EUR.1/SAD).
6. 🔲 **[Python]** 3-way match faktura↔PO↔przyjęcie — na bazie istniejącego OCR faktur.
7. 🔲 **[Python]** Wspólny helper eksportu do Excel dla wszystkich list.
8. 🔲 **[Teams]** Webhook Teams dla alertów demurrage/opóźnień — jeden connector.
9. 🔲 **[Python]** SLA odpraw + pętla alertu — reużywa customs_delay_loop.
10. 🔲 **[Feature]** Zapisane filtry/widoki per użytkownik na listach.
11. 🔲 **[Feature]** Globalne wyszukiwanie (kontener/BL/PO/klient).
12. 🔲 **[Python]** Alert braku dokumentu blokującego odprawę.
13. 🔲 **[Python]** Idempotencja importów (hash pliku) — mniej błędów operacyjnych.
14. 🔲 **[Feature]** Powiadomienie klienta o zmianie ETA jego kontenera.
15. 🔲 **[Python]** Predykcja realnej ETA z historii opóźnień trasy/portu.
16. 🔲 **[Feature]** Bulk-edycja statusów kontenerów z kolejki.
17. 🔲 **[Python]** Dwell time przyjęć — KPI wąskiego gardła magazynu.
18. 🔲 **[Feature]** Rotacja/wygaszanie linków share z datą ważności — bezpieczeństwo.
19. 🔲 **[Python]** Rekoncyliacja faktury spedytora vs zlecenie/wycena.
20. 🔲 **[Feature]** Eksport dowolnego widoku do Excel/CSV jednym kliknięciem.
21. 🔲 **[Python]** Optymalizator okien rampy (greedy) — mniej kolizji awizacji.
22. 🔲 **[n8n]** Pipeline mail→OCR→podpięcie do kontenera po nr BL.
23. 🔲 **[Python]** Healthcheck integracji (AIS/SAP/Compare) + alert awarii.
24. 🔲 **[Python]** Scoring spedytorów (terminowość/cena/szkody).
25. 🔲 **[Feature]** Paginacja + wirtualizacja długich list kolejki (wydajność).
26. 🔲 **[Python]** Naprawa N+1 w listach kontenerów (eager loading).
27. 🔲 **[Feature]** Preferencje kanału powiadomień per użytkownik.
28. 🔲 **[Python]** Auto-uzupełnienie ATA z zawinięcia AIS.
29. 🔲 **[Feature]** Podpis elektroniczny na karcie rozładunku.
30. 🔲 **[Python]** Digest poranny dla magazynu (co przyjąć dziś) — reużywa daily_digest.

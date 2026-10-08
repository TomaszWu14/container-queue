# Analiza dokumentów transportu FCL → aplikacja TIMPORYE

Data: 2026-09-22 · Autor analizy: sesja Claude Code · Status: referencja do planowania

## 1. Kontekst

Dział transportu przesłał trzy dokumenty opisujące proces importu morskiego (FCL):

1. **Procesowanie transportu FCL – Import** (mapa procesu / swimlane) — **druga połowa** procesu: realizacja transportu, awizacja, odprawa celna, faktury, dostawa na magazyn.
2. **Specyfikacja funkcjonalna dla Wykonawców** (RFP, Acme) — pełne wymagania funkcjonalne i niefunkcjonalne aplikacji do śledzenia importu FCL.
3. **Zlecenie transportu FCL** (mapa procesu / swimlane) — **pierwsza połowa** procesu: zamówienie → CRD → konsolidacja → wybór spedycji → wypełnienie kontenera. Zawiera legendę „krok w Excel vs w aplikacji".

TIMPORYE realizuje dziś głównie **drugą połowę** (kontener → kolejka → tracking → awizacja → odprawa → faktury). **Pierwsza połowa** (koszyk zamówień, CRD, konsolidacja) jest w aplikacji w większości nieobecna.

### Role: proces vs aplikacja

| Rola w procesie | Rola w aplikacji (6) | Uwaga |
|---|---|---|
| Kupiec Operacyjny | `purchasing` | ok |
| Asystent Operacyjny (Acme China + inne kraje) | `logistics` | brak rozróżnienia per-region |
| **Dział Transportu** | — **brak** | luka: zlany z logistics/admin |
| Spedycja | `forwarder` | ok |
| Agencja Celna | `customs` | ok |
| Administrator | `admin` | ok |
| (dostawa na magazyn) | `warehouse` | rola w apce, nie wyróżniona w RFP |

## 2. Mapa proces → aplikacja (pokryte / częściowe / luki)

Zweryfikowane w kodzie (grep): m.in. `CRD` i zapis do SAP mają **zero trafień**.

### ✅ Pokryte
- Zlecenie „1 nr zamówienia = ≥1 kontener" → `PurchaseOrder` (import ETD)
- Wpięcie dokumentów do odprawy + tłumaczenia → załączniki + typy dokumentów + checklista braków (`missing_document_types`)
- Śledzenie transportu → AIS (aisstream) + globus 3D
- Propozycja/akceptacja/odrzucenie harmonogramu (cykl iteracji) → awizacja `/propose` `/accept` `/reject` (`confirm_plan`, audyt)
- Komunikacja w aplikacji bez maila → panel wiadomości
- Przesłanie kompletu dokumentów do agencji celnej → customs `send-docs` (409 przy brakach)
- Alert o zmianie daty dostawy → silnik sygnałów + digest zmian
- Faktura za transport → `FreightInvoice` (BL m:n) + porównanie CIPL (Compare)
- Dashboard wbudowany → Wieża + KPI operacyjne + KPI spedycji
- Harmonogram dzienny + rozwinięcie + podział na magazyn → kolejka (szyna Tydz./Data/Dzień)
- RBAC, audyt, PL/EN (jest też PT), portale zewnętrzne z izolacją danych partnera

### 🟡 Częściowe
- „Rezerwacja frachtu" z **NR DOSTAWY** → jest `TransportOrder`/`TransportJob`, brak osobnego obiektu rezerwacji z nr dostawy
- Awizacja „dzień przed do 14:00" → avizo jest, brak reguły/przypomnienia o deadline 14:00
- Obieg statusów odprawy 5-stopniowy (przygotowane→draft→potwierdzono→odprawiono→**rozliczono**) → statusy celne są, nie 1:1
- Statusy transportu 5-stopniowe → `ContainerStatus` mapuje się inaczej
- Konfigurowalne czasy standardowe (transport/obsługa) przez Admina → dziś stała `PLAN_LEAD_DAYS`
- Prognoza wypełnienia CBM w czasie rzeczywistym → jest wizualizacja 3D, brak prognozy przy dodawaniu zamówień
- KPI jakości dostaw → częściowo `ComplaintsPanel`
- Auto-mail do dostawcy po uzupełnieniu danych → częściowo

### 🔴 Luki (zweryfikowane)
| Luka | Źródło | Waga |
|---|---|---|
| **SAP zapis dwukierunkowy** (data dostawy/statusy) — dziś read-only | RFP §5.8 (must-have) | największa |
| **Moduł CRD + eskalacja** (rejestr, odchylenie od ETD, próg 10 dni, blokada→Kupiec) | RFP §5.2, dok. 3 | duża |
| **Koszyk + auto-konsolidacja ≤70 CBM** (3 typy zlecenia, sortowanie po dostawcy) | RFP §5.1, dok. 3 | duża |
| **Zwolnienie zamówienia przez Kupca** | RFP §5.1, dok. 3 | średnia |
| **Dział Transportu jako osobna rola** | dok. 1/2/3 | średnia |
| **Faktura za odprawę + należności celno-podatkowe** | dok. 1, RFP §5.4 | średnia |
| **Status celny T1** (odprawa poza portem, równoległy) | RFP §5.4/5.5 | średnia |
| KPI: dwell time / detention / storage | RFP §5.9 | średnia |

## 3. Przeoczone luki (poza dokumentami)

Rzeczy, których dokumenty nie mówią wprost, a proces ich wymaga — wyjdą dopiero przy budowie. Każda z rekomendowaną regułą rozstrzygania.

1. **Szew front↔back w modelu danych.** Konsolidacja łączy wiele zamówień w jeden kontener (m:1), a dziś model to `PurchaseOrder` 1→wiele kontenerów (odwrotna relacja). *Rekomendacja:* wprowadzić relację **zamówienie ↔ kontener m:n**; kontener jako „naczynie", zamówienie jako pozycja, która może być nieprzypisana / w koszyku / przypisana.

2. **Konsolidacja to żywy stan, nie akt.** Kontener napełnia się w czasie do 70 CBM z deadline; przy poślizgu CRD zamówienia wchodzą/wychodzą. *Rekomendacja:* stan kontenera-konsolidacji (`otwarty` → `wypełniony` → `zamknięty`) z możliwością re-konsolidacji dopóki nie zamknięty; audyt ruchu zamówień między kontenerami.

3. **CRD per-zamówienie vs ETD per-kontener — konflikt.** W jednym kontenerze wiele CRD. *Rekomendacja (do potwierdzenia przez transport):* CRD kontenera = **najpóźniejsze CRD** jego zamówień; odchylenie >10 dni liczone od tego; blokada dotyczy zamówienia, nie całego kontenera (zamówienie wypada z konsolidacji, kontener jedzie dalej).

4. **Granica człowiek/automat.** „Specjalista rozdziela", „Marcia potwierdza CRD", „decyzja Kupca" — kroki osądu. *Rekomendacja:* automat **proponuje** konsolidację (sortowanie po dostawcy, sumowanie CBM), człowiek **zatwierdza/koryguje**; nie auto-domykać kontenerów.

5. **KPI wymagają capture zdarzeń, nie tylko wykresów.** Dwell time, detention, terminowość podstawień, brak kontaktu ze spedytorem/kierowcą, uszkodzenia/wypadki — brak rejestracji tych zdarzeń w przepływie. *Rekomendacja:* najpierw zaprojektować **rejestrowanie zdarzeń** (timestampy stanów, zgłoszenia szkód/incydentów, próby kontaktu), potem raport. Bez capture KPI z §5.9 są niewykonalne.

6. **Dwukierunkowy SAP = pytanie o źródło prawdy.** Konflikt gdy dane w SAP zmienią się po imporcie. *Rekomendacja:* SAP źródłem prawdy dla zamówień/dostawcy; aplikacja źródłem dla daty dostawy/statusów; **drift-detection** przy re-imporcie + log rozbieżności do ręcznego rozstrzygnięcia (nie ciche nadpisanie).

7. **Dostawca i agent w Azji poza aplikacją (tylko mail).** Pętla potwierdzenia CRD jest „ślepa" — status wraca ręcznie. *Rekomendacja:* rozważyć **publiczny link potwierdzenia dla dostawcy** (wzorzec jak avizo/portal), żeby CRD wracało do aplikacji, a nie mailem.

8. **Blokada zlecenia to stan workflow, nie flaga.** *Rekomendacja:* blokada zatrzymuje downstream, ma właściciela (Kupiec), SLA na odpowiedź, jawne „co odblokowuje"; transport/spedycja widzą, że zamówienie jest wstrzymane (bez szczegółów wewnętrznych).

## 4. Rekomendowana dekompozycja (kolejność)

Fundament to **szew front↔back w modelu danych** — bez niego konsolidacja, CRD/eskalacja i harmonogram nie mają się o co oprzeć, a istniejąca kolejka/tracking się z tym nie zepnie.

1. **Model danych front-half** — relacja zamówienie ↔ kontener m:n, pole CRD per-zamówienie, reguła CRD-w-kontenerze (§3.1–3.3). *Fundament.*
2. **Koszyk + konsolidacja** — UI koszyka, kategoryzacja (konsolidacja/nie), 3 typy zlecenia, sumowanie CBM ≤70, człowiek zatwierdza (§3.4).
3. **CRD + eskalacja** — statusy CRD, odchylenie od ETD, próg 10 dni, blokada→Kupiec, alerty (§3.8).
4. **SAP zapis** — osobna analiza z IT (mechanizm RFC/BAPI/OData, drift, obsługa błędów) (§3.6). Równolegle, bo długi lead-time po stronie IT.
5. **Domknięcia back-half** — rola Dział Transportu, faktura celna + należności, status T1, konfigurowalne czasy standardowe.
6. **KPI** — najpierw capture zdarzeń (§3.5), potem raporty (dwell/detention/storage, jakość dostaw).

## 5. Otwarte decyzje biznesowe (do ustalenia z Działem Transportu)

Nie zgadujemy — te reguły muszą podać ludzie z procesu:

- **Reguła CRD-w-kontenerze:** które CRD rządzi kontenerem przy konsolidacji (rekomendacja: najpóźniejsze) i czy blokada dotyczy zamówienia czy całego kontenera.
- **Granica człowiek/automat:** jak daleko automatyzujemy konsolidację (rekomendacja: automat proponuje, człowiek zatwierdza).
- **Źródło prawdy przy SAP:** które pola aplikacja może nadpisać w SAP, a które są tylko-do-odczytu; jak rozstrzygać drift.
- **Zakres portalu dostawcy:** czy dostawca dostaje link do aplikacji (potwierdzenie CRD), czy zostajemy przy mailu wychodzącym.

## 6. Źródła

- Dok. 1: `PROCESOWANIE_TRANSPORTU_FCL_-_IMPORT` (mapa procesu, back-half)
- Dok. 2: `Specyfikacja_funkcjonalna_dla_Wykonawcow` (RFP)
- Dok. 3: `ZLECENIE_TRANSPORTU_FCL` (mapa procesu, front-half)

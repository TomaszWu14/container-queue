# Wizja: TIMPORYE jako Wieża kontrolna importu grupy

*Data: 2026-09-22 · Typ: dokument wizji (big picture), nie spec implementacyjny*

## Kontekst

TIMPORYE to wewnętrzny system grupy (Borealis, Cobalt Sport, Iberia, Acme)
zastępujący wspólny Excel kolejki kontenerów. Dojrzały (PR-y >#410), FastAPI + React,
multi-spółka/multi-rola, integracje SAP/Power BI/AIS/SafeCube, deploy Coolify/Hetzner.

Kierunek strategiczny (ustalony): **control tower grupy** — pogłębiać jako wewnętrzny
mózg operacji, NIE robić z tego produktu/SaaS na zewnątrz.

## Zdanie przewodnie

**TIMPORYE = Wieża kontrolna importu grupy.** Nie „system do wpisywania kontenerów",
lecz miejsce, które **samo mówi zespołowi co zrobić dziś** — bo widzi wszystko (jedno
źródło prawdy), samo zaciąga dane (automatyzacja) i samo ostrzega zanim zaboli (sygnały).

### Zasada: odwrócenie ciężaru (push zamiast pull)

- **Dziś (pull):** człowiek wchodzi, skanuje kolejkę, sam wyłapuje co się pali, sam
  przepisuje dane między Excelem / SAP / mailem.
- **Wizja (push):** system zaciąga dane sam, liczy ryzyko sam, a człowiekowi podaje
  **jedną listę działań** posortowaną wg pilności × kosztu. Excel/mail znikają nie przez
  zakaz, tylko dlatego, że w apce jest **szybciej i pełniej**.

## Filary i luki

North star = trzy filary (widoczność + automatyzacja + jedno źródło prawdy). Koszty
przychodzą pochodnie (przez wczesne ostrzeżenia). Cztery zidentyfikowane luki dzielą
„dziś" od „wizji":

| Filar | Luka do zasypania |
|---|---|
| **Widzę wszystko** (jedno źródło prawdy) | Kompletność danych + Adopcja |
| **Robi się samo** (automatyzacja) | Automatyzacja przepływów |
| **Ostrzega samo** (sygnały) | Alerty proaktywne |

## Dobry dzień (doświadczenie docelowe)

Sercem jest **jeden ekran startowy „Co dziś"** — nie 12 modułów do obchodzenia, tylko
jedna, posortowana lista działań. Moduły to narzędzia, w które wchodzisz **z tej listy**.

1. **Wieża pokazuje:** *N rzeczy wymaga Ciebie dziś* — sortowane pilność × koszt
   (np. „ETA za 2 dni, brak awizacji", „3 kontenery grożą demurrage ≈€1 200",
   „BL-777 — brak faktury frachtu", „2 kontenery utknęły — brak ruchu 6 dni").
2. **Każda pozycja = akcja jednym kliknięciem** (zaawizuj / dopnij dokument / wyślij do
   spedycji), nie „idź poszukaj".
3. **Dane już tam są** — tracking zaciągnął ETA, importy zaciągnęły zamówienia, faktury BL
   policzyły ryzyko/kontener. Człowiek **potwierdza i decyduje**, nie przepisuje.
4. **Sygnał znajduje człowieka** — pilne trafia też na kanał (mail/n8n/push).
5. **Każdy widzi swoje, aktualne** — spółka, magazyn, spedycja, klient (portal) na tych
   samych danych real-time.

Zmiana mentalna: **moduły to narzędzia, Wieża to dom.** Dziś dom = kolejka (tabela);
w wizji dom = lista działań, a kolejka jest jednym z widoków.

## Persony i widoki (kto co widzi na Wieży)

Zasada: **ta sama Wieża, inny filtr** — nie osobne apki per rola, tylko jedno „Co dziś"
zawężone regułą izolacji, którą system już ma (scope per spółka/`view_all`,
magazyn→`warehouse_id`, spedytor→`forwarder_id`, klient→token portalu).

| Persona | Filtr widoku (co widzi) | „Co dziś" = jej lista działań |
|---|---|---|
| **Logistyka / admin** | Wszystkie spółki (admin) lub swoja + `view_all`; pełny obraz | Ryzyka demurrage (€), utknięcia, braki awizacji/dokumentów, kontenery bez ETA — całość grupy, sort pilność×koszt |
| **Magazyn** | Tylko `warehouse_id` operatora; kontenery kierowane do jego magazynu | Co przyjeżdża dziś/jutro do rozładunku, przekroczone limity awizacji, oczekuje na potwierdzenie rozładunku |
| **Spedycja** | Tylko `forwarder_id`; kontenery/zlecenia jej przypisane | Zlecenia do odpowiedzi (deadline), wyceny/RFQ otwarte, faktury BL bez pliku/kwoty, transporty w realizacji |
| **Zakupy** | Swoja spółka; oś zamówienie↔dostawa | Rozjazd faktura↔zamówienie ponad tolerancję, zamówienia bez potwierdzonej ETA, opóźnione dostawy |
| **Klient (portal)** | Tylko kontenery jego `customer` (token); read-only | Status „moich" kontenerów, ETA, dokumenty oznaczone jako widoczne — **bez listy działań** (klient widzi, nie działa) |

Wyjątek: klient nie ma „Co dziś" z akcjami — portal jest oknem podglądu, nie pulpitem
pracy. Reszta person dostaje tę samą mechanikę listy działań, różni je tylko filtr.

## Cztery zdolności (80% to dopięcie istniejącego)

**A. Silnik sygnałów** — serce „ostrzega samo".
Wspólna warstwa reguł licząca per kontener: pilność, ryzyko demurrage (€), „utknął",
braki dokumentów/awizacji → zasila listę „Co dziś" i alerty.
*Jest:* flaga opóźniony, sygnał „utknął" (W5), demurrage default, powód śledzenia.
*Brak:* wspólny scoring + jedna lista.

**B. Autopilot danych** — serce „robi się samo".
Dane wpadają bez człowieka: tracking→ETA, importy (SAP/PBI/xlsx), faktury→koszty,
statusy; n8n jako reguły „jeśli X to Y".
*Jest:* AIS, SafeCube, importy LFA1/EKKO/MARM/DLT, faktury BL, Compare, plan n8n.
*Brak:* orchestracja + reguły + odblokowanie CI/runnera.

**C. Jedno źródło prawdy z pełnymi danymi.**
Domknięcie dziur: koszty, dokumenty, tracking, powody — wszystko przy kontenerze,
real-time, per rola/spółka.
*Jest:* separacja spółek, audyt pola, timeline, portal klienta.
*Brak:* kompletność (nie wszystko wpada auto) + pełnoprawny widok klienta/spółki.

**D. Wieża jako dom + adopcja.**
Ekran „Co dziś" jako start dla każdej roli; onboarding, by porzucić Excel.
*Jest:* dashboard „Wieża kontrolna" (1a, F1–F3), KPI.
*Brak:* przejście z „dashboard" na „lista działań = punkt startowy", widoki per rola.

## Kolejność (kierunek, nie backlog)

**0. Odblokuj autopilota (warunek brzegowy).** Self-hosted runner + n8n na Hetznerze.
To nie feature — to **zawór**: bez CI zmiany nie jadą, bez n8n filar B stoi.
*(Jest: #406/#407 + runbooki.)*

**1. Silnik sygnałów (A) — najwyższa dźwignia.** Z danych które JUŻ są złóż wspólny
scoring i jedną listę „Co dziś". Realizuje 2 z 3 filarów odczuwalnie (zero niespodzianek
+ dom) bez czekania na nowe integracje. Największy efekt / najmniejszy koszt.

**2. Wieża jako dom (D).** Gdy lista działań istnieje — uczyń ją startem dla każdej roli
(logistyka/magazyn/spedycja/klient). Domyka adopcję.

**3. Autopilot (B) + kompletność (C) — równolegle, ciągłe.** Każda nowa reguła n8n i
każde nowe auto-źródło **zasila silnik sygnałów** z kroku 1. To tryb pracy, nie milestone.

## Test spójności z wizją

Każdy przyszły feature pytamy: **„czy zasila Wieżę?"**
- Dokłada sygnał, auto-dane albo skraca drogę do akcji → pasuje.
- Kolejny osobny ekran do obchodzenia → czerwona flaga.

## Poza zakresem (świadomie)

- Multi-tenant / SaaS / sprzedaż na zewnątrz (wybrano kierunek wewnętrzny).
- Optymalizacja kosztów jako osobny cel (przychodzi pochodnie przez filar sygnałów).

## Następny krok

To wizja parasolowa. Pierwszy konkret do rozpisania w osobnym cyklu spec → plan:
**Silnik sygnałów + ekran „Co dziś" (zdolność A, krok 1)** — bo ma najwyższą dźwignię
i opiera się wyłącznie na danych, które już są w systemie.

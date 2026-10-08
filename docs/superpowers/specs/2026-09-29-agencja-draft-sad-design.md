# Agencja celna: potwierdzenie odbioru i draft SAD do akceptacji (design)

Data: 2026-09-29 · Status: zatwierdzony w brainstormingu, do przeglądu · Poprzedza: plan wdrożenia

## Cel
Po wysłaniu faktur do agencji (szkic `.eml`: Excel pozycji + kartoteka symboli + PDF) aplikacja
śledzi odpowiedź agencji: potwierdzenie odbioru i draft SAD. Draft SAD jest automatycznie
porównywany z naszymi danymi (faktury, kartoteka, packing list), a operator akceptuje go albo
odsyła do poprawy — jednym kliknięciem, z gotowym szkicem odpowiedzi.

## Ograniczenia (decyzje użytkownika)
- **TIMPORYE działa tylko w sieci wewnętrznej.** Agencja jest podmiotem zewnętrznym —
  nie loguje się do aplikacji ani nie dostaje linków. Kanałem wymiany jest **mail** z Outlooka
  użytkownika (jak dziś szkic `.eml`).
- Agencja nie wprowadza żadnych danych w aplikacji.
- Wejście automatyczne (odczyt odpowiedzi agencji) — **n8n** (preferowane) albo Power Automate
  → folder SharePoint → aplikacja. Oba zależą od dostępu od IT; do tego czasu wejście ręczne.

## Podejście: „B teraz + A później na tym samym wejściu”
- **B (od razu, bez IT):** operator przy paczce faktur klika „Agencja potwierdziła” i wgrywa
  draft SAD z maila.
- **A (po dostępie IT):** automat wywołuje **ten sam** endpoint przyjęcia. Warianty:
  - n8n czyta wspólną skrzynkę odpraw (Microsoft 365 OAuth, `Mail.Read` ograniczone do tej
    skrzynki) i woła API TIMPORYE z tokenem automatyzacji (`X-Automation-Token`);
  - hybryda: Power Automate zapisuje załącznik do SharePointa (`Odprawy/<kontener>/`), n8n albo
    aplikacja pobiera go przez Graph (`Sites.Selected` read — ten sam dostęp co dla faktur).
- Dopasowanie odpowiedzi do kontenera: temat maila z aplikacji `Faktury — <kontener> — <spółka>`,
  odpowiedź `RE: Faktury — <kontener> — …`. Sama odpowiedź = potwierdzenie odbioru; jej
  załącznik PDF = draft SAD.

Odrzucone: konto / link dla agencji (aplikacja niedostępna z zewnątrz); reguła Outlooka
przekierowująca na osobną skrzynkę (i tak wymaga OAuth, nic nie upraszcza).

## 1. Obieg i model danych
Obieg per paczka faktur (jeden mail do agencji = jedna paczka):

```
WYSŁANE ─► POTWIERDZONE przez agencję ─► DRAFT SAD vN ─► porównanie
   ─► ZAAKCEPTOWANY (szkic .eml „akceptuję”)
   └► DO POPRAWY (szkic .eml z rozbieżnościami) ─► agencja przysyła vN+1 ─► porównanie …
```

- **Potwierdzenie odbioru** na paczce faktur: czas, źródło (`manual` / `automation`), użytkownik.
- **Draft SAD** — nowy rekord z numerem wersji w obrębie paczki: plik (także jako załącznik
  kontenera z typem dokumentu „Draft SAD”), suma kontrolna pliku, źródło, dane odczytane z PDF
  (JSON), wynik porównania (JSON), decyzja `pending` / `accepted` / `rejected` + komentarz,
  kto i kiedy.
- Każda zmiana → audyt kontenera. Status dokumentów i słownik statusu sprawy celnej bez zmian —
  obieg dokłada się obok nich.

## 2. Porównanie draft SAD ↔ nasze dane
| Poziom | Pole zgłoszenia | Nasza strona | Zasada |
|---|---|---|---|
| Nagłówek | nr faktur w dokumentach (44) | numery faktur paczki | każda faktura paczki obecna w SAD |
| Nagłówek | waluta i łączna wartość faktur (22) | suma faktur + koszty dodatkowe | w tolerancji kwot profilu dostawcy |
| Nagłówek | kraj wysyłki / pochodzenia (15/34) | kraj dostawcy (LFA1) | zgodny |
| Pozycja | kod towaru (33) | CN z kartoteki (Dane materiałowe SharePoint) | 8 cyfr zgodne; TARIC informacyjnie |
| Pozycja | wartość pozycji (42) | suma pozycji faktur o tym CN | w tolerancji kwot |
| Pozycja | masa netto (38) | wagi netto z packing listy | w tolerancji ilości/wag |
| Pozycja | ilość w jedn. uzupełniającej (41) | ilość × przelicznik (master data) | zgodna, gdy CN jej wymaga |

- Agencja łączy pozycje po kodzie CN → porównanie **grup CN**, nie wierszy.
- Wynik: nagłówek ✓/✗, tabela per CN (nasze / SAD / różnica % / status), „brakuje w SAD”,
  „nadmiarowe w SAD”, podsumowanie („7/7 zgodne” / „2 rozbieżności”). Rozbieżności trafiają do
  treści szkicu „Do poprawy”.
- Odczyt PDF: warstwa tekstowa (jak faktury), OCR dla skanów; pola rozpoznawane po etykietach
  i numerach pól; profil układu agencji (jak profil dostawcy). Pole nieodczytane = jawne
  „nie odczytano pola X”, nigdy zgadywanie — operator porównuje wtedy z PDF obok.

Poza zakresem: wyliczanie należności (cło, VAT) i wartości statystycznej (kompetencja agencji);
odczyt XML z systemu celnego (dopiero, gdy agencja go zaoferuje).

## 3. Ekran, błędy, uprawnienia, testy
**Ekran** — sekcja „Agencja” przy paczce faktur kontenera: wysłano / potwierdzono (źródło),
lista wersji draftu SAD z decyzjami i komentarzami, przyciski „Agencja potwierdziła” i
„Wgraj draft SAD”. „Porównaj” otwiera okno w stylu istniejącej porównywarki (faktura ↔ PL /
zamówienie) z PDF obok; na dole „Akceptuję” i „Do poprawy” (komentarz) → szkic `.eml` odpowiedzi
(`RE: Faktury — <kontener> — …`, adresaci jak przy wysyłce). Kolejka: stan odprawy na kafelku
(„SAD do akceptacji” / „SAD OK”).

**Błędy i brzegi**
- skan bez tekstu → OCR; porażka = „nie odczytano” + porównanie ręczne;
- draft dla kontenera bez wysłanej paczki → przyjęty z ostrzeżeniem;
- ten sam plik ponownie (np. ponowienie automatu) → rozpoznany po sumie kontrolnej, bez nowej wersji;
- decyzja o starej wersji, gdy istnieje nowsza → zablokowana;
- nieznany kontener w wejściu automatu → 404 z czytelnym komunikatem.

**Uprawnienia** — jak „Przygotuj maila do agencji” (`docs_senders`); wejście automatu tokenem
automatyzacji (konto serwisowe), z izolacją spółki jak reszta API.

**Testy-strażnicy**
- porównanie na danych syntetycznych: zgodne, rozbieżny CN / wartość / masa, brakujące i
  nadmiarowe CN, koszty dodatkowe w sumie nagłówka;
- obieg wersji v1 → do poprawy → v2 → akceptacja, blokada decyzji o starej wersji;
- wejście automatu: token, duplikat pliku, nieznany kontener, izolacja spółki;
- szkic `.eml` odpowiedzi: adresaci, temat, rozbieżności w treści;
- odczyt PDF: próbka syntetyczna, potem przykładowy draft Deltaa.

## Kolejność wdrożenia (osobne PR)
1. Model + migracja, obieg wersji, ręczne potwierdzenie i wgranie draftu, decyzja (B).
2. Odczyt draftu SAD + porównanie ↔ faktury + okno porównania.
3. Szkic `.eml` odpowiedzi „Akceptuję” / „Do poprawy”.
4. Wejście automatu (endpoint z tokenem) — pod n8n / hybrydę z SharePointem.
5. Dostrojenie odczytu do przykładowego draftu SAD od Deltaa.

## Sprawy otwarte
- Przykładowy draft SAD od Deltaa (PDF, może być zanonimizowany) — do kroku 5.
- Format: czy agencja może dać XML z systemu celnego albo Excel (dokładniejsze porównanie).
- Wybór automatu (n8n vs Power Automate + SharePoint) — po odpowiedzi IT; n8n na Coolify
  wymaga sprawdzenia (ostatni znany stan: kontener zatrzymany).
- Wspólna skrzynka odpraw zamiast prywatnego konta (wyzwalacz automatu, wysyłka).

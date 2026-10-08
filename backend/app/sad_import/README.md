# Import SAD z WinSAD (`app/sad_import`)

Odczyt PDF „Podgląd danych zgłoszenia celnego importowego” z WinSAD (Huzar Software,
wydruk z pliku ZC415): nagłówek, wszystkie pozycje (także przechodzące przez strony),
opłaty [14 03] i podsumowanie opłat. Kontrola rachunkowa i formalna, raport Excel.

| Moduł | Rola |
|---|---|
| `parser.py` | `parse_sad(ścieżka \| strumień) -> Zgloszenie`; nie-WinSAD → `SadFormatError` |
| `validator.py` | `validate(z, dzis=None) -> list[Wynik]` (statusy `OK` / `WARN` / `ERROR`), `najgorszy()` |
| `excel.py` | `build_workbook(zgloszenia, wyniki) -> BytesIO` (xlsx, 4 arkusze) |
| `service.py` | upload → parser → zakres spółek → walidacja → audyt (dla routera) |
| `__main__.py` | CLI |

Kwoty wyłącznie jako `Decimal`. Dane osobowe (osoba kontaktowa agencji, telefon, e-mail)
nie są odczytywane — nie ma ich w modelu, w JSON-ie ani w raporcie.

## CLI

Z katalogu `backend/`:

```bash
python -m app.sad_import SAD7100001.pdf SAD7100002.pdf -o raport.xlsx
```

- na stdout: per plik numer SAD, liczba pozycji, najgorszy status, liczba WARN/ERROR
  i lista reguł innych niż OK;
- plik spoza WinSAD (albo nie-PDF) → komunikat na stderr, pozostałe pliki idą dalej;
- `-o` domyślnie `raport_sad.xlsx`; bez żadnego odczytanego zgłoszenia plik nie powstaje;
- kod wyjścia: `0` — wszystkie pliki odczytane i żadnego ERROR; `1` — jakikolwiek ERROR
  albo plik nie do odczytania.

## API

| Endpoint | Wynik |
|---|---|
| `POST /api/sad-import/check` | JSON: per plik nagłówek, pozycje, wyniki walidacji albo błąd pliku |
| `POST /api/sad-import/report` | xlsx (arkusze jak niżej) z plików odczytanych i dostępnych |

- multipart, pole `files` (kilka PDF naraz);
- uprawnienia jak drafty SAD: role admin / logistics / purchasing;
- zakres spółek po numerach kontenerów z SAD [19 07] → `deps.check_container_access`
  (konto grupowe widzi każde zgłoszenie); SAD bez widocznego kontenera = błąd pliku bez danych;
- PDF przetwarzany w pamięci, nie jest zapisywany na dysk ani do logów;
- ślad audytu (`sad_import`) na pasującym kontenerze: numer SAD i status walidacji.

## Reguły walidacji

Tolerancje: 1 PLN dla wartości celnej i podstawy VAT, 0,01 dla kwot wyliczonych i sumy
faktur, 0 dla kwot należnych (pełne PLN, zaokrąglenie 0,5 w górę).

Pozycja:

| Reguła | Niezgodność |
|---|---|
| wartość celna (A00) = wart. fakt. × kurs + ΣAK | ERROR |
| wartość celna (A00) = wartość stat. [99 06] | ERROR |
| A00/B00…: kwota wyliczona = podstawa × stawka | ERROR |
| A00/B00…: należna = zaokrąglenie kwoty wyliczonej | ERROR |
| podstawa VAT (B00) = A00 + cło + ΣCA | ERROR |
| Σ należnych = kwota ogółem [14 16] | ERROR |
| masa netto > 0 | ERROR |
| kraj pochodzenia podany | ERROR |
| kod CN: 8 cyfr | ERROR |
| ilość z opisu (SZT) = ilość w jedn. uzup. [18 02] (gdy opis podaje SZT) | WARN |
| faktura (N935) w dokumentach [12 03] | WARN |

CA (transport od granicy UE do miejsca przeznaczenia) nie wchodzi do wartości celnej,
tylko do podstawy VAT (art. 30b ustawy o VAT).

Zgłoszenie:

| Reguła | Niezgodność |
|---|---|
| liczba pozycji z nagłówka = odczytane pozycje | ERROR |
| Σ wartości fakturowych pozycji = wartość faktur [14 06] | ERROR |
| Σ opakowań pozycji = liczba opakowań | ERROR |
| Σ mas netto ≤ masa brutto [18 04] | ERROR |
| Σ należnych KOD = podsumowanie opłat (każdy kod opłaty) | ERROR |
| numer kontenera [19 07] podany | WARN |
| kontener: cyfra kontrolna ISO 6346 | ERROR |
| NIP importera: cyfra kontrolna | ERROR |
| nr VAT FR7 [13 16] = PL + NIP importera | ERROR |
| stan AIS: zgłoszenie przyjęte / zwolnione | WARN |
| deklarowana data zgłoszenia podana | WARN |
| data zgłoszenia nie starsza niż 14 dni od wydruku | WARN |
| data zgłoszenia nie w przyszłości | WARN |

Draft przed wysłaniem ma stan AIS „W przygotowaniu” — WARN jest wtedy oczekiwany.

## Raport Excel

| Arkusz | Wiersz | Zawartość |
|---|---|---|
| Zgłoszenia | 1 SAD | pola nagłówka, Σ cło (należne A00), Σ VAT (należne B00), status walidacji (najgorszy) |
| Pozycje | 1 pozycja | nr SAD, LRN, kontenery, faktury N935, proformy N325, pola pozycji, A00 i B00 (podstawa / stawka / wyliczona / należna / metoda), kwota ogółem, kolumny kontrolne |
| Walidacja | 1 reguła | nr SAD, pozycja, reguła, oczekiwane, odczytane, status (OK zielony, WARN żółty, ERROR czerwony) |
| Dokumenty | 1 dokument | nr SAD, pozycja, kod dokumentu [12 03], numer |

- kwoty i masy to liczby (`#,##0.00`), kurs `0.0000`, stawki ułamkiem w formacie `0.0%`,
  daty jako daty;
- identyfikatory (nr SAD, LRN, CN, TARIC, NIP, EORI, kontener, kody) jako tekst — zera
  wiodące zostają (TARIC „00”);
- kolumny kontrolne w „Pozycje” to formuły z komórek wiersza:
  `Wartość celna wyliczona = ROUND(wart. fakt. × kurs + ΣAK; 0)`, różnica z podstawą A00,
  `Podstawa VAT wyliczona = ROUND(A00 podstawa + A00 należna + ΣCA; 0)`, różnica z podstawą B00
  (różnica > ±1 PLN = coś do sprawdzenia);
- nagłówek pogrubiony i zamrożony, autofiltr na każdym arkuszu, czcionka Arial.

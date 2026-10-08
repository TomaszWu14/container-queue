# Kontrole jakości danych (SQL, tylko odczyt)

Źródło: audyt 2026-09-28, ustalenie DATA-007 (zapytania: `audit/sql/data_*.sql`, przetestowane na danych
syntetycznych). Kopia operacyjna: `backend/scripts/data_quality/`, uruchamiana skryptem
`backend/scripts/data_quality.py`. Kontrole w panelu (Master data → Jakość danych) to osobny, prostszy
zestaw reguł (`backend/app/master_quality.py`).

## Co sprawdzają

| Plik | Co | Oczekiwane |
|---|---|---|
| `data_01` | duplikaty numeru kontenera (aktywne / historia) | 0 aktywnych duplikatów |
| `data_02` | numery kontenerów niezgodne z ISO 6346 (cyfra kontrolna) | 0 (poza świadomymi numerami tymczasowymi / AWB) |
| `data_03` | duplikaty zamówień (PO) | 0 |
| `data_04` | duplikaty dostawców | 0 w (a) i (c); (b) do przeglądu |
| `data_05` | pola wymagane przez logikę, a puste | 0 w każdej regule |
| `data_06` | daty nierealne i sprzeczne (np. ETA < ETD) | 0 w każdej regule |
| `data_07` | status sprzeczny z datami | 0 w regułach twardych (`!`) |
| `data_08` | sieroty relacji, powiązania między spółkami | wg opisu w pliku |
| `data_09` | wartości spoza słowników w kolumnach tekstowych | 0 (poza rozkładem `container_size`) |
| `data_10` | liczniki i denormalizacje vs rekordy, luki `transport_id` | 0 w pierwszej części |

Pełny opis reguł jest w nagłówku każdego pliku — raport go przepisuje.

## Jak uruchomić
Tylko PostgreSQL (SQLite w dev → skrypt odmawia, kod 2). Sesja jest ustawiana jako **tylko do odczytu**
(`SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`), każde zapytanie ma limit 120 s i własną
transakcję — błąd jednego nie zatrzymuje reszty.

```sh
# produkcja (kontener aplikacji ma DATABASE_URL i skrypty w /app)
docker exec -it $(docker ps -qf name=app) python -m scripts.data_quality
docker exec $(docker ps -qf name=app) python -m scripts.data_quality --json > jakosc-$(date +%F).json
```

Kod wyjścia: `0` = wszystko wykonane; `1` = błąd zapytania (albo, z `--fail-on-findings`, jakiekolwiek
znalezisko); `2` = baza nie jest PostgreSQL. „Znaleziska” to wiersze z kolumną `ile` > 0, a w
zapytaniach bez tej kolumny — liczba zwróconych wierszy. Część zapytań jest informacyjna
(rozkłady, luki numeracji), więc wynik czyta człowiek, porównując z kolumną „Oczekiwane”.

## Harmonogram (propozycja)
Coolify → aplikacja → **Scheduled Tasks → Add**:

| Nazwa | Command | Frequency (cron) |
|---|---|---|
| `jakosc-danych` | `python -m scripts.data_quality` | `30 6 * * 1` (poniedziałek 6:30) |

Wynik jest w logu zadania w Coolify. Raport mailem albo do Teams: przez n8n (Execute Command →
`--json`) — TODO(właściciel): czy i do kogo. Reguły, które na produkcji regularnie coś znajdują,
warto przenieść do `master_quality.RULES`, żeby były widoczne w panelu (rekomendacja DATA-007).


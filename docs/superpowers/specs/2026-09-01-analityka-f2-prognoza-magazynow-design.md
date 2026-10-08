# Analityka F2: prognoza obciążenia magazynów — design

Data: 2026-09-01 · Status: zatwierdzony przez użytkownika

## Cel

Logistyka widzi z wyprzedzeniem, którym magazynom grozi przeciążenie rozładunkami,
zanim kolejka aut stanie pod rampą.

## Decyzje (z brainstormingu)

1. Miary: **obie** — kontenery/dzień vs `DailyLimit` (twarda oś) + palety/dzień.
2. Braki `pallet_count` → szacunek: średnia historyczna per dostawca, fallback
   średnia globalna; wartości szacowane oznaczone w UI.

## Zakres

### 1. Dane i horyzont

- Aktywne kontenery (statusy przed rozładunkiem/zakończeniem) z datą planowaną
  (proponowana data dostawy; fallback ETA), per magazyn/dzień.
- Horyzont: 4 tygodnie w przód od dziś.

### 2. Endpoint prognozy

- `GET /api/analytics/warehouse-forecast` (role jak moduł Analiza):
  `{warehouses: [{id, name, days: [{date, containers, limit, pallets,
  pallets_estimated: bool}]}]}`.
- Liczenie w SQL (grupowanie po magazynie i dacie) + słownik średnich palet
  per dostawca z historii (kontenery zakończone, pallet_count > 0).

### 3. Widok — heatmapa tygodniowa

- W module Analiza nowa karta „Prognoza magazynów": wiersze = magazyny,
  kolumny = dni (4 tyg., przewijane tygodniami), kolor komórki wg % limitu
  (zielony <80%, bursztyn 80–100%, czerwony >100%); w komórce liczba kontenerów
  i palet (szacunek oznaczony „~").
- Klik w komórkę → lista kontenerów tego dnia/magazynu (link do szczegółów).
- Style spójne z paletami projektu (tokeny, `table.analysis-grid`/heatmapa).

### 4. Alert przekroczenia

- Ustawienie `forecast_alert_days` (admin, domyślnie 7).
- Przebieg w istniejącym cyklu alertów: przewidywane przekroczenie limitu
  w ciągu N dni → `notify(kind="forecast-overload")` do obserwatorów spółki
  z magazynem i datą; dedup raz dziennie per magazyn+data.

## Poza zakresem

- Godziny pracy ramp / sloty.
- Modele ML, sezonowość — prosta projekcja z dat planowanych.

## Testy

- Prognoza: grupowanie per magazyn/dzień, fallback ETA, tylko aktywne statusy.
- Szacunek palet: średnia dostawcy, fallback globalna, flaga `pallets_estimated`.
- Alert: tylko przekroczenia w oknie N dni, dedup per magazyn+data.

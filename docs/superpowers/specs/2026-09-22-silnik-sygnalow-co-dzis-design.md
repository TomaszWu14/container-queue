# Spec: Silnik sygnałów + lista „Co dziś" (v1)

*Data: 2026-09-22 · Zdolność A z [wizji control tower](2026-09-22-wizja-control-tower-design.md), krok 1*

## Cel

Zamienić trzy osobne listy dashboardu (`delayed_list`, `today_list`, `demurrage_list`)
w **jedną posortowaną listę działań „Co dziś"** na Wieży, zasilaną wspólnym silnikiem
sygnałów. Najwyższa dźwignia wizji przy oparciu wyłącznie o dane już w systemie.

## Zakres v1

**Jest:** jedna lista na istniejącym `/api/stats/dashboard`, 6 typów sygnałów, punktacja
pilność×koszt, deep-link per typ, izolacja przez `scope_containers`.

**Poza zakresem (follow-up):** akcje inline (v1 = tylko deep-link), osobny feed
magazynu/klienta (inny filtr per persona), push do n8n/alertów, panel admina do wag.

## Architektura

Czysty, testowalny moduł `backend/app/signals.py`:

```
compute_signals(containers, deadlines, today, weights=SIGNAL_WEIGHTS) -> list[Signal]
```

`Signal` (dataclass/dict): `container_id, container_no, type, score, urgency_days,
cost_eur|None, action{kind, container_id}, summary`.

Wołany przez istniejący `/api/stats/dashboard` (containers.py:1580), który dostaje nowe
pole `action_feed: list[Signal]` (sort malejąco). Zero dodatkowych zapytań — dashboard
już ładuje kontenery ze `scope_containers` i `demurrage_deadlines`. Trzy legacy listy
mogą zostać w odpowiedzi (kompatybilność), ale UI renderuje `action_feed`.

### Typy sygnałów i reguły

| Typ | Reguła | action.kind |
|---|---|---|
| `delayed` | `delay_days > 0` (po ETA, inaczej po awizacji) | container |
| `demurrage` | `deadline` ≤ próg dni; `cost_eur = dni_po_terminie × stawka` | container |
| `stuck` | brak ruchu ≥ próg dni (reużyj logiki „utknął" z W5) | container |
| `missing_avizo` | `eta` ≤ próg dni i brak `notify_date` | avizo-form |
| `missing_eta` | status w transporcie/porcie i brak `eta` | container |
| `missing_docs` | `document_status == BRAK` (lub brak wymaganych) | documents |

Jeden kontener może wygenerować kilka sygnałów (różne typy) — każdy to osobna pozycja.

### Punktacja

```
score = weight[type] * urgency_factor + cost_factor
  urgency_factor = f(urgency_days)     # rośnie z dniami po terminie / maleje z dniami do terminu
  cost_factor    = (cost_eur or 0) / COST_SCALE
```
Sort: `score` malejąco; remis → większy `cost_eur`, potem mniejszy `container_no`.

### Pokrętło strojenia (calibration knob)

Wszystkie wagi i progi w jednym słowniku `SIGNAL_WEIGHTS` w `signals.py` z domyślnymi:
- `weight[type]` per typ sygnału,
- progi: `demurrage_days`, `avizo_lead_days`, `stuck_days`,
- `COST_SCALE`.

Stawka €/dzień demurrage: w configu NIE istnieje osobne pole €/dzień (są tylko
`demurrage_alert_days`, `demurrage_default_free_days`), więc `demurrage_eur_per_day`
to nowa stała w `SIGNAL_WEIGHTS` (część pokrętła). Panel admina do edycji wag =
follow-up; w v1 knob = nazwane, opisane stałe.

## Frontend

Wieża (dashboard) renderuje jedną listę „Co dziś" z `action_feed` zamiast 3 paneli.
Wiersz: badge ważności (kolor wg progu score) · `container_no` · zwięzły `summary`
(np. „demurrage za 2 dni ≈ €600", „ETA jutro, brak awizacji") · `→` deep-link.
KPI-kafelki zostają bez zmian.

Mapowanie `action.kind → route` po stronie frontendu (zna routing):
- `container` → `/kontenery/{id}`
- `avizo-form` → formularz awizacji kontenera
- `documents` → karta kontenera / sekcja dokumentów

i18n etykiet typów sygnałów i szablonów `summary` (PL/EN/PT).

## Obsługa błędów / przypadki brzegowe

- Brak `eta` i `notify_date` → `delayed` się nie odpala (brak punktu odniesienia), ale
  `missing_eta`/`missing_avizo` tak.
- `deadlines[c.id]` None → brak sygnału demurrage.
- Pusty feed → UI pokazuje stan „nic nie wymaga uwagi" (pozytywny, nie „brak danych").
- Magazyn: dashboard nadal 403 (bez zmian); feed magazynu to osobny spec.

## Testy

`backend/tests/test_signals.py` — na czystej funkcji `compute_signals` (bez DB):
- każdy typ sygnału wykrywany na spreparowanym kontenerze,
- kolejność: demurrage z kosztem > drobny `missing_docs`,
- kontener z wieloma sygnałami → wiele pozycji,
- pusta lista → pusty feed,
- `action.kind` poprawny per typ.

## Następny krok

Po akceptacji specu → skill writing-plans (plan implementacji).

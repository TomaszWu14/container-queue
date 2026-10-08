# Moduł Analityka i Predykcja — Faza 1 (baseline end-to-end)

Data: 2026-08-05
Status: spec zatwierdzony (do przeglądu przed planem implementacji)

## Cel

Zastąpić ręczne reguły zapotrzebowania (`target_days × zużycie_dzienne`) w module
wywołań palet z DLT **prognozą dziennego popytu per produkt**. Faza 1 dostarcza
działający system end-to-end oparty o **baseline** (średnia krocząca + profil
sezonowy), za interfejsem, który w Fazie 2 podmieni model ML — bez ruszania reszty.

Prognozowany jest **dzienny popyt per produkt**. Dwa pozostałe wyniki wyliczają się
z niego deterministycznie:
- **Zapotrzebowanie na palety** = `suma(prognoza na horyzont) / PAZ − stan − już_wywołane`.
- **Dzień wyczerpania zapasu** = stan podzielony przez narastającą prognozę.

## Ustalenia (z brainstormu)

- **Dane wejściowe:** dzienna historia wydań per produkt, 2–3+ lata, z wymiarami
  (firma, magazyn, kontrahent). Master data leży dziś na dysku firmowym.
- **Ingest:** ręczny upload pliku (CSV/XLSX) w panelu. Bez watchera/integracji SAP
  na tym etapie (YAGNI).
- **Horyzont:** suwak w panelu (planista ustawia; lead time z DLT bywa różny).
- **Odświeżanie:** automatycznie po wgraniu nowych danych + przycisk „Przelicz".
  Bez codziennego auto-retreningu (dane wchodzą ręcznie).
- **Rola planisty:** prognoza to **sugestia z przedziałem niepewności**
  („18–24 palety"); człowiek decyduje i klika „Wywołaj".
- **Kryterium sukcesu:** biznesowo — mniej braków (stockoutów) i mniej zalegania
  w DLT; technicznie — **bramka: ML musi pobić baseline**, inaczej zostajemy przy
  baseline.

## Architektura

Nowy pakiet `backend/app/analytics/` + strona `AnalitykaPage` na froncie.
Jedno źródło prawdy dla prognozy, konsumowane przez wywołania DLT.

```
upload (CSV/XLSX) → walidacja/podgląd → tabela material_issues (historia)
                                              │
                                    Predictor.forecast(produkt, horyzont)
                          (Faza 1: BaselinePredictor; Faza 2: ML — ten sam interfejs)
                                              │
                          ┌───────────────────┴───────────────────┐
                 Analityka (wykres + przedział)          Wywołania DLT (sugestia palet)
```

## Komponenty

### `analytics/ingest.py`
Parser CSV/XLSX → wiersze `(data, produkt, ilość, firma, magazyn, kontrahent)`.
Zwraca **raport walidacji przed zapisem**: liczba wierszy, nieznane produkty,
błędne/niepełne wiersze, wykryte duplikaty. Zapis dopiero po zatwierdzeniu podglądu.
Import **przyrostowy** (dokładanie nowych dni), dedup po `(źródło_pliku, produkt, data)`.

### `analytics/models.py` — `MaterialIssue`
Historia wydań: `date, product, qty, company_id, warehouse, counterparty, source_file`.
Indeks po `(product, date)` dla szybkiego odczytu serii.

### `analytics/predictor.py` — interfejs `Predictor`
```
forecast(product, horizon_days) -> list[DayForecast{date, mean, lo, hi}]
```
**Faza 1: `BaselinePredictor`** — sezonowo-naiwny: profil dnia tygodnia
przemnożony przez średnią kroczącą poziomu; przedział z historycznego rozrzutu
reszt (np. ±1 odch. std, konfigurowalne). To jest szew rozszerzalności — Faza 2
wstawia `MLPredictor` (globalny XGBoost/LightGBM, produkt jako cecha) za tym samym
interfejsem.

### Integracja z wywołaniami
W `pallets_analysis.build_rows` zapotrzebowanie liczone z `sum(forecast na horyzont)`
zamiast `zużycie_dzienne × target_days`. Przedział niepewności niesie się do sugestii
palet. Reszta logiki (cap do `floor(stan_DLT)`, odejmowanie `już_wywołane`,
`brak_paz`) bez zmian.

## Przepływ / UI

Moduł „Analityka i Predykcja" (rola admin/logistics):
1. **Wgraj dane** — drag pliku, podgląd raportu walidacji, zatwierdź.
2. **Prognoza per produkt** — wykres historii + prognozy z pasmem niepewności,
   suwak horyzontu.
3. Zasila **Wywołania DLT** (sugestia z przedziałem).

## Błędy i przypadki brzegowe

- Zły plik/kolumny → raport błędów w podglądzie, **nic nie zapisujemy**.
- Produkt bez wystarczającej historii → brak prognozy, oznaczony jako sygnał
  (analogicznie do dzisiejszego `brak_paz`), bez crashu.
- Brak PAZ dalej blokuje przeliczenie sztuk na palety (bez zmian).

## Testy

- `test_ingest` — parsuje przykładowy CSV, łapie zły nagłówek i duplikaty.
- `test_baseline` — na syntetycznej sezonowej serii prognoza trafia w profil;
  przedział pokrywa prawdę w oczekiwanym odsetku.
- Self-check `__main__` w `predictor.py`.

## Świadomie poza Fazą 1

- Silnik ML (globalny XGBoost/LightGBM) — osobny spec, wchodzi po pobiciu baseline.
- Watcher folderu / cykliczny import z SAP.
- Automatyczny retrening.

## Otwarte do potwierdzenia

- ~~Dokładny format pliku (CSV vs XLSX) i nazwy kolumn źródłowych~~ — **rozstrzygnięte
  (D16, 2026-09-24): xlsx + autodetekcja nagłówków**. W praktyce ustalił to import stanów
  DLT z autodetekcją kolumn. Nazwy kolumn nie są sztywnym kontraktem.
- Skala (liczba produktów) — projekt zakłada setki–tysiące SKU (globalny model w
  Fazie 2 to obsługuje).
- Mapping kolumny `niestandardowe` w istniejących wywołaniach (parking z Pytania 1)
  — niezależny wątek, nie blokuje Fazy 1.

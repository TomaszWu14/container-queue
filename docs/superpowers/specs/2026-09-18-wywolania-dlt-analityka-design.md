# Wywołania palet DLT — auta/HU/analityka zapasu (rozszerzenie modułu)

Data: 2026-09-18 · Status: zatwierdzony w brainstormingu (sesja)

## Decyzje użytkownika

1. Źródło danych: **Power BI — rozszerzony dataset** (stany naszego magazynu + stany
   DLT na poziomie HU). Feature-detect: bez nowych kolumn moduł działa jak dziś.
2. **132 miejsca = 4 auta × 33 miejsca paletowe** (naczepa) — wywołanie planuje
   załadunek konkretnych aut.
3. Wysyłka: **auto-mail przy „Wyślij wywołanie"** (Excel w załączniku, adresy DLT
   z konfiguracji, kopia do wywołującego, status WYSŁANE, audyt).
4. Analityka: **zużycie ze średniej kroczącej rozchodów w PBI (30 dni)**, cel
   pokrycia w dniach **globalny + nadpisywalny per materiał**; podpowiedź wywołania
   = braki do celu w pełnych paletach, przycięte do 132 miejsc.

## Zakres

### Dane i przeliczniki
- Rozszerzenie zapytań PBI (backend/app/powerbi.py + pallets_analysis.py):
  stany WŁASNE, stany DLT per HU (materiał, nr HU, ilość, lokalizacja), rozchody
  dzienne (30 dni) — degradacja przy braku kolumn (flaga w odpowiedzi API).
- Palety z MARM: ilość ÷ (szt/paletę z jednostki PAL w MaterialUnit) → Numeric(7,3)
  („7,3 palety"); brak przelicznika → tylko szt + oznaczenie.

### Model
- `PalletCallTruck` (call_id FK, ordinal 1..4, capacity=33).
- `PalletCallLine` + `truck_id` FK NULL, `hu_numbers` (Text, lista), `pallets`
  Numeric(7,3).
- Cel pokrycia: `pallet_target_days` globalnie (ustawienia/konfiguracja) +
  nadpisanie per materiał (nowa tabela `MaterialStockTarget(material_no, days)`,
  edycja w Master data).
- Migracja alembic na końcu łańcucha + dev-shim.

### Analityka (strona modułu Wywołania-DLT)
- Tabela per materiał: stan NASZ (szt + palety), stan DLT (szt + palety),
  zużycie/dzień, **zapas w dniach**, cel dni, **podpowiedź wywołania (palety)**.
- Sortowanie po zapasie w dniach (najkrótszy u góry), filtr „poniżej celu",
  przycisk „Dodaj podpowiedzi do wywołania" (prefill kreatora).

### Kreator wywołania
- Wybór pozycji: ilość materiału LUB konkretne HU (checkboxy ze stanów DLT).
- Przydział do aut 1–4 z licznikiem zajętości (suma palet ceil per HU, guard ≤33
  na auto, podgląd ∑/132).

### Wysyłka
- Excel: arkusz per auto (miejsce, materiał, HU, ilość, palety) — rozszerzenie
  pallets_export.build_xlsx.
- Mail przez notifications/SMTP na adresy z konfiguracji (env `DLT_CALL_EMAILS`
  lub kontakt magazynu DLT ze słownika — wybrać istniejący mechanizm) + kopia do
  autora; status WYSŁANE + sent_at + audyt.

## Testy
- pytest: guard 33/auto i 132/wywołanie, przeliczniki MARM (ułamki, brak PAL),
  degradacja bez kolumn HU/rozchodów, podpowiedź (cel per materiał > globalny),
  mail (mock SMTP), Excel (arkusze per auto), izolacja spółek.
- vitest: tabela analityki (sort/filtr), kreator (licznik 33, prefill z podpowiedzi).

## Poza zakresem (świadomie)
- Link potwierdzenia dla DLT (tokenowy „przygotowane") — można dołożyć później.
- Automatyczny dobór HU przez system — wskazuje człowiek albo leci sama ilość.

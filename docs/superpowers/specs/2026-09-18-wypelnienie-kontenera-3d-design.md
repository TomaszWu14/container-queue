# Wizualizacja wypełnienia kontenera 3D (pakowanie kartonów)

Data: 2026-09-18 · Status: zatwierdzony przez użytkownika (brainstorming w sesji)

## Cel

Na karcie kontenera (`/kontenery/:id`) pokazać, jak wypełniony jest kontener: scena 3D
z ułożonymi kartonami + % wypełnienia.

## Decyzje (z brainstormingu)

1. **Pełne 3D** (nie sam wskaźnik %) — Three.js + realny packer.
2. **Silnik pakowania portowany do TIMPORYE** (moduł w FastAPI, zależność `py3dbp`) —
   zero zależności sieciowej od zewnętrznych serwisów.
3. **Wymiary jednostek z MARM** (rozszerzenie importu o LAENG/BREIT/HOEH + MEABM);
   materiał bez wymiarów, ale z objętością → sześcian o tej objętości (flaga
   `approximated`); bez objętości → lista `excluded` z powodem.
4. **Miejsce: tylko karta kontenera** (bez kolumny % w kolejce i trybu planowania —
   świadomie poza zakresem, można dołożyć później).

## Architektura

### Backend — `backend/app/packing/`

- Logika pakowania (reguła: najpierw bloki mono-SKU,
  resztki mieszane) na py3dbp.
- Wejście: pozycje zamówień kontenera (`OrderItem`: quantity, material) × wymiary
  jednostki z `MaterialUnit` (MARM). Wymiary wnętrza per typ kontenera — stała
  (20' ≈ 589×235×239 cm, 40', 40'HC).
- Endpoint `GET /api/containers/{id}/packing` (Viewer + `check_container_access`),
  on-demand + krótki cache w pamięci procesu.
- Wynik JSON:
  `{ boxes: [{x,y,z,w,h,d,sku,color,approximated}], fill_pct, volume_used_m3,
     volume_total_m3, container_dims, excluded: [{order_no, material, reason}] }`.

### Import MARM — rozszerzenie

Model `MaterialUnit` + kolumny `length`/`width`/`height` (Numeric, NULL) +
`dimension_unit` (MEABM; MM/CM/M → normalizacja do cm przy odczycie). Mapowanie
nagłówków: LAENG/DŁUGOŚĆ, BREIT/SZEROKOŚĆ, HOEH/WYSOKOŚĆ, MEABM/„JEDN. WYM".
Migracja alembic na końcu łańcucha.

### Frontend — panel „Wypełnienie kontenera"

- Nowa zależność npm `three`; scena ładowana **leniwie** (dynamic import), żeby nie
  tuczyć głównego bundla.
- Kontener jako przezroczysty szkielet, kartony jako bloki kolorowane per SKU/zamówienie,
  OrbitControls, HUD `% wypełnienia · X/Y m³`.
- Bloki `approximated` półprzezroczyste + legenda; pod sceną lista „Nieuwzględnione
  pozycje (brak danych MARM)" z linkiem do Master data → Jednostki (MARM).

## Błędy i brzegi

- Kontener bez pozycji / bez typu → komunikat zamiast sceny.
- Wszystkie pozycje bez danych MARM → wskaźnik „brak danych do ułożenia" + lista braków.
- Przepełnienie → packer układa co wchodzi, reszta w `excluded` („nie zmieściło się"),
  HUD czerwony >100%.
- Endpoint nie zwraca 500 przez śmieciowe dane — złe wiersze lądują w `excluded`
  z powodem.

## Testy

- pytest: packer (mono-SKU przed mieszanymi, determinizm, przepełnienie, fallback
  sześcianu, excluded), endpoint (izolacja spółek, kształt JSON), import MARM z wymiarami.
- vitest: panel renderuje HUD i listę braków z mockowanego JSON; scena WebGL za
  feature-detect (jsdom bez WebGL).

## Plan dostarczenia

- **PR 1**: rozszerzenie MARM o wymiary (model+migracja+import+zakładka Master data).
- **PR 2**: packer + endpoint + panel 3D na karcie kontenera.

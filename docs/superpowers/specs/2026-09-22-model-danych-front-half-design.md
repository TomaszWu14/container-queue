# Plaster 1: model danych front↔back (zamówienie ↔ kontener + CRD)

Data: 2026-09-22 · Status: spec do implementacji · Poprzednik: `2026-09-22-analiza-spec-transportu-design.md`

## Cel

Położyć **fundament pierwszej połowy procesu** (koszyk → CRD → konsolidacja), tak
by zepiął się z istniejącą kolejką/trackingiem (druga połowa). Bez tego modelu
konsolidacja, CRD/eskalacja i harmonogram nie mają się o co oprzeć.

Zakres tego plastra to **tylko model danych + reguły + endpointy odczytu**. UI
koszyka, silnik konsolidacji i eskalacja CRD to kolejne plastry.

## Założenia biznesowe (przyjęte wg rekomendacji — do korekty przez Dział Transportu)

> ⚠️ To są reguły domenowe. Przyjęte jako rozsądny default; jeśli w Excelu robicie
> inaczej — zmieniamy PRZED migracją, nie po.

- **ZAŁ-1 (CRD kontenera):** CRD kontenera = **najpóźniejsze CRD** z jego zamówień.
- **ZAŁ-2 (blokada):** próg eskalacji (10 dni) i blokada dotyczą **zamówienia**, nie
  całego kontenera. Zablokowane zamówienie **wypada z konsolidacji**; kontener jedzie dalej.
- **ZAŁ-3 (człowiek/automat):** automat **proponuje** konsolidację (sortowanie po
  dostawcy, sumowanie CBM ≤70), człowiek **zatwierdza/koryguje**. Automat nie domyka kontenerów.
- **ZAŁ-4 (źródło prawdy):** SAP jest źródłem dla zamówień/dostawcy; aplikacja dla
  daty dostawy/CRD/przypisań. Re-import z SAP nie nadpisuje po cichu — loguje drift.

## Model danych

> **Korekta po przeglądzie kodu (ponytail — reuse):** `PurchaseOrder` już ma
> `cbm` (Numeric), `container_id` (FK many:1 → jeden kontener agreguje wiele
> zamówień) oraz `ready_date` (tekst — źródłowy CRD z arkusza). Dlatego **NIE**
> dodajemy tabeli m:n ani pola CBM — relacja konsolidacji już istnieje przez
> `container_id`, a plaster 1 dokłada tylko brakujące pola dat/statusu.

### Istniejące, rozszerzane
- **`PurchaseOrder`** — dodać tylko brakujące:
  - `crd: date | null` — Cargo Ready Date jako **data** (do arytmetyki odchylenia);
    `ready_date: str` zostaje jako źródłowy zapis z arkusza (nie ruszamy)
  - `crd_target: date | null` — zakładany CRD/ETD (baza odchylenia)
  - `cart_status: enum` — `w_koszyku | zwolnione | przypisane | zablokowane`
  - (`cbm`, `container_id`, `supplier` — **już są**, reużywamy)

### Relacja zamówienie ↔ kontener
- **Reużywamy istniejący `PurchaseOrder.container_id`** (many:1). Wiele zamówień z
  tym samym `container_id` = konsolidacja w jednym kontenerze. Zamówienie
  nieprzypisane: `container_id IS NULL` + `cart_status='w_koszyku'`.

### Nowy stan kontenera-konsolidacji
- **`Container`** — dodać:
  - `consolidation_status: enum` — `otwarty | wypelniony | zamkniety`
    (dopóki `otwarty`/`wypelniony` — można dodawać/odejmować zamówienia; `zamkniety`
    wchodzi w istniejący obieg kolejki/trackingu)
  - `capacity_cbm: numeric` — domyślnie 70

### Pola wyliczane (nie kolumny — property/serwis, jedno źródło prawdy)
- `Container.fill_cbm` = suma `cbm` zamówień przypisanych
- `Container.crd` = **max** `crd` zamówień (ZAŁ-1)
- `Container.is_overfilled` = `fill_cbm > capacity_cbm`

## Reguły (do testów)
1. Dodanie zamówienia do `zamkniety` kontenera → 400 (nie wolno).
2. `fill_cbm` nigdy nie liczy zamówień `zablokowane` (ZAŁ-2 — wypadają z konsolidacji).
3. `Container.crd` = max z niezablokowanych zamówień; brak zamówień → null.
4. Zamówienie może być w **maksymalnie jednym** kontenerze naraz (unikat + guard).
5. Izolacja: nowe encje przechodzą przez `_enforce_scope`/`scope_*` (spółka), audyt zmian.

## Endpointy (tylko odczyt w tym plastrze)
- `GET /api/purchase-orders?cart_status=w_koszyku` — koszyk (zawężony scope)
- `GET /api/containers/{id}/orders` — zamówienia w kontenerze + `fill_cbm`, `crd`, `capacity`
- (mutacje: dodaj/usuń zamówienie z kontenera, zmiana CRD, zwolnienie — **kolejny plaster**)

## Migracja
Wyłącznie **addytywna**: nowe kolumny (nullable/default), nowa tabela łącząca. Nie
rusza istniejących wierszy ani obiegu kolejki. Jedna głowa alembica (strażnik
`test_migration_chain`).

## Poza zakresem (kolejne plastry)
- UI koszyka + drag zamówień do kontenerów
- Silnik auto-propozycji konsolidacji (sortowanie po dostawcy, pakowanie ≤70)
- CRD: odchylenie, próg 10 dni, blokada→Kupiec, alerty
- Zapis do SAP (drift-detection)

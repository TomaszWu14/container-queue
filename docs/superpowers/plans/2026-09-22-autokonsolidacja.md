# Plaster 6: silnik auto-propozycji konsolidacji (backend) — Plan (draft, scratchpad)

**Goal:** Zaproponować pogrupowanie zamówień z koszyka w kontenery ≤70 CBM (sortowanie po dostawcy), jako **tylko-odczyt** (propozycja); człowiek zatwierdza istniejącymi mutacjami przypisania (plaster 2). Reguły z RFP §5.1 + dok. 3 + ZAŁ-3 (automat proponuje, człowiek zatwierdza).

**Architecture:** Czysta funkcja pakowania `propose_consolidation(orders)` w `app/consolidation.py` (testowalna bez DB) + endpoint `GET /api/consolidation/proposals` w routerze (zbiera koszyk danej spółki, woła funkcję). Nic nie mutuje.

## Global Constraints
- Tylko odczyt — endpoint NIE zmienia bazy. Zatwierdzenie = istniejące `PUT /containers/{cid}/orders/{poId}` (plaster 2).
- Reguły (udokumentowane): grupuj po dostawcy; sumuj CBM; jeden kontener ≤ 70 CBM (`Container.capacity_cbm`/stała 70). Zamówienia bez CBM traktuj jako 0 (i oznacz `has_unknown_cbm`).
- Bierz tylko zamówienia „gotowe do konsolidacji": `container_id IS NULL` i `cart_status in (w_koszyku, zwolnione)`; pomiń `zablokowane`.
- Izolacja spółki (`company_filter_ids`).

---

### Task 1: Czysta funkcja pakowania

**Files:** Modify `backend/app/consolidation.py`; Test `backend/tests/test_autokonsolidacja.py`

**Interfaces:** `propose_consolidation(orders: list, capacity: float = 70.0) -> list[dict]`
gdzie `orders` = lista obiektów z `.id`, `.supplier`, `.cbm`; zwraca listę propozycji
`{"supplier": str, "orders": [id,...], "total_cbm": float}`.

Algorytm (first-fit malejąco per dostawca — mono-dostawca najpierw):
1. Grupuj po `supplier`.
2. W każdej grupie sortuj malejąco po `cbm`, pakuj first-fit do binów ≤ capacity.
3. Każdy bin = jedna propozycja (supplier, ordery, suma).
(Miks różnych dostawców w jednym kontenerze — POZA tym plastrem; MVP = mono-dostawca, jak „≥2 od jednego dostawcy = 1 kontener".)

Testy:
- 2 zamówienia tego samego dostawcy 30+30 CBM → jedna propozycja total 60.
- 30+50 CBM (razem 80 > 70) → dwie propozycje (bin-packing).
- różni dostawcy → osobne propozycje per dostawca.
- cbm=None → liczone jako 0, flaga (opcjonalnie) — minimalnie: nie wywala się.

### Task 2: Endpoint `GET /api/consolidation/proposals`

**Files:** Modify `backend/app/routers/consolidation.py`; Test dopisać.

Zbierz `PurchaseOrder` gdzie `container_id IS NULL`, `cart_status in (w_koszyku, zwolnione)`, scope spółki; wywołaj `propose_consolidation`; zwróć listę propozycji + dla każdej pozycji nazwy zamówień (do UI). Test: koszyk 2 zamówień 1 dostawcy ≤70 → 1 propozycja przez API.

## Poza zakresem
Miks wielu dostawców w kontenerze; UI propozycji (przycisk „Zastosuj"); auto-tworzenie kontenerów. To kolejny plaster (UI) — zatwierdzanie i tak idzie istniejącymi mutacjami.

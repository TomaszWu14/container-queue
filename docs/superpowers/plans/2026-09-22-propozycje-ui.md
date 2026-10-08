# Plaster: UI propozycji konsolidacji ("Zastosuj") — Plan

**Goal:** Pokazać w KoszykPage propozycje z `GET /api/consolidation/proposals` i pozwolić je zastosować (przypisać zamówienia propozycji do wybranego otwartego kontenera), na ISTNIEJĄCYCH API — bez zmian backendu.

## Constraints
- Tylko frontend (`frontend/src/pages/KoszykPage.tsx` + i18n). Zero zmian backendu.
- Reużyj: `GET /api/consolidation/proposals`, `GET /api/consolidation/containers?status=otwarty`, `PUT /api/containers/{cid}/orders/{poId}`.
- Design system aplikacji, Polish-first, i18n PL/EN/PT. `tsc --noEmit` czysto.

## Zadanie
- W KoszykPage dodaj sekcję "Propozycje konsolidacji": lista z `GET /proposals`. Każda propozycja: `supplier`, liczba/nazwy zamówień (`order_names`), `total_cbm` (pasek do 70).
- Przy każdej propozycji: `<select>` otwartego kontenera (z `GET /consolidation/containers?status=otwarty`) + przycisk **Zastosuj** → dla każdego `order id` w propozycji wywołaj `PUT /api/containers/{cid}/orders/{poId}` (sekwencyjnie); po sukcesie `load()` (odśwież koszyk+kontenery+propozycje). Błędy: istniejący wzorzec toast/errorMessage.
- Stan pusty: "Brak propozycji" gdy lista pusta.
- i18n: `proposalsSection`, `applyProposal`, `proposalOrders` (PL/EN/PT).

## Poza zakresem
Tworzenie NOWEGO kontenera z propozycji (wymaga backendu) — tu przypisujemy do istniejącego otwartego. DnD.

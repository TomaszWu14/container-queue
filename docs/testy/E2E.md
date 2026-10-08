# Testy E2E (Playwright) i strony bez testów

Stan: 2026-09-28 (TEST-007). Właściciel: właściciel aplikacji.

## Jak i kiedy biegną

| Gdzie | Kiedy | Jak |
|---|---|---|
| CI — `.github/workflows/e2e.yml` | **co noc** (01:41 UTC) na `main` + ręcznie: Actions → „E2E (Playwright)” → *Run workflow* | self-hosted runner, porty API/panelu `18000`/`15173` (na hoście runnera `:8000` zajmuje panel Coolify) |
| Lokalnie | przed zmianą ekranów logowania, kolejki, karty kontenera | `cd frontend && npx playwright install chromium && npm run e2e` (porty 8000/5173) |

- E2E **nie blokuje** merge'y (nie jest w REQUIRED w `automerge.yml`) — wolniejsze i bardziej kruche
  niż testy jednostkowe. Czerwony bieg nocny = regresja do sprawdzenia rano.
- Przy porażce bieg ma artefakt `e2e-raport-<run_id>`: raport HTML, zrzuty, wideo i trace (14 dni).
  Trace otwierasz: `npx playwright show-trace trace.zip`.
- Porty zmieniasz zmiennymi `E2E_API_PORT` / `E2E_WEB_PORT` (`frontend/e2e/ports.ts`).

### Wymaganie runnera (raz, admin hosta)
Job instaluje samą przeglądarkę (`npx playwright install chromium`, bez sudo). Biblioteki systemowe
Chromium doinstalowuje raz admin serwera runnera:

```bash
cd ~gha/actions-runner/_work/TIMPORYE/TIMPORYE/frontend   # albo dowolny katalog z node_modules
sudo npx playwright install-deps chromium
```

Objaw braku: pierwszy bieg nocny pada na starcie przeglądarki (`error while loading shared libraries`).

## Co pokrywa E2E (`frontend/e2e/`)
- `login.spec.ts` — logowanie (ekran `AuthPages`),
- `container-crud.spec.ts` — kontener na liście kolejki, edycja, walidacja ISO 6346,
- `scoping.spec.ts` — izolacja spółek (lista i karta kontenera innej spółki → 403),
- `visual/` — wzorce wizualne (tylko lokalnie, per system: `npm run e2e:visual`).

## Strony bez testów

Moduły `frontend/src/pages/*.tsx`, których żaden test vitest nie importuje wprost (import przez
komponent nadrzędny się nie liczy — lista jest zachowawcza). Odświeżanie:
`python scripts/frontend_untested_pages.py`. **63 moduły, 21 bez testu:**

| Moduł | Uwagi / pokrycie pośrednie |
|---|---|
| `AdminPage.tsx` | panel administracji |
| `AnalysisTab.tsx` | |
| `AuthPages.tsx` | logowanie — E2E `login.spec.ts`; reset hasła bez testu |
| `AvizoSendModal.tsx` | wysyłka awizacji do spedycji |
| `ClearQueueModal.tsx` | **operacja masowa** — priorytet (audyt TEST-007) |
| `ComplaintDetailPage.tsx` | |
| `ContainerSidePanels.tsx` | karta kontenera — częściowo E2E `container-crud.spec.ts` |
| `DriverPage.tsx` | **publiczny link kierowcy** — priorytet |
| `ForecastTab.tsx` | |
| `ForwardingPage.tsx` | |
| `FoundOrderModal.tsx` | |
| `FreightInvoicesPanel.tsx` | |
| `ImportErrors.tsx` | |
| `ImportModal.tsx` | **import Excela/SAP** — priorytet |
| `LandingPage.tsx` | |
| `ProfilePage.tsx` | |
| `QueueEmailModal.tsx` | |
| `SectionShell.tsx` | ramka sekcji (layout) |
| `StatsCharts.tsx` | |
| `SupplierPage.tsx` | |
| `WarehouseQueuePage.tsx` | |

Kolejność pisania testów (rekomendacja audytu): `AuthPages` (reset hasła), `DriverPage`,
`ClearQueueModal`, `ImportModal` — testy RTL (`*.dom.test.tsx`) jak dla istniejących modali.

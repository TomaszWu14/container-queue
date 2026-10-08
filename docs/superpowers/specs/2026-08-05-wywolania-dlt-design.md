# Wywołania-DLT — spec (Wersja 1, model per-produkt)

**Data:** 2026-08-05 (rev. 2 — po analizie realnego arkusza roboczego)
**Repo:** timporye (FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL, frontend React/Vite/TS)
**Status:** do zatwierdzenia (rev. 2)

## Cel

Moduł **Wywołania-DLT** odtwarza obecny arkusz decyzyjny „wywołanie z DLT": **per
produkt** zestawia stan w magazynie (ACME) i w DLT — w **paletach** — z
zapotrzebowaniem (dostawy wychodzące + zlecenia sprzedaży) i zużyciem, wylicza
sygnały (projekcja stanu, dni zapasu, flaga „do wywołania pilnie") oraz **sugerowaną
liczbę palet do wywołania**, którą użytkownik może nadpisać. Zatwierdzone pozycje
tworzą wywołanie do firmy DLT, eksportowane do xlsx i wysyłane mailem.

> Zmiana względem rev. 1: wywołanie jest **per produkt (ilość palet)**, nie per
> pojedyncza paleta/HU. Rev. 1 (ręczny wybór HU) była błędnym modelem — realny
> proces pokazał załączony arkusz roboczy.

## Źródła danych (Power BI / SAP BW) — potwierdzone

Wszystkie cztery przez Power BI `executeQueries` (DAX). Nazwy kolumn normalizowane
(lowercase, bez akcentów, `_`).

1. **Stan** (`stock`, ~32 tys. wierszy, poziom palety/HU) — z lokalizacją. Kolumny m.in.:
   `miejsce_skladowania`, `produkt`, `krotki_opis_produktu`, `ilosc`,
   `podst_jedn_miary`, `partia`, `glowna_hu`, `rodzaj_zapasow`. **Lokalizacja
   rozróżnia magazyn ACME vs DLT** (mapowanie konfigurowalne — patrz niżej).
2. **Dostawy wychodzące** (`vbba`/ZL) — `dokument`, `produkt`, `ilosc`,
   `status_pobrania`. Otwarte statusy konfigurowalne (`Nie rozpoczęte,Częściowo
   zakończone`).
3. **Zlecenia sprzedaży** (`vbbe+likp`) — `materiał`/`produkt`, `ilosc_otwarta`,
   potwierdzone/niepotwierdzone (kolumny `Otw`/`Potw`/`Niestandardowe`).
4. **Zużycie** (`Zużycie+mbew`) — `produkt`, zużycie miesięczne/dzienne per produkt.

**Nie z Power BI:**
- **PAZ** (ile sztuk na paletę per produkt) — **słownik w naszej bazie** (`ProductPaz`),
  CRUD + import xlsx/csv. W SAP jest niekompletny („Brak_PAZ").
- **Wywołane-przywiezione** — **nasza historia wywołań** (`PalletCall` w statusie
  sent/confirmed), nie zewnętrzne źródło.

## Logika per produkt (odtworzenie arkusza `W`)

Dla każdego produktu (klucz = `produkt`, konfigurowalny `POWERBI_MERGE_KEY`):

| Sygnał | Wyliczenie |
|---|---|
| `stan_mag_szt` / `stan_dlt_szt` | suma `ilosc` ze `stock` wg lokalizacji (magazyn vs DLT) |
| `stan_mag_pal` / `stan_dlt_pal` | `stan_*_szt / PAZ[produkt]` (gdy brak PAZ → `null`, oznaczone „Brak_PAZ") |
| `dostawy_pal` | suma otwartych dostaw (`ZL`) / PAZ |
| `zlec_niepotw_pal`, `zlec_potw_pal` | suma z `vbbe+likp` (niepotw./potw.) / PAZ |
| `wywolane_pal` | suma palet z naszych wywołań (sent/confirmed) danego produktu, jeszcze nie „przywiezionych” |
| `projekcja_mag_pal` | `stan_mag_pal − (dostawy_pal + zlec_niepotw_pal)` |
| `dni_zapasu` | `stan_mag_pal / zuzycie_dzienne_pal` |
| `pilne` (flaga) | `projekcja_mag_pal < próg_pilny` (domyślnie 2) lub projekcja < 0 |
| `sugestia_pal` (IL do wywołania) | `clamp(ceil(zuzycie_dzienne_pal*target_days + dostawy_pal + zlec_niepotw_pal − stan_mag_pal − wywolane_pal), 0, stan_dlt_pal)` |

`target_days` i `próg_pilny` — konfigurowalne (**pokrętła kalibracyjne**; realny
proces dostroi wartości). `sugestia_pal` jest tylko propozycją — użytkownik podaje
własną `ilosc_pal` przy tworzeniu wywołania.

> Uwaga o mnożeniu wierszy: każde źródło agregujemy do `dict[produkt -> wartość]`
> **przed** złączeniem (żaden row-join → brak kartezjanu). Agregacja to szew
> rozszerzalności — kolejne źródła zapotrzebowania dokładamy do tych dictów.

### Mapowanie lokalizacji magazyn vs DLT
Konfigurowalne: `POWERBI_DLT_LOCATIONS` (lista wartości/prefiksów `miejsce_skladowania`
traktowanych jako DLT); reszta = magazyn ACME. Pole lokalizacji też konfigurowalne
(`POWERBI_LOCATION_FIELD`, domyślnie `miejsce_skladowania`). Dostosujemy po podaniu
realnych kodów.

## Architektura (moduły `backend/app/`)

- **`powerbi.py`** — integracja: `fetch_table(dataset, table)`, kaskada auth
  (token → service principal → device-code z cache MSAL w `PowerBIToken`), TLS
  konfigurowalny, leniwe importy, `is_configured()`/`has_delegated_session()`,
  provider-gating `off/mock/real` (mock = fixture z realnymi kolumnami).
- **`pallets_analysis.py`** — czyste funkcje: agregacja każdego źródła per produkt,
  przeliczenie przez PAZ, złożenie wiersza produktu z sygnałami i `sugestia_pal`.
- **`pallets_cache.py`** — jednorządkowy cache policzonej analizy (JSON + `fetched_at`),
  TTL `POWERBI_CACHE_TTL_MIN`; re-fetch 4 kostek + re-compute po wygaśnięciu.
- **`pallets_export.py`** — `build_xlsx(call)` (openpyxl) + rozszerzenie
  `notifications.send_html_email(attachments=...)`.
- **`routers/pallets.py`** — `/api/pallet-calls`:
  - `GET /analysis` — widok per produkt (paginacja, filtr: szukaj, „tylko pilne",
    „tylko z brakiem PAZ”), plus `discrepancies` (produkty bez PAZ / bez stanu).
  - `POST ""` — utwórz wywołanie z listy `{produkt, ilosc_pal, data_dostawy}`.
  - `GET ""` / `GET /{id}` — lista i historia (scoping per firma).
  - `PATCH /{id}` — edycja szkicu.
  - `POST /{id}/send|confirm|cancel` — statusy; `send` = xlsx + mail do DLT.
- **`routers/paz.py`** — CRUD słownika PAZ: `GET/POST/PUT/DELETE /api/paz`
  + `POST /api/paz/import` (xlsx/csv, kolumny `produkt`,`sztuk_na_palete`).
- **`scripts/powerbi_connect.py`** — jednorazowe device-code logowanie (delegated).

## Model danych (`models.py` + migracja Alembic)

- `PowerBIToken` — cache MSAL (`id`, `cache`, `updated_at`).
- `PalletStockCache` — cache analizy (`id`, `fetched_at`, `payload` JSON,
  `discrepancies` JSON).
- `ProductPaz` — słownik PAZ: `id`, `produkt` (unique), `sztuk_na_palete` (Numeric),
  `updated_at`.
- `PalletCall` — nagłówek: `id`, `company_id` (index, scoping), `number` (unikalny
  per firma), `status` (enum `draft|sent|confirmed|cancelled`), `needed_by`, `notes`,
  `created_by`, `created_at`, `sent_at`, `lines`.
- `PalletCallLine` — pozycja **per produkt**: `id`, `pallet_call_id`, `produkt`,
  `krotki_opis`, `ilosc_pal` (Numeric — liczba palet do wywołania), `data_dostawy`
  (Date, null), `note`.

Enum `PalletCallStatus(str, enum.Enum)`.

## Konfiguracja (`config.py`)

`powerbi_provider` (off/mock/real), `powerbi_workspace_id`, `powerbi_dataset_stock/table`,
`powerbi_dataset_vbba/table`, `powerbi_dataset_orders/table`, `powerbi_dataset_usage/table`,
`powerbi_merge_key` (`produkt`), `vbba_open_statuses`, `powerbi_location_field`,
`powerbi_dlt_locations`, `pallet_target_days` (kalibracja), `pallet_urgent_threshold`
(domyślnie 2), auth (`powerbi_tenant_id/client_id/client_secret/access_token`),
TLS (`powerbi_ca_bundle`, `powerbi_ssl_verify`), `powerbi_cache_ttl_min` (15),
`dlt_email`. Zero sekretów w repo; `.env.example` uzupełniony.

## Frontend (`frontend/src/`)

- **`PalletCalls.tsx`** — widok analizy per produkt (tabela z sygnałami: stan MAG/DLT
  w paletach, dostawy, zlecenia, projekcja, dni zapasu, flaga pilne, sugestia),
  filtry/paginacja, edytowalna kolumna „ilość do wywołania" (prefill = sugestia),
  „Utwórz wywołanie" z zaznaczonych, historia wywołań ze statusami i „Wyślij do DLT".
- **`Paz.tsx`** — prosty CRUD słownika PAZ + import pliku.
- Wpięcie w routing/menu (zakładki „Wywołania-DLT”, „PAZ”), styl spójny z repo.

## Obsługa błędów
- Power BI niedostępny/niekonfigurowany → 503 z czytelnym komunikatem; przy dostępnym
  świeżym cache — serwuj cache.
- Brak PAZ dla produktu → palety `null`, wiersz oznaczony „Brak_PAZ” w `discrepancies`;
  nie blokuje reszty.
- Błąd SMTP przy `send` → wywołanie zostaje, błąd logowany, możliwość ponowienia.

## Testy (`backend/tests/`)
- `pallets_analysis`: agregacja per źródło, przeliczenie PAZ (w tym brak PAZ),
  projekcja, dni zapasu, flaga pilne, `sugestia_pal` (w tym clamp do stanu DLT),
  brak kartezjanu.
- `powerbi`: mock provider, defensywne parsowanie.
- `pallets_cache`: TTL, re-compute.
- PAZ CRUD + import.
- Wywołanie: utworzenie z pozycji, scoping per firma, przejścia statusów, `send`
  (mail zmockowany), `build_xlsx`.

## Świadome skróty (ponytail)
- Cache = jeden wiersz JSON policzonej analizy (nie per-kostka) — wystarcza dla ~6k
  produktów; rozbicie później jeśli trzeba.
- `sugestia_pal` = prosty wzór z dwoma pokrętłami (`target_days`, `urgent_threshold`)
  — **wymaga dostrojenia do realnego procesu** (kalibracja, nie „gotowa prawda”).
- Mapowanie lokalizacji i dokładne nazwy kolumn/datasetów — konfigurowalne, do
  uzupełnienia realnymi wartościami przy wdrożeniu.

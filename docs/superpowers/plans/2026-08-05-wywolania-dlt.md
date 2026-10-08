# Wywołania-DLT Implementation Plan (rev.2 — model per-produkt)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans / subagent-driven-development. Steps use `- [ ]`.

**Goal:** Panel wywołań palet do DLT — per produkt zestawia stan MAG/DLT (w paletach), zapotrzebowanie i zużycie, wylicza sygnały + sugestię palet do wywołania (ręcznie korygowalną), tworzy wywołanie i wysyła xlsx mailem.

**Architecture:** 4 kostki Power BI (stan+lokalizacja, dostawy, zlecenia, zużycie) → czyste agregacje per produkt (`pallets_analysis.py`) z przeliczeniem przez słownik PAZ (nasza baza) → cache TTL → router FastAPI. Szczegóły: `../specs/2026-08-05-wywolania-dlt-design.md`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, pydantic-settings, msal (NOWA), httpx+openpyxl (w repo), React/Vite/TS.

## Global Constraints
- Routery w `backend/app/routers/`, prefix `/api`, włączane w `main.py`.
- Modele w `models.py` (`Base` z `.database`, `utcnow()`); izolacja per firma przez `deps.py`.
- Zero sekretów w repo; konfiguracja w `config.py` + `.env.example`. Nowa zależność tylko `msal`; HTTP na `httpx`.
- Kolumny PBI normalizowane: lowercase, bez akcentów, `_`.
- TDD: test → fail → impl → pass → commit. Testy w `backend/tests/`, fixture `client`/`admin_headers`.

## Zadania (kolejność zależności)
1. **Config + `msal` w requirements + `.env.example`** — pola z sekcji Konfiguracja specu; property `vbba_open_statuses_set`, `powerbi_dlt_locations_set`.
2. **Modele + enum** — `PowerBIToken`, `PalletStockCache`, `ProductPaz`, `PalletCall`, `PalletCallLine(produkt, krotki_opis, ilosc_pal, data_dostawy, note)`, `PalletCallStatus`.
3. **Migracja Alembic** — 5 tabel, index `company_id`, unique `(company_id, number)`, unique `ProductPaz.produkt`.
4. **`powerbi.py`** — `normalize_header`, `parse_execute_queries` (defensywne), `fetch_table` (off/mock/real), kaskada auth + cache MSAL, TLS. Fixture mock z 4 źródłami.
5. **`pallets_analysis.py`** — agregacje per produkt + PAZ + sygnały + sugestia (patrz kod niżej).
6. **`pallets_cache.py`** — `get_analysis(db, force)` z TTL; pobiera 4 kostki + PAZ + historię wywołań, liczy, cache’uje.
7. **`pallets_export.py`** + `send_html_email(attachments=...)` — xlsx `{produkt, ilość palet, data dostawy}`.
8. **Schematy Pydantic** — `AnalysisRow`, `AnalysisPage`, `PazIn/Out`, `PalletCallLineIn/Out`, `PalletCallCreate/Update/Out`.
9. **`routers/pallets.py`** — `GET /analysis`, `POST/GET/PATCH`, `send/confirm/cancel`; wpiąć w `main.py`.
10. **`routers/paz.py`** — CRUD + `POST /import` (xlsx/csv); wpiąć w `main.py`.
11. **CLI `scripts/powerbi_connect.py`** — device-code.
12. **Frontend** — `PalletCalls.tsx` (analiza per produkt, edytowalna ilość=prefill sugestia, historia), `Paz.tsx` (CRUD+import), routing.

## Kluczowy kod — Task 5 (`pallets_analysis.py`)

```python
# backend/app/pallets_analysis.py
"""Analiza per produkt: stan MAG/DLT (palety) vs zapotrzebowanie i zużycie.
Każde źródło agregowane do dict[produkt->wartość] PRZED złożeniem (brak kartezjanu).
"""
from __future__ import annotations
import math

def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0

def _is_dlt(row: dict, field: str, dlt_values: set[str]) -> bool:
    val = str(row.get(field, ""))
    return any(val == v or val.startswith(v) for v in dlt_values)

def sum_by_product(rows: list[dict], key: str, qty_field: str,
                   predicate=None) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in rows:
        if predicate and not predicate(r):
            continue
        k = r.get(key)
        if k is None:
            continue
        out[k] = out.get(k, 0.0) + _num(r.get(qty_field))
    return out

def to_pallets(qty: float, paz: float | None) -> float | None:
    if not paz:
        return None
    return qty / paz

def build_rows(stock, vbba, orders, usage, paz_map, called_map, *,
               key, location_field, dlt_values, open_statuses,
               target_days, urgent_threshold):
    """Zwraca (rows, discrepancies). rows: list[dict] sygnałów per produkt."""
    mag_szt = sum_by_product(stock, key, "ilosc",
                             lambda r: not _is_dlt(r, location_field, dlt_values))
    dlt_szt = sum_by_product(stock, key, "ilosc",
                             lambda r: _is_dlt(r, location_field, dlt_values))
    dostawy_szt = sum_by_product(vbba, key, "ilosc",
                                 lambda r: r.get("status_pobrania") in open_statuses)
    zlec_niepotw_szt = sum_by_product(orders, key, "niepotwierdzone")
    zlec_potw_szt = sum_by_product(orders, key, "potw")
    usage_daily = {u.get(key): _num(u.get("zuzycie_dzienne")) for u in usage}

    produkty = set(mag_szt) | set(dlt_szt) | set(dostawy_szt) | set(zlec_niepotw_szt)
    rows, disc = [], []
    for p in sorted(produkty):
        paz = paz_map.get(p)
        mag_pal = to_pallets(mag_szt.get(p, 0), paz)
        dlt_pal = to_pallets(dlt_szt.get(p, 0), paz)
        dost_pal = to_pallets(dostawy_szt.get(p, 0), paz) or 0
        zn_pal = to_pallets(zlec_niepotw_szt.get(p, 0), paz) or 0
        wywolane = called_map.get(p, 0.0)
        zuzycie_pal = to_pallets(usage_daily.get(p, 0), paz)
        projekcja = None if mag_pal is None else mag_pal - (dost_pal + zn_pal)
        dni = (mag_pal / zuzycie_pal) if (mag_pal is not None and zuzycie_pal) else None
        pilne = projekcja is not None and (projekcja < urgent_threshold or projekcja < 0)
        if paz is None:
            sugestia = None
            disc.append({"produkt": p, "powod": "brak_paz"})
        else:
            need = (zuzycie_pal or 0) * target_days + dost_pal + zn_pal
            raw = math.ceil(need - (mag_pal or 0) - wywolane)
            sugestia = max(0, min(raw, math.floor(dlt_pal or 0)))
        rows.append({
            "produkt": p, "stan_mag_pal": mag_pal, "stan_dlt_pal": dlt_pal,
            "dostawy_pal": dost_pal, "zlec_niepotw_pal": zn_pal,
            "wywolane_pal": wywolane, "projekcja_mag_pal": projekcja,
            "dni_zapasu": dni, "pilne": pilne, "sugestia_pal": sugestia,
        })
    return rows, disc
```

Test (`backend/tests/test_pallets_analysis.py`): dwa produkty, jeden z PAZ i jeden bez; assert palety, projekcja, flaga pilne, clamp sugestii do stanu DLT, wpis „brak_paz” w discrepancies.

## Reszta zadań
Struktura kroków (test→fail→impl→pass→commit) i wzorce (router prefix `/api`, `deps` `Editors/Viewer`, `resolve_company_id`, `send_html_email`) jak w repo — patrz istniejące `routers/quotes.py`, `notifications.py`, `conftest.py`. Nazwy datasetów/kolumn i mapowanie lokalizacji: konfigurowalne, uzupełniane realnymi wartościami.

## Self-Review
Pokrycie specu: źródła→Task4/6, analiza per produkt→Task5, PAZ→Task2/10, cache→Task6, wywołania+eksport→Task2/7/9, UI→Task12. Bez placeholderów w kodzie Task5. Typy spójne (`build_rows`, `get_analysis`, `sugestia_pal`).

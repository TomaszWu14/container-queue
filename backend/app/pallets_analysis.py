"""Analiza per produkt: stan MAG/DLT (palety) vs zapotrzebowanie i zużycie.

Każde źródło agregowane do dict[produkt -> wartość] PRZED złożeniem (brak
kartezjanu). Agregacja to szew rozszerzalności — kolejne źródła zapotrzebowania
dokłada się do tych dictów.
"""
from __future__ import annotations

import math

from .tabular import to_float


def _num(v) -> float:
    return to_float(v) or 0.0   # brak/nie-liczba liczy się jako 0 w sumach


def _is_dlt(row: dict, field: str, dlt_values: set[str]) -> bool:
    if not dlt_values:
        return False
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


PALLET_CAP = 132          # 4 auta × 33 miejsca paletowe


def daily_usage_map(usage, key, window_days=30):
    """Zużycie dzienne per produkt + flaga trybu.

    Rozszerzony dataset PBI: dzienne rozchody (kolumna daty + 'ilosc') -> średnia
    krocząca z okna `window_days`. Degradacja (feature-detect): brak kolumny daty ->
    stara kolumna 'zuzycie_dzienne' wprost."""
    has_daily = any(("data" in u or "date" in u) and "ilosc" in u for u in usage)
    if not has_daily:
        return {u.get(key): _num(u.get("zuzycie_dzienne")) for u in usage}, False
    totals = sum_by_product(usage, key, "ilosc")
    return {p: v / window_days for p, v in totals.items()}, True


def dlt_hu_map(stock, key, location_field, dlt_values, hu_field="glowna_hu"):
    """Stany DLT per HU: dict[produkt -> list[{hu, ilosc}]] + flaga dostępności kolumny."""
    has_hu = any(hu_field in r for r in stock)
    if not has_hu:
        return {}, False
    out: dict[str, list[dict]] = {}
    for r in stock:
        if not _is_dlt(r, location_field, dlt_values):
            continue
        p, hu = r.get(key), r.get(hu_field)
        if p is None or not hu:
            continue
        out.setdefault(p, []).append({"hu": str(hu), "ilosc": _num(r.get("ilosc"))})
    return out, True


def build_rows(stock, vbba, orders, usage, paz_map, called_map, *,
               key, location_field, dlt_values, open_statuses,
               target_days, urgent_threshold,
               orders_confirmed_field="potw", orders_unconfirmed_field="niestandardowe",
               demand_forecast=None, horizon_days=14,
               target_days_map=None, usage_window_days=30):
    """Zwraca (rows, discrepancies, features). rows: list[dict] sygnałów per produkt."""
    target_days_map = target_days_map or {}
    mag_szt = sum_by_product(stock, key, "ilosc",
                             lambda r: not _is_dlt(r, location_field, dlt_values))
    dlt_szt = sum_by_product(stock, key, "ilosc",
                             lambda r: _is_dlt(r, location_field, dlt_values))
    dostawy_szt = sum_by_product(vbba, key, "ilosc",
                                 lambda r: r.get("status_pobrania") in open_statuses)
    zlec_niepotw_szt = sum_by_product(orders, key, orders_unconfirmed_field)
    zlec_potw_szt = sum_by_product(orders, key, orders_confirmed_field)
    usage_daily, has_daily_usage = daily_usage_map(usage, key, usage_window_days)
    hu_map, has_hu = dlt_hu_map(stock, key, location_field, dlt_values)

    produkty = set(mag_szt) | set(dlt_szt) | set(dostawy_szt) | set(zlec_niepotw_szt)
    rows, disc = [], []
    for p in sorted(produkty):
        paz = paz_map.get(p)
        mag_pal = to_pallets(mag_szt.get(p, 0), paz)
        dlt_pal = to_pallets(dlt_szt.get(p, 0), paz)
        dost_pal = to_pallets(dostawy_szt.get(p, 0), paz) or 0
        zn_pal = to_pallets(zlec_niepotw_szt.get(p, 0), paz) or 0
        zp_pal = to_pallets(zlec_potw_szt.get(p, 0), paz) or 0
        wywolane = _num(called_map.get(p, 0.0))
        has_forecast = bool(demand_forecast and p in demand_forecast)
        if has_forecast:
            fc_pal = to_pallets(demand_forecast[p], paz)
            zuzycie_pal = None if fc_pal is None else fc_pal / horizon_days
        else:
            fc_pal = None
            zuzycie_pal = to_pallets(usage_daily.get(p, 0), paz)
        projekcja = None if mag_pal is None else mag_pal - (dost_pal + zn_pal)
        dni = (mag_pal / zuzycie_pal) if (mag_pal is not None and zuzycie_pal) else None
        pilne = projekcja is not None and (projekcja < urgent_threshold or projekcja < 0)
        cel_dni = int(target_days_map.get(p, target_days))
        if paz is None:
            sugestia = None
            disc.append({"produkt": p, "powod": "brak_paz"})
        else:
            base = fc_pal if has_forecast else (zuzycie_pal or 0) * cel_dni
            need = (base or 0) + dost_pal + zn_pal
            raw = math.ceil(need - (mag_pal or 0) - wywolane)
            # przycięcie do stanu DLT i do 132 miejsc (4 auta × 33)
            sugestia = max(0, min(raw, math.floor(dlt_pal or 0), PALLET_CAP))
        rows.append({
            "produkt": p, "stan_mag_pal": mag_pal, "stan_dlt_pal": dlt_pal,
            "stan_mag_szt": mag_szt.get(p, 0), "stan_dlt_szt": dlt_szt.get(p, 0),
            "zuzycie_szt_dzien": usage_daily.get(p) or 0, "cel_dni": cel_dni,
            "dostawy_pal": dost_pal, "zlec_niepotw_pal": zn_pal, "zlec_potw_pal": zp_pal,
            "wywolane_pal": wywolane, "projekcja_mag_pal": projekcja,
            "dni_zapasu": dni, "pilne": pilne, "sugestia_pal": sugestia,
            "hu": hu_map.get(p, []),
        })
    features = {"hu": has_hu, "daily_usage": has_daily_usage}
    return rows, disc, features

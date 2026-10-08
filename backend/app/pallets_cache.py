"""Jednorządkowy cache policzonej analizy per produkt. Świeży w oknie TTL -> serwuj
z DB, inaczej pobierz 4 kostki + PAZ + historię wywołań, policz, zapisz.
ponytail: jeden wiersz JSON wystarcza dla ~6k produktów.
"""
from __future__ import annotations

import datetime
import json
import threading

from sqlalchemy import select

from . import powerbi
from .config import settings
from .models import (
    PalletCall,
    PalletCallLine,
    PalletCallStatus,
    PalletStockCache,
    ProductPaz,
    utcnow,
)
from .pallets_analysis import build_rows


# wartość lokalizacji oznaczająca ręcznie zaimportowane stany jako DLT
DLT_SENTINEL = "DLT"

# jedno odświeżanie naraz (4 zapytania PBI × do 120 s) — reszta dostaje ostatni wynik z cache
# ponytail: blokada per proces; przy kilku workerach każdy może odświeżyć raz (wiersz i tak jeden)
_refresh_lock = threading.Lock()


class AnalysisRefreshInProgress(powerbi.PowerBINotConfigured):
    """Brak cache, a odświeżanie już trwa — wołający traktują to jak chwilowy brak PBI (503)."""


def _imported_dlt_stock(db) -> list[dict]:
    """Zaimportowane stany DLT jako wiersze `stock` dla build_rows (oznaczone jako DLT)."""
    from .models import DltStock
    key = settings.powerbi_merge_key
    loc = settings.powerbi_location_field
    out: list[dict] = []
    for s in db.query(DltStock).all():
        row = {key: s.produkt, "ilosc": float(s.ilosc), loc: DLT_SENTINEL}
        if s.hu:
            row["glowna_hu"] = s.hu
        out.append(row)
    return out


def _fresh(row: PalletStockCache) -> bool:
    ttl = settings.powerbi_cache_ttl_min
    if ttl <= 0:
        return False
    return (utcnow() - row.fetched_at) < datetime.timedelta(minutes=ttl)


def _paz_map(db) -> dict[str, float]:
    """Sztuk na paletę per produkt: MARM (jednostka PAL) jako baza, słownik PAZ nadpisuje."""
    from .models import MaterialUnit
    out: dict[str, float] = {}
    for mu in db.query(MaterialUnit).filter(MaterialUnit.unit == "PAL").all():
        if mu.numerator and mu.denominator:
            out[mu.material_no] = float(mu.numerator) / float(mu.denominator)
    for p in db.query(ProductPaz).all():
        out[p.produkt] = float(p.sztuk_na_palete)
    return out


def _target_map(db) -> dict[str, int]:
    from .models import MaterialStockTarget
    return {t.material_no: int(t.days) for t in db.query(MaterialStockTarget).all()}


def invalidate(db) -> None:
    """Kasuje cache analizy (np. po zmianie celu dni) — następny odczyt przeliczy."""
    db.query(PalletStockCache).delete()
    db.commit()


def _called_map(db) -> dict[str, float]:
    """Palety już wywołane (sent/confirmed), jeszcze nieodjęte ze stanu."""
    stmt = (select(PalletCallLine.produkt, PalletCallLine.ilosc_pal)
            .join(PalletCall, PalletCallLine.pallet_call_id == PalletCall.id)
            .where(PalletCall.status.in_(
                (PalletCallStatus.sent, PalletCallStatus.confirmed))))
    out: dict[str, float] = {}
    for produkt, ilosc in db.execute(stmt):
        out[produkt] = out.get(produkt, 0.0) + float(ilosc or 0)
    return out


def _cached(row: PalletStockCache):
    cached = json.loads(row.payload)
    if isinstance(cached, dict):        # nowy format: {"rows": [...], "features": {...}}
        return (cached.get("rows", []), json.loads(row.discrepancies),
                row.fetched_at, cached.get("features", {}))
    return cached, json.loads(row.discrepancies), row.fetched_at, {}


def get_analysis(db, force: bool = False):
    """Zwraca (rows, discrepancies, fetched_at, features). Gdy inne żądanie właśnie odświeża —
    ostatni wynik z cache (nawet nieświeży), a bez cache AnalysisRefreshInProgress."""
    row = db.query(PalletStockCache).order_by(PalletStockCache.id).first()
    if row and not force and _fresh(row):
        return _cached(row)
    if not _refresh_lock.acquire(blocking=False):
        if row is not None:
            return _cached(row)
        raise AnalysisRefreshInProgress("Odświeżanie analizy w toku — spróbuj za chwilę.")
    try:
        db.commit()   # koniec transakcji odczytu — połączenie wraca do puli na czas HTTP
        return _refresh(db)
    finally:
        _refresh_lock.release()


def _refresh(db):
    def _fetch(dataset, table):
        _, rows = powerbi.fetch_table(dataset, table, db=db)
        return powerbi.apply_column_map(rows)

    dlt_values = settings.powerbi_dlt_locations_set
    try:
        stock = _fetch(settings.powerbi_dataset_stock, settings.powerbi_table_stock)
        vbba = _fetch(settings.powerbi_dataset_vbba, settings.powerbi_table_vbba)
        orders = _fetch(settings.powerbi_dataset_orders, settings.powerbi_table_orders)
        usage = _fetch(settings.powerbi_dataset_usage, settings.powerbi_table_usage)
    except powerbi.PowerBINotConfigured:
        # PBI wyłączone: analityka działa wyłącznie na ręcznym imporcie stanów DLT
        imported = _imported_dlt_stock(db)
        if not imported:
            raise
        stock, vbba, orders, usage = imported, [], [], []
        dlt_values = dlt_values | {DLT_SENTINEL}
    else:
        # PBI działa, ale bez stanów DLT → dołóż ręczny import (fallback per-źródło)
        from .pallets_analysis import _is_dlt
        loc = settings.powerbi_location_field
        if not any(_is_dlt(r, loc, dlt_values) for r in stock):
            imported = _imported_dlt_stock(db)
            if imported:
                stock = stock + imported
                dlt_values = dlt_values | {DLT_SENTINEL}
    rows, disc, features = build_rows(
        stock, vbba, orders, usage, _paz_map(db), _called_map(db),
        key=settings.powerbi_merge_key,
        location_field=settings.powerbi_location_field,
        dlt_values=dlt_values,
        open_statuses=settings.vbba_open_statuses_set,
        target_days=settings.pallet_target_days,
        urgent_threshold=settings.pallet_urgent_threshold,
        orders_confirmed_field=settings.powerbi_orders_confirmed_field,
        orders_unconfirmed_field=settings.powerbi_orders_unconfirmed_field,
        horizon_days=settings.pallet_forecast_horizon_days,
        target_days_map=_target_map(db))
    now = utcnow()
    payload = json.dumps({"rows": rows, "features": features}, default=str)
    discj = json.dumps(disc, default=str)
    # upsert jednego wiersza; duplikaty (dawne równoległe chybienia, inny worker) sprzątane
    existing = db.query(PalletStockCache).order_by(PalletStockCache.id).all()
    for extra in existing[1:]:
        db.delete(extra)
    if not existing:
        db.add(PalletStockCache(payload=payload, discrepancies=discj, fetched_at=now))
    else:
        row = existing[0]
        row.payload, row.discrepancies, row.fetched_at = payload, discj, now
    db.commit()
    return rows, disc, now, features

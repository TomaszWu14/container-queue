import threading

import pytest
from sqlalchemy.orm import Session

from app import models, pallets_cache
from app.database import Base, engine


def _clean(db):
    db.query(models.PalletCallLine).delete()
    db.query(models.PalletCall).delete()
    db.query(models.PalletStockCache).delete()
    db.query(models.ProductPaz).delete()
    db.commit()


def _mock_sources(monkeypatch):
    s = pallets_cache.settings
    monkeypatch.setattr(s, "powerbi_provider", "mock")
    monkeypatch.setattr(s, "powerbi_dlt_locations", "3DLT")
    monkeypatch.setattr(s, "powerbi_cache_ttl_min", 15)
    # nazwy tabel kierują mock do właściwego źródła
    monkeypatch.setattr(s, "powerbi_table_stock", "stock")
    monkeypatch.setattr(s, "powerbi_table_vbba", "vbba")
    monkeypatch.setattr(s, "powerbi_table_orders", "vbbe")
    monkeypatch.setattr(s, "powerbi_table_usage", "zuzycie")


def test_get_analysis_mock(monkeypatch):
    _mock_sources(monkeypatch)
    Base.metadata.create_all(bind=engine)
    with Session(bind=engine) as db:
        _clean(db)
        db.add(models.ProductPaz(produkt="DEMO-SKU-020", sztuk_na_palete=100))
        db.commit()
        rows, disc, _, _ = pallets_cache.get_analysis(db, force=True)
        r = next(x for x in rows if x["produkt"] == "DEMO-SKU-020")
        assert r["stan_mag_pal"] == 10 and r["stan_dlt_pal"] == 20
        assert r["sugestia_pal"] == 10
        # DEMO-SKU-079 bez PAZ -> discrepancy
        assert any(d["powod"] == "brak_paz" for d in disc)


def test_cache_served_when_fresh(monkeypatch):
    _mock_sources(monkeypatch)
    Base.metadata.create_all(bind=engine)
    with Session(bind=engine) as db:
        _clean(db)
        pallets_cache.get_analysis(db, force=True)
        # bez force i świeży cache -> ten sam fetched_at
        rows1, _, ts1, _ = pallets_cache.get_analysis(db)
        rows2, _, ts2, _ = pallets_cache.get_analysis(db)
        assert ts1 == ts2


def test_concurrent_miss_fetches_once_and_serves_stale(monkeypatch):
    """Dwa równoległe chybienia = jedno pobranie z PBI (4 zapytania); drugie żądanie bez cache
    dostaje „odświeżanie w toku” (503), a z nieświeżym cache — ostatni wynik bez czekania."""
    _mock_sources(monkeypatch)
    Base.metadata.create_all(bind=engine)
    with Session(bind=engine) as db:
        _clean(db)
    real = pallets_cache.powerbi.fetch_table
    started, release = threading.Event(), threading.Event()
    calls = []

    def slow(dataset, table, db=None):
        calls.append(table)
        started.set()
        release.wait(5)
        return real(dataset, table, db=db)

    monkeypatch.setattr(pallets_cache.powerbi, "fetch_table", slow)
    result = {}

    def first():
        with Session(bind=engine) as db:
            result["rows"] = pallets_cache.get_analysis(db)[0]

    worker = threading.Thread(target=first)
    worker.start()
    assert started.wait(5)
    with Session(bind=engine) as db, pytest.raises(pallets_cache.AnalysisRefreshInProgress):
        pallets_cache.get_analysis(db)
    release.set()
    worker.join(5)
    assert len(calls) == 4 and result["rows"]

    monkeypatch.setattr(pallets_cache.settings, "powerbi_cache_ttl_min", 0)   # cache nieświeży
    assert pallets_cache._refresh_lock.acquire(blocking=False)              # „inne żądanie”
    try:
        with Session(bind=engine) as db:
            assert pallets_cache.get_analysis(db, force=True)[0] == result["rows"]
    finally:
        pallets_cache._refresh_lock.release()
    assert len(calls) == 4


def test_refresh_dedupes_cache_rows(monkeypatch):
    _mock_sources(monkeypatch)
    Base.metadata.create_all(bind=engine)
    with Session(bind=engine) as db:
        _clean(db)
        db.add_all([models.PalletStockCache(), models.PalletStockCache()])
        db.commit()
        pallets_cache.get_analysis(db, force=True)
        assert db.query(models.PalletStockCache).count() == 1

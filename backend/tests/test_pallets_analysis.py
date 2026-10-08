from app.pallets_analysis import build_rows
from tests.fixtures import pallets_mock as m

OPEN = {"Nie rozpoczęte", "Częściowo zakończone"}


def _rows(paz_map):
    return build_rows(
        m.STOCK_ROWS, m.VBBA_ROWS, m.ORDERS_ROWS, m.USAGE_ROWS,
        paz_map, called_map={}, key="produkt",
        location_field="miejsce_skladowania", dlt_values={"3DLT"},
        open_statuses=OPEN, target_days=14, urgent_threshold=2.0)


def test_signals_with_paz():
    rows, disc, _ = _rows({"DEMO-SKU-020": 100})
    r = next(x for x in rows if x["produkt"] == "DEMO-SKU-020")
    assert r["stan_mag_pal"] == 10           # 1000/100 (magazyn)
    assert r["stan_dlt_pal"] == 20           # 2000/100 (DLT)
    assert r["dostawy_pal"] == 4             # tylko 'Nie rozpoczęte' 400/100
    assert r["zlec_niepotw_pal"] == 2        # 200/100
    assert r["projekcja_mag_pal"] == 4       # 10 - (4+2)
    assert r["dni_zapasu"] == 10             # 10 / 1
    assert r["pilne"] is False
    assert r["sugestia_pal"] == 10           # 1*14 + 4 + 2 - 10 = 10, clamp<=20


def test_suggestion_capped_by_dlt_stock():
    # duże zapotrzebowanie, mały stan DLT -> sugestia ograniczona stanem DLT
    rows, _, _ = _rows({"DEMO-SKU-020": 100})
    r = next(x for x in rows if x["produkt"] == "DEMO-SKU-020")
    assert r["sugestia_pal"] <= r["stan_dlt_pal"]


def test_missing_paz_flags_discrepancy():
    rows, disc, _ = _rows({"DEMO-SKU-020": 100})   # DEMO-SKU-079 bez PAZ
    st = next(x for x in rows if x["produkt"] == "DEMO-SKU-079")
    assert st["stan_mag_pal"] is None and st["sugestia_pal"] is None
    assert any(d["produkt"] == "DEMO-SKU-079" and d["powod"] == "brak_paz"
               for d in disc)


def test_orders_confirmed_and_unconfirmed():
    rows, _, _ = _rows({"DEMO-SKU-020": 100})
    r = next(x for x in rows if x["produkt"] == "DEMO-SKU-020")
    assert r["zlec_potw_pal"] == 1        # potw 100/100
    assert r["zlec_niepotw_pal"] == 2     # niestandardowe 200/100
    # projekcja odejmuje niepotwierdzone, nie potwierdzone
    assert r["projekcja_mag_pal"] == 4    # 10 - (dostawy 4 + niepotw 2)


def test_urgent_flag():
    # PAZ duży -> mag_pal maleje, projekcja poniżej progu -> pilne
    rows, _, _ = _rows({"DEMO-SKU-020": 1000})
    r = next(x for x in rows if x["produkt"] == "DEMO-SKU-020")
    # mag 1000/1000=1, dostawy 0.4, zlec 0.2 -> projekcja 0.4 < 2
    assert r["pilne"] is True

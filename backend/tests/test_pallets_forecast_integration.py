from app.pallets_analysis import build_rows


def test_forecast_drives_need_when_present():
    stock = [{"produkt": "A", "ilosc": 100, "lok": "MAG"}]
    paz = {"A": 10.0}          # 10 szt/paleta
    rows, _, _ = build_rows(
        stock, [], [], [], paz, {}, key="produkt", location_field="lok",
        dlt_values={"DLT"}, open_statuses=set(), target_days=7, urgent_threshold=2,
        demand_forecast={"A": 140.0}, horizon_days=14)   # 140 szt = 14 palet na 14 dni
    r = next(x for x in rows if x["produkt"] == "A")
    # need = 14 palet forecast; stan_mag = 10 palet → sugestia dąży do 4 (cap floor(DLT)=0 → 0),
    # ale dni_zapasu liczone z prognozy (10 palet / (1 pal/dzień) = 10 dni)
    assert round(r["dni_zapasu"], 1) == 10.0

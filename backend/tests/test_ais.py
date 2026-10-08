"""AIS (aisstream.io): normalizacja nazw, ETA bez roku, obsługa wiadomości, endpoint."""
import datetime
import json

from app.models import TrackedVessel
from app.tracking.ais import (
    active_vessel_names,
    ais_eta_to_datetime,
    handle_message,
    next_backoff,
    normalize_name,
    prune_positions,
    sync_vessel_rows,
)
from tests.conftest import login


def test_normalize_name_strips_ais_padding():
    assert normalize_name("MV DEMO EOS NOVA@@@") == "MV DEMO EOS NOVA"
    assert normalize_name("  mv demo   gale ") == "MV DEMO GALE"
    assert normalize_name("") == ""


def test_normalize_name_strips_container_type_junk():
    # realne brudy z kolejki: typ kontenera doklejony do pola statku
    assert normalize_name("20'GP - MV DEMO CORAL") == "MV DEMO CORAL"
    assert normalize_name("40'NOR MV DEMO ORION") == "MV DEMO ORION"
    assert normalize_name("MV DEMO FJORD - 40'NOR") == "MV DEMO FJORD"
    assert normalize_name("20'GP- MV DEMO JUNO") == "MV DEMO JUNO"
    assert normalize_name("45'HC MV DEMO NORDIC") == "MV DEMO NORDIC"
    # duble po czyszczeniu zlewają się w jedną nazwę
    assert normalize_name("MV DEMO FJORD") == normalize_name("MV DEMO FJORD - 40'NOR")
    # myślnik w środku nazwy → spacja po obu stronach porównania (symetria)
    assert normalize_name("MV DEMO NORTH-STAR") == "MV DEMO NORTH STAR"


def test_normalize_name_handles_typographic_apostrophe_and_no_separator():
    # Excel/Word zamienia ' na ’ — bez tego statek cicho nie dopasowuje się w AIS
    assert normalize_name("20’GP MV DEMO CORAL") == "MV DEMO CORAL"
    assert normalize_name("MV DEMO FJORD 40’NOR") == normalize_name("MV DEMO FJORD - 40'NOR")
    # typ bez separatora
    assert normalize_name("40HC MV DEMO NORDIC") == "MV DEMO NORDIC"
    assert normalize_name("MV DEMO CORAL 20GP") == "MV DEMO CORAL"
    # ale token nazwy statku zaczynający się cyfrą NIE jest typem kontenera
    assert normalize_name("EVER 4EVER") == "EVER 4EVER"


def test_prune_positions_kasuje_tylko_stare_punkty(db_session):
    from app.models import TrackedVessel, VesselPosition, utcnow
    v = TrackedVessel(name="MV DEMO CORAL")
    db_session.add(v)
    db_session.commit()
    now = utcnow()
    db_session.add_all([
        VesselPosition(vessel_id=v.id, lat=1, lon=1, at=now - datetime.timedelta(days=90)),
        VesselPosition(vessel_id=v.id, lat=2, lon=2, at=now - datetime.timedelta(days=10)),
    ])
    db_session.commit()

    assert prune_positions(db_session) == 1
    left = db_session.query(VesselPosition).all()
    assert [p.lat for p in left] == [2]
    # idempotentne: drugi przebieg nie ma już co kasować
    assert prune_positions(db_session) == 0


def test_ais_eta_infers_year_across_new_year():
    now = datetime.datetime(2026, 12, 20)
    eta = ais_eta_to_datetime({"Month": 1, "Day": 5, "Hour": 8, "Minute": 30}, now)
    assert eta == datetime.datetime(2027, 1, 5, 8, 30)
    # ten sam rok, gdy miesiąc niedaleko w przód/wstecz
    eta = ais_eta_to_datetime({"Month": 12, "Day": 28, "Hour": 0, "Minute": 0},
                              datetime.datetime(2026, 12, 20))
    assert eta == datetime.datetime(2026, 12, 28)
    # AIS-owe „brak wartości": Month=0, Hour=24
    assert ais_eta_to_datetime({"Month": 0, "Day": 0}, now) is None
    eta = ais_eta_to_datetime({"Month": 12, "Day": 28, "Hour": 24, "Minute": 60}, now)
    assert eta == datetime.datetime(2026, 12, 28, 23, 59)
    assert ais_eta_to_datetime(None, now) is None
    assert ais_eta_to_datetime({"Month": 2, "Day": 31}, now) is None  # 31 lutego


def test_next_backoff_doubles_capped_with_jitter():
    no_jitter = lambda lo, hi: 1.0  # noqa: E731 — jitter wyłączony do sprawdzenia progresji
    assert next_backoff(0, base=60.0, jitter_fn=no_jitter) == 60.0
    assert next_backoff(60.0, base=60.0, jitter_fn=no_jitter) == 120.0
    assert next_backoff(1000.0, base=60.0, max_backoff=900.0, jitter_fn=no_jitter) == 900.0
    # jitter ±20% wokół wartości bazowej (rzeczywisty random.uniform)
    for _ in range(50):
        value = next_backoff(60.0, base=60.0, max_backoff=900.0)
        assert 96.0 <= value <= 144.0  # 120 ±20%


def _mk_vessel_row(db, name):
    vessel = TrackedVessel(name=name)
    db.add(vessel)
    db.commit()
    return vessel


def test_handle_message_learns_mmsi_and_position(db_session):
    vessel = _mk_vessel_row(db_session, "MV DEMO EOS NOVA")
    wanted = {vessel.name: vessel}
    raw = json.dumps({
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": 111222330, "ShipName": "MV DEMO EOS NOVA@@"},
        "Message": {"PositionReport": {"Latitude": 35.1, "Longitude": 18.4,
                                       "Sog": 17.3, "Cog": 42.0}},
    })
    assert handle_message(db_session, raw, wanted) is True
    assert vessel.mmsi == 111222330
    assert (vessel.lat, vessel.lon, vessel.sog, vessel.cog) == (35.1, 18.4, 17.3, 42.0)
    assert vessel.last_seen is not None


def test_handle_message_static_data_sets_destination_eta(db_session):
    vessel = _mk_vessel_row(db_session, "MV DEMO GALE")
    raw = json.dumps({
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": 111222332, "ShipName": "MV DEMO GALE",
                     "latitude": 1.2, "longitude": 103.8},
        "Message": {"ShipStaticData": {
            "Destination": "PL GDN", "Eta": {"Month": 10, "Day": 2, "Hour": 6, "Minute": 0}}},
    })
    assert handle_message(db_session, raw, {vessel.name: vessel}) is True
    assert vessel.destination == "PL GDN"
    assert vessel.ais_eta is not None and vessel.ais_eta.month == 10
    # discovery: pozycja z metadanych ShipStaticData, gdy brak PositionReport
    assert (vessel.lat, vessel.lon) == (1.2, 103.8)


def test_handle_message_ignores_foreign_and_broken(db_session):
    vessel = _mk_vessel_row(db_session, "MV DEMO KESTREL")
    wanted = {vessel.name: vessel}
    foreign = json.dumps({"MessageType": "PositionReport",
                          "MetaData": {"MMSI": 1, "ShipName": "MV DEMO ATLAS"},
                          "Message": {}})
    assert handle_message(db_session, foreign, wanted) is False
    assert handle_message(db_session, "not-json{", wanted) is False


def test_vessels_endpoint_returns_only_active_queue_vessels(client, db_session):
    headers = login(client)
    # kontener aktywny ze statkiem + wiersz AIS; drugi wiersz „historyczny" bez kontenera
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    resp = client.post("/api/containers", headers=headers, json={
        "container_no": "TGBU6784203", "vessel": "mv demo eos nova",
        "company_id": company_id})
    assert resp.status_code == 201, resp.text
    db_session.add(TrackedVessel(name="MV DEMO EOS NOVA", mmsi=111222330, lat=35.0, lon=18.0))
    db_session.add(TrackedVessel(name="STARY STATEK", mmsi=111111111))
    db_session.commit()

    names = active_vessel_names(db_session)
    assert "MV DEMO EOS NOVA" in names

    data = client.get("/api/tracking/vessels", headers=headers).json()
    returned = {v["name"] for v in data}
    assert "MV DEMO EOS NOVA" in returned
    assert "STARY STATEK" not in returned


def test_position_report_appends_trail_point(db_session):
    from app.models import VesselPosition
    vessel = _mk_vessel_row(db_session, "MV TRAIL")
    wanted = {vessel.name: vessel}
    def report(lat, lon):
        return json.dumps({"MessageType": "PositionReport",
                           "MetaData": {"MMSI": 999999999, "ShipName": "MV TRAIL"},
                           "Message": {"PositionReport": {"Latitude": lat, "Longitude": lon}}})
    handle_message(db_session, report(30.0, 20.0), wanted)   # pierwszy punkt
    handle_message(db_session, report(30.005, 20.005), wanted)  # szum kotwicy — bez punktu
    handle_message(db_session, report(30.5, 20.5), wanted)   # realny ruch — punkt
    pts = db_session.query(VesselPosition).filter_by(vessel_id=vessel.id).all()
    assert [(p.lat, p.lon) for p in pts] == [(30.0, 20.0), (30.5, 20.5)]


def test_vessels_endpoint_returns_trail_companies_delayed(client, db_session):
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    resp = client.post("/api/containers", headers=headers, json={
        "container_no": "TGBU6784203", "vessel": "MV BADANY",
        "company_id": company_id, "eta": "2020-01-01"})   # ETA dawno minęła → opóźniony
    assert resp.status_code == 201, resp.text
    from app.models import VesselPosition
    vessel = _mk_vessel_row(db_session, "MV BADANY")
    db_session.add_all([
        VesselPosition(vessel_id=vessel.id, lat=30.0, lon=20.0),
        VesselPosition(vessel_id=vessel.id, lat=31.0, lon=21.0)])
    db_session.commit()
    data = client.get("/api/tracking/vessels", headers=headers).json()
    v = next(x for x in data if x["name"] == "MV BADANY")
    assert v["trail"] == [[30.0, 20.0], [31.0, 21.0]]
    assert v["companies"] == ["ACME"]
    assert v["containers"] == 1
    assert v["delayed"] == 1


def test_locate_destination_locode_and_name():
    from app.routers.tracking import locate_destination
    assert locate_destination("PL GDN") == (54.40, 18.66)   # LOCODE ze spacją
    assert locate_destination("PLGDN") == (54.40, 18.66)
    assert locate_destination("GDANSK") == (54.40, 18.66)   # fallback po nazwie
    assert locate_destination("XX NOWHERE") is None
    assert locate_destination("") is None


def test_hours_to_destination_math_and_guards():
    from app.routers.tracking import hours_to_destination
    # wielkie koło Algeciras→Gdańsk ≈ 1480 nm → ~99 h przy 15 kn (sanity ±15%);
    # celowo mniej niż trasa morska (~2200 nm) — patrz ponytail w hours_to_destination
    h = hours_to_destination(36.13, -5.44, 15.0, "PLGDN")
    assert h is not None and 84 < h < 114
    assert hours_to_destination(36.13, -5.44, 1.0, "PLGDN") is None   # dryf < 3 kn
    assert hours_to_destination(None, None, 15.0, "PLGDN") is None    # brak pozycji
    assert hours_to_destination(36.13, -5.44, 15.0, "???") is None    # nieznany port


def test_vessels_endpoint_reports_eta_drift(client, db_session):
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    resp = client.post("/api/containers", headers=headers, json={
        "container_no": "TGBU6784203", "vessel": "MV DRIFT",
        "company_id": company_id, "eta": "2030-01-10"})
    assert resp.status_code == 201, resp.text
    vessel = _mk_vessel_row(db_session, "MV DRIFT")
    vessel.ais_eta = datetime.datetime(2030, 1, 14, 6, 0)   # 4 dni po ETA kontenera
    db_session.commit()
    data = client.get("/api/tracking/vessels", headers=headers).json()
    v = next(x for x in data if x["name"] == "MV DRIFT")
    assert v["drift_days"] == 4
    assert v["eta_alert"] is True    # próg domyślny tracking_eta_alert_days=2


def test_sync_vessel_rows_upserts_without_deleting(db_session):
    db_session.add(TrackedVessel(name="ZOSTAJE", mmsi=222222222))
    db_session.commit()
    wanted = sync_vessel_rows(db_session, {"NOWY STATEK"})
    assert set(wanted) == {"NOWY STATEK"}
    all_names = {v.name for v in db_session.query(TrackedVessel).all()}
    assert {"ZOSTAJE", "NOWY STATEK"} <= all_names

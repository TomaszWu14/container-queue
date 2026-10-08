"""AIS: geofence portów (histereza, zawinięcia), endpointy portów/pogody, flagi opóźnień."""
import json

from app.models import TrackedVessel
from app.tracking.ais import handle_message
from tests.conftest import login
from tests.test_ais import _mk_vessel_row


def test_nearest_port_geofence():
    from app.tracking.geo import nearest_port
    assert nearest_port(54.38, 18.70) == "GDANSK"       # reda Gdańska
    assert nearest_port(45.0, -30.0) is None            # środek Atlantyku
    assert nearest_port(52.23, 21.01) is None           # Warszawa — port lądowy poza geofence


def test_resolve_port_enters_from_open_sea():
    from app.tracking.geo import resolve_port
    assert resolve_port("", 54.38, 18.70) == "GDANSK"


def test_resolve_port_stays_in_hysteresis_when_candidate_within_band():
    """W2: kandydat (Gdynia) w paśmie 2 NM od bieżącego (Gdańsk) — bez przełączenia."""
    from app.tracking.geo import resolve_port
    assert resolve_port("GDANSK", 54.475, 18.60) == "GDANSK"


def test_resolve_port_switches_when_candidate_clearly_closer():
    """Trwała zmiana portu w klastrze (Gdańsk→Gdynia, ~8 NM > pasmo 2 NM) przełącza."""
    from app.tracking.geo import resolve_port
    assert resolve_port("GDANSK", 54.53, 18.55) == "GDYNIA"


def test_resolve_port_exits_when_no_candidate_in_range():
    from app.tracking.geo import resolve_port
    assert resolve_port("GDANSK", 45.0, -30.0) is None


def test_position_report_sets_near_port_and_notifies(client, db_session):
    from app.models import Notification
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    client.post("/api/containers", headers=headers, json={
        "container_no": "TGBU6784203", "vessel": "MV PORTOWY", "company_id": company_id})
    vessel = _mk_vessel_row(db_session, "MV PORTOWY")
    raw = json.dumps({"MessageType": "PositionReport",
                      "MetaData": {"MMSI": 888888888, "ShipName": "MV PORTOWY"},
                      "Message": {"PositionReport": {"Latitude": 54.38, "Longitude": 18.70,
                                                     "Sog": 0.4}}})
    assert handle_message(db_session, raw, {vessel.name: vessel}) is True
    assert vessel.near_port == "GDANSK"
    assert vessel.near_port_since is not None
    ports = db_session.query(Notification).filter_by(kind="vessel_port").all()
    assert any("MV PORTOWY" in n.title and "GDANSK" in n.title for n in ports)
    # druga pozycja w tym samym porcie — bez kolejnego powiadomienia
    handle_message(db_session, raw, {vessel.name: vessel})
    assert db_session.query(Notification).filter_by(kind="vessel_port").count() == len(ports)


def test_port_entry_creates_call_and_exit_closes_it(db_session):
    from app.models import VesselPortCall
    vessel = _mk_vessel_row(db_session, "MV PORTCALL")
    wanted = {vessel.name: vessel}

    def report(lat, lon):
        return json.dumps({"MessageType": "PositionReport",
                           "MetaData": {"MMSI": 777777777, "ShipName": "MV PORTCALL"},
                           "Message": {"PositionReport": {"Latitude": lat, "Longitude": lon}}})

    handle_message(db_session, report(54.38, 18.70), wanted)   # wejście: reda Gdańska
    calls = db_session.query(VesselPortCall).filter_by(vessel_id=vessel.id).all()
    assert len(calls) == 1
    assert calls[0].port == "GDANSK"
    assert calls[0].arrived_at is not None
    assert calls[0].departed_at is None

    handle_message(db_session, report(45.0, -30.0), wanted)   # wyjście: pełne morze
    db_session.refresh(calls[0])
    assert calls[0].departed_at is not None
    assert db_session.query(VesselPortCall).filter_by(vessel_id=vessel.id).count() == 1


def test_handle_message_bad_mmsi_conflict_dropped_session_survives(db_session):
    """W1: druga wiadomość ucząca MMSI już zajęte innym wierszem nie wywraca sesji —
    wiadomość jest porzucana (bez commitu), a KOLEJNA wciąż się przetwarza."""
    _mk_vessel_row(db_session, "MV OWNER").mmsi = 555555555
    db_session.commit()
    vessel = _mk_vessel_row(db_session, "MV RENAMED")
    wanted = {vessel.name: vessel}
    conflicting = json.dumps({"MessageType": "PositionReport",
                              "MetaData": {"MMSI": 555555555, "ShipName": "MV RENAMED"},
                              "Message": {"PositionReport": {"Latitude": 1.0, "Longitude": 2.0}}})
    assert handle_message(db_session, conflicting, wanted) is True   # wiadomość i tak przetworzona
    assert vessel.mmsi is None   # ale mmsi nie nadpisane cudzym

    next_msg = json.dumps({"MessageType": "PositionReport",
                           "MetaData": {"MMSI": 666666666, "ShipName": "MV RENAMED"},
                           "Message": {"PositionReport": {"Latitude": 3.0, "Longitude": 4.0}}})
    assert handle_message(db_session, next_msg, wanted) is True    # sesja żyje dalej
    assert vessel.mmsi == 666666666


def test_port_geofence_hysteresis_no_flip_flop(client, db_session):
    """W2: statek migoczący między Gdańskiem a Gdynią (8 NM) trzyma JEDEN otwarty
    port call i wysyła JEDNO powiadomienie o przybyciu, zamiast flip-flopować."""
    from app.models import Notification, VesselPortCall
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    assert client.post("/api/containers", headers=headers, json={
        "container_no": "TGBU6784203", "vessel": "MV HISTERIA",
        "company_id": company_id}).status_code == 201
    vessel = _mk_vessel_row(db_session, "MV HISTERIA")

    def report(lat, lon):
        return json.dumps({"MessageType": "PositionReport",
                           "MetaData": {"MMSI": 444444444, "ShipName": "MV HISTERIA"},
                           "Message": {"PositionReport": {"Latitude": lat, "Longitude": lon}}})

    # dwa punkty na redzie MIĘDZY portami (~1.3 NM różnicy dystansów — poniżej
    # pasma przełączenia 2 NM); nearest_port sam z siebie flipowałby między nimi
    near_gdansk, near_gdynia = (54.455, 18.61), (54.475, 18.60)
    wanted = {vessel.name: vessel}
    for lat, lon in [near_gdansk, near_gdynia, near_gdansk, near_gdynia, near_gdansk]:
        handle_message(db_session, report(lat, lon), wanted)

    calls = db_session.query(VesselPortCall).filter_by(vessel_id=vessel.id).all()
    assert len(calls) == 1
    assert calls[0].departed_at is None
    assert db_session.query(Notification).filter_by(kind="vessel_port").count() == 1

    # odpłynięcie daleko poza promień wyjścia zamyka postój
    handle_message(db_session, report(45.0, -30.0), wanted)
    db_session.refresh(calls[0])
    assert calls[0].departed_at is not None


def test_port_switch_in_cluster_closes_old_opens_new(client, db_session):
    """Review: trwała zmiana portu w klastrze (Gdańsk→Gdynia, ~8 NM > pasmo 2 NM)
    MUSI przełączyć: stary call zamknięty, nowy otwarty, jedno powiadomienie Gdynia."""
    from app.models import Notification, VesselPortCall
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    assert client.post("/api/containers", headers=headers, json={
        "container_no": "TGBU6784203", "vessel": "MV PRZESIADKA",
        "company_id": company_id}).status_code == 201
    vessel = _mk_vessel_row(db_session, "MV PRZESIADKA")

    def report(lat, lon):
        return json.dumps({"MessageType": "PositionReport",
                           "MetaData": {"MMSI": 333333333, "ShipName": "MV PRZESIADKA"},
                           "Message": {"PositionReport": {"Latitude": lat, "Longitude": lon}}})

    wanted = {vessel.name: vessel}
    for lat, lon in [(54.40, 18.66), (54.53, 18.55), (54.53, 18.55), (54.53, 18.55)]:
        handle_message(db_session, report(lat, lon), wanted)

    calls = {c.port: c for c in db_session.query(VesselPortCall)
             .filter_by(vessel_id=vessel.id).all()}
    assert set(calls) == {"GDANSK", "GDYNIA"}
    assert calls["GDANSK"].departed_at is not None    # stary domknięty
    assert calls["GDYNIA"].departed_at is None        # nowy otwarty
    assert vessel.near_port == "GDYNIA"
    gdynia_notes = [n for n in db_session.query(Notification)
                    .filter_by(kind="vessel_port").all() if "GDYNIA" in n.title]
    assert len(gdynia_notes) == 1


def test_predicted_late_flag(client, db_session):
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    client.post("/api/containers", headers=headers, json={
        "container_no": "TGBU6784203", "vessel": "MV SPOZNIONY",
        "company_id": company_id, "eta": "2026-09-09"})   # jutro-nierealne
    vessel = _mk_vessel_row(db_session, "MV SPOZNIONY")
    # Algeciras, 12 kn, cel Gdańsk → ~5 dni drogi, ETA za dzień → nie zdąży
    vessel.lat, vessel.lon, vessel.sog, vessel.destination = 36.13, -5.44, 12.0, "PLGDN"
    db_session.commit()
    data = client.get("/api/tracking/vessels", headers=headers).json()
    v = next(x for x in data if x["name"] == "MV SPOZNIONY")
    assert v["predicted_late"] is True


def test_status_age_days_single_query(client, db_session):
    """#27: wiek statusu z audytu — obecny w liście kontenerów."""
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    created = client.post("/api/containers", headers=headers, json={
        "container_no": "TGBU6784203", "company_id": company_id}).json()
    data = client.get("/api/containers?limit=50", headers=headers).json()
    row = next(x for x in data if x["id"] == created["id"])
    assert row["status_age_days"] == 0   # status nadany przy utworzeniu = dziś

def test_weather_endpoint_scoped_and_mocked(client, db_session, monkeypatch):
    """Pogoda: user widzi tylko statki wyprowadzone z JEGO kontenerów; cache
    współdzielony nie przecieka cudzych vessel_id (fix: unscoped weather)."""
    from app.tracking import weather
    from tests.conftest import forwarder
    weather._cache.update(at=None, data=[])

    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    assert client.post("/api/containers", headers=headers, json={
        "container_no": "TGBU6784203", "vessel": "MV POGODNA",
        "company_id": company_id}).status_code == 201
    db_session.add(TrackedVessel(name="MV POGODNA", mmsi=222222222, lat=35.0, lon=18.0))
    db_session.commit()
    vid = db_session.query(TrackedVessel).filter_by(name="MV POGODNA").one().id

    class _Resp:
        def __init__(self, data): self._d = data
        def json(self): return self._d

    def fake_get(url, params=None, timeout=None):
        if "marine" in url:
            return _Resp([{"current": {"wave_height": 1.2}}])
        return _Resp([{"current": {"wind_speed_10m": 20.0, "wind_direction_10m": 90}}])
    monkeypatch.setattr("httpx.get", fake_get)

    data = client.get("/api/tracking/weather", headers=headers).json()
    assert [x["vessel_id"] for x in data] == [vid]
    assert data[0]["wind_kmh"] == 20.0

    # spedytor bez zleceń: cache pełny, ale odpowiedź pusta (izolacja)
    spedalfa = forwarder(client, headers, "SPEDALFA")["id"]
    client.post("/api/users", headers=headers, json={
        "login": "sped.spedalfa", "password": "haslo123", "role": "forwarder",
        "forwarder_id": spedalfa, "email": "spedalfa@example.com"})
    sped = login(client, "sped.spedalfa", "haslo123")
    assert client.get("/api/tracking/weather", headers=sped).json() == []

"""Pogoda na pozostałej trasie: próbkowanie wielkiego okręgu + batch open-meteo (mock)."""
from app.models import TrackedVessel
from app.tracking import weather
from app.tracking.weather import route_points
from tests.conftest import login


def _active_container(client, vessel, no="TGBU6784203"):
    """Pogoda liczy się tylko dla statków z aktywnych kontenerów."""
    headers = login(client)
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "ACME")
    assert client.post("/api/containers", headers=headers, json={
        "container_no": no, "vessel": vessel,
        "company_id": company_id}).status_code == 201


def test_route_points_sampling_between_endpoints():
    # Singapur → Gdańsk: 4 punkty pośrednie, bez końców, lat rośnie monotonicznie
    pts = route_points(1.29, 103.85, 54.40, 18.66)
    assert len(pts) == 4
    lats = [p[0] for p in pts]
    assert all(1.29 < la < 90 for la in lats)
    assert lats == sorted(lats)   # trasa na północ — kolejne próbki coraz dalej


def test_route_points_degenerate_same_point():
    assert route_points(10.0, 20.0, 10.0, 20.0) == []


class _Resp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


def test_fetch_weather_includes_route_samples(client, db_session, monkeypatch):
    weather._cache.update(at=None, data=[])
    _active_container(client, "MV TRASA")
    db_session.add(TrackedVessel(name="MV TRASA", lat=1.29, lon=103.85,
                                 destination="PLGDN"))
    db_session.commit()
    vid = db_session.query(TrackedVessel).filter_by(name="MV TRASA").one().id

    calls = {}

    def fake_get(url, params=None, timeout=None):
        n = len(params["latitude"].split(","))
        calls["n"] = n
        if "marine" in url:
            return _Resp([{"current": {"wave_height": 1.0 + i}} for i in range(n)])
        return _Resp([{"current": {"wind_speed_10m": 10.0 + i,
                                   "wind_direction_10m": 90}} for i in range(n)])

    monkeypatch.setattr("httpx.get", fake_get)
    data = weather.fetch_weather(db_session)
    weather._cache.update(at=None, data=[])   # nie zostawiaj cache innym testom

    assert calls["n"] == 5   # pozycja + 4 próbki trasy w JEDNYM batchu
    entry = next(x for x in data if x["vessel_id"] == vid)
    assert entry["wind_kmh"] == 10.0
    assert len(entry["route"]) == 4
    # próbki trasy mają własną pogodę i współrzędne między statkiem a Gdańskiem
    assert entry["route"][0]["wind_kmh"] == 11.0
    assert all(1.29 < p["lat"] < 60 for p in entry["route"])


def test_fetch_weather_no_destination_keeps_shape(client, db_session, monkeypatch):
    weather._cache.update(at=None, data=[])
    _active_container(client, "MV BEZCELU")
    db_session.add(TrackedVessel(name="MV BEZCELU", lat=35.0, lon=18.0))
    db_session.commit()

    def fake_get(url, params=None, timeout=None):
        n = len(params["latitude"].split(","))
        key = "wave_height" if "marine" in url else "wind_speed_10m"
        return _Resp([{"current": {key: 5}} for _ in range(n)])

    monkeypatch.setattr("httpx.get", fake_get)
    data = weather.fetch_weather(db_session)
    weather._cache.update(at=None, data=[])
    assert data and data[0]["route"] == []


def test_fetch_weather_caches_failure(client, db_session, monkeypatch):
    """Awaria open-meteo: kolejne wejście na mapę nie czeka znów 2×8 s pod lockiem."""
    weather._cache.update(at=None, data=[])
    _active_container(client, "MV AWARIA")
    db_session.add(TrackedVessel(name="MV AWARIA", lat=35.0, lon=18.0))
    db_session.commit()
    calls = []

    def boom(url, params=None, timeout=None):
        calls.append(url)
        raise TimeoutError("open-meteo leży")

    monkeypatch.setattr("httpx.get", boom)
    assert weather.fetch_weather(db_session) == []
    assert weather.fetch_weather(db_session) == []
    weather._cache.update(at=None, data=[])
    assert len(calls) == 1          # drugi raz z negatywnego cache, bez HTTP


def test_fetch_weather_skips_vessels_without_active_container(client, db_session,
                                                              monkeypatch):
    """Historyczne TrackedVessel (nikt ich nie kasuje) nie puchną batcha."""
    weather._cache.update(at=None, data=[])
    _active_container(client, "MV AKTYWNY")
    db_session.add(TrackedVessel(name="MV AKTYWNY", lat=35.0, lon=18.0))
    db_session.add(TrackedVessel(name="MV HISTORYCZNY", lat=10.0, lon=10.0))
    db_session.commit()
    calls = {}

    def fake_get(url, params=None, timeout=None):
        calls["n"] = len(params["latitude"].split(","))
        return _Resp([{"current": {}} for _ in range(calls["n"])])

    monkeypatch.setattr("httpx.get", fake_get)
    weather.fetch_weather(db_session)
    weather._cache.update(at=None, data=[])
    assert calls["n"] == 1

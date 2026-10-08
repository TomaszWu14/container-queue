"""AIS: subskrypcja aisstream — tryby discovery/pozycje i rotacja paczek MMSI ponad limit."""
from app.tracking.ais import MMSI_FILTER_MAX, build_subscription


def test_build_subscription_modes():
    sub = build_subscription("key", [111222330, 111222331])
    assert sub["FiltersShipMMSI"] == ["111222330", "111222331"]
    assert "PositionReport" in sub["FilterMessageTypes"]
    # discovery: bez MMSI — tylko ShipStaticData (bez zalewu pozycji całego świata)
    sub = build_subscription("key", [])
    assert "FiltersShipMMSI" not in sub
    assert sub["FilterMessageTypes"] == ["ShipStaticData"]


def test_build_subscription_rotates_over_mmsi_limit():
    """> 50 statków: kolejne sesje biorą kolejne paczki, żaden statek nie zostaje
    trwale bez pozycji (wcześniej nadmiarowe odpadały na zawsze)."""
    mmsis = list(range(200000000, 200000000 + 120))
    covered: set[str] = set()
    for rotation in range(3):
        chunk = build_subscription("key", mmsis, rotation)["FiltersShipMMSI"]
        assert len(chunk) == MMSI_FILTER_MAX
        covered |= set(chunk)
    assert covered == {str(m) for m in mmsis}


def test_ais_loop_rotates_only_positions_sessions(monkeypatch):
    """Tryb mieszany (część statków bez MMSI): pozycje idą co drugą sesję (flip).
    Rotacja musi rosnąć tylko po sesjach pozycji — inaczej sesje pozycji widzą
    wyłącznie nieparzyste rotacje i przy N=100 dolna paczka 50 MMSI nigdy nie
    dostaje pozycji (start zawsze 50)."""
    import asyncio

    from app.tracking import ais

    seen: list[int] = []

    async def fake_session(_db, _deadline, *, prefer_positions=False, rotation=0):
        if len(seen) >= 4:
            raise asyncio.CancelledError
        if prefer_positions:   # mieszany tryb: bez flip byłoby discovery
            seen.append(rotation)
        return prefer_positions

    async def no_sleep(_s):
        return None

    monkeypatch.setattr(ais, "run_session", fake_session)
    monkeypatch.setattr(ais.asyncio, "sleep", no_sleep)
    try:
        asyncio.run(ais.ais_loop())
    except asyncio.CancelledError:
        pass
    mmsis = list(range(200000000, 200000000 + 100))
    covered: set[str] = set()
    for rotation in seen:
        covered |= set(build_subscription("key", mmsis, rotation)["FiltersShipMMSI"])
    assert covered == {str(m) for m in mmsis}

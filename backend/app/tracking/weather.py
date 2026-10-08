"""Cache pogody dla śledzonych statków: proxy open-meteo (wiatr + fala), TTL 30 min."""
import datetime
import logging
import math
import threading

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import TrackedVessel
from .ais import active_vessel_names
from .geo import locate_destination

logger = logging.getLogger(__name__)
_cache: dict = {"at": None, "data": [], "ttl": 0}
_lock = threading.Lock()
TTL_S = 1800
# negatywny cache: po awarii upstreamu kolejne wejścia na mapę nie czekają znów
# 2×8 s pod globalnym lockiem (polling co 5 min per user kolejkował się do ~16 s)
ERROR_TTL_S = 300
ROUTE_SAMPLES = 4   # punkty pośrednie na pozostałej trasie (wielki okrąg)


def route_points(lat1: float, lon1: float, lat2: float, lon2: float,
                 n: int = ROUTE_SAMPLES) -> list[tuple[float, float]]:
    """n punktów pośrednich wielkiego okręgu (slerp wektorów 3D) między pozycją
    statku a portem docelowym — bez końców (pozycja ma już swoją pogodę).

    ponytail: wielki okrąg, nie trasa morska — punkt może wypaść na lądzie;
    open-meteo i tak zwróci tam wiatr, a fala będzie None (marine API)."""
    def vec(lat: float, lon: float) -> tuple[float, float, float]:
        la, lo = math.radians(lat), math.radians(lon)
        return (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
    va, vb = vec(lat1, lon1), vec(lat2, lon2)
    d = max(-1.0, min(1.0, sum(a * b for a, b in zip(va, vb, strict=True))))
    ang = math.acos(d)
    if ang < 1e-6 or math.sin(ang) < 1e-6:
        return []
    out = []
    for i in range(1, n + 1):
        t = i / (n + 1)
        ka = math.sin((1 - t) * ang) / math.sin(ang)
        kb = math.sin(t * ang) / math.sin(ang)
        x, y, z = (ka * va[j] + kb * vb[j] for j in range(3))
        out.append((round(math.degrees(math.asin(max(-1.0, min(1.0, z)))), 2),
                    round(math.degrees(math.atan2(y, x)), 2)))
    return out


def fetch_weather(db: Session) -> list[dict]:
    """Wiatr i fala we WSZYSTKICH śledzonych statkach + próbki na pozostałej trasie
    (open-meteo, bez klucza).

    Best-effort: błąd upstreamu = pusta lista, mapa działa dalej. Jeden batch
    (multi-point) na pozycje i trasy razem; cache współdzielony między userami —
    trzyma WSZYSTKIE statki, przycinanie do statków widocznych dla usera to zadanie
    wołającego (izolacja per-zasób jak w tracked_vessels)."""
    now = datetime.datetime.now(datetime.UTC)
    # lock: TTL-check + refill atomowo — bez niego zimny cache wypuszczał
    # N równoległych requestów do open-meteo (thundering herd)
    # ponytail: jeden globalny lock, wystarczy dla jednego upstreama
    with _lock:
        if _cache["at"] and (now - _cache["at"]).total_seconds() < _cache["ttl"]:
            return _cache["data"]

        # tylko statki aktywnych kontenerów — TrackedVessel nie jest kasowany
        # (ais.sync_vessel_rows), więc bez tego batch i URL rosły bez końca
        names = active_vessel_names(db)
        vessels = [(v.id, v.lat, v.lon, v.destination)
                   for v in db.scalars(select(TrackedVessel).where(
                       TrackedVessel.lat.is_not(None),
                       TrackedVessel.name.in_(names))).all()] if names else []
        if not vessels:
            return []
        # plan zapytania: pozycja statku + punkty trasy, jeden płaski batch
        plan: list[tuple[int, str, float, float]] = []   # (vessel_id, rodzaj, lat, lon)
        for vid, lat, lon, dest in vessels:
            plan.append((vid, "current", lat, lon))
            coords = locate_destination(dest)
            if coords:
                for rlat, rlon in route_points(lat, lon, *coords):
                    plan.append((vid, "route", rlat, rlon))
        lats = ",".join(f"{lat:.2f}" for _, _, lat, _ in plan)
        lons = ",".join(f"{lon:.2f}" for _, _, _, lon in plan)
        out: list[dict] = []
        try:
            wind = httpx.get(
                "https://api.open-meteo.com/v1/forecast",
                params={"latitude": lats, "longitude": lons,
                        "current": "wind_speed_10m,wind_direction_10m"},
                timeout=8).json()
            wave = httpx.get(
                "https://marine-api.open-meteo.com/v1/marine",
                params={"latitude": lats, "longitude": lons,
                        "current": "wave_height"},
                timeout=8).json()
            # multi-point zwraca listę obiektów; pojedynczy punkt — obiekt
            wind_list = wind if isinstance(wind, list) else [wind]
            wave_list = wave if isinstance(wave, list) else [wave]
            by_vessel: dict[int, dict] = {}
            for i, (vid, kind, lat, lon) in enumerate(plan):
                cur = (wind_list[i].get("current") or {}) if i < len(wind_list) else {}
                mar = (wave_list[i].get("current") or {}) if i < len(wave_list) else {}
                sample = {"wind_kmh": cur.get("wind_speed_10m"),
                          "wind_dir": cur.get("wind_direction_10m"),
                          "wave_m": mar.get("wave_height")}
                if kind == "current":
                    entry = {"vessel_id": vid, **sample, "route": []}
                    by_vessel[vid] = entry
                    out.append(entry)
                elif vid in by_vessel:
                    by_vessel[vid]["route"].append({"lat": lat, "lon": lon, **sample})
        except Exception:  # noqa: BLE001 — pogoda to dekoracja, nie blocker
            # negatywny cache → najwyżej jeden wpis na ERROR_TTL_S
            logger.warning("pogoda: open-meteo niedostępne", exc_info=True)
            _cache.update(at=now, data=[], ttl=ERROR_TTL_S)
            return []
        _cache.update(at=now, data=out, ttl=TTL_S)
        return out

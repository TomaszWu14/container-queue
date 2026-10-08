"""Geografia portów: współrzędne, dopasowanie nazw/LOCODE, dystanse, geofence.

Wydzielone z routers.tracking, żeby kolektor AIS mógł liczyć bliskość portu
bez importu warstwy routerów (cykl: router importuje tracking.ais)."""
import math

# współrzędne głównych portów (lat, lon) — dopasowanie po nazwie lokalizacji
PORT_COORDS: dict[str, tuple[float, float]] = {
    "SHANGHAI": (31.23, 121.49), "NINGBO": (29.87, 121.55), "YANTIAN": (22.58, 114.27),
    "SHEKOU": (22.48, 113.92), "SHENZHEN": (22.54, 114.05), "QINGDAO": (36.07, 120.38),
    "XIAMEN": (24.48, 118.08), "TIANJIN": (39.00, 117.71), "XINGANG": (39.00, 117.71),
    "DALIAN": (38.92, 121.63), "GUANGZHOU": (23.11, 113.25), "NANSHA": (22.77, 113.60),
    "HONG KONG": (22.30, 114.17), "KAOHSIUNG": (22.62, 120.28), "BUSAN": (35.10, 129.04),
    "SINGAPORE": (1.29, 103.85), "TANJUNG PELEPAS": (1.37, 103.55),
    "PORT KLANG": (3.00, 101.40), "KLANG": (3.00, 101.40),
    "COLOMBO": (6.93, 79.85), "MUNDRA": (22.74, 69.70), "NHAVA SHEVA": (18.95, 72.95),
    "JEBEL ALI": (25.01, 55.06), "SALALAH": (16.94, 54.00),
    "PORT SAID": (31.26, 32.30), "SUEZ": (29.97, 32.55), "PIRAEUS": (37.94, 23.64),
    "GDANSK": (54.40, 18.66), "GDAŃSK": (54.40, 18.66), "GDYNIA": (54.53, 18.55),
    "HAMBURG": (53.54, 9.98), "BREMERHAVEN": (53.55, 8.58), "ROTTERDAM": (51.95, 4.14),
    "ANTWERP": (51.28, 4.34), "ANTWERPIA": (51.28, 4.34), "LE HAVRE": (49.48, 0.11),
    "FELIXSTOWE": (51.95, 1.31), "VALENCIA": (39.44, -0.32), "ALGECIRAS": (36.13, -5.44),
    "BARCELONA": (41.35, 2.16), "GENOA": (44.40, 8.93), "GENUA": (44.40, 8.93),
    "KOPER": (45.55, 13.73), "TRIESTE": (45.62, 13.77), "CONSTANTA": (44.17, 28.65),
    "MALASZEWICZE": (52.03, 23.53), "MAŁASZEWICZE": (52.03, 23.53),
    "DUISBURG": (51.43, 6.76), "WARSZAWA": (52.23, 21.01), "LODZ": (51.76, 19.46),
    "ŁÓDŹ": (51.76, 19.46), "SLAWKOW": (50.30, 19.39), "SŁAWKÓW": (50.30, 19.39),
    "NEW YORK": (40.67, -74.04), "LOS ANGELES": (33.73, -118.26),
    "SAVANNAH": (32.08, -81.09), "SANTOS": (-23.96, -46.33),
}

# AIS Destination to zwykle UN/LOCODE ("PLGDN", "BEANR", "PL GDN") — mapa najczęstszych
# na naszych trasach; reszta próbuje locate() po nazwie
LOCODE_COORDS: dict[str, tuple[float, float]] = {
    "PLGDN": (54.40, 18.66), "PLGDY": (54.53, 18.55),
    "DEHAM": (53.54, 9.98), "DEBRV": (53.55, 8.58), "NLRTM": (51.95, 4.14),
    "BEANR": (51.28, 4.34), "FRLEH": (49.48, 0.11), "ESALG": (36.13, -5.44),
    "ESVLC": (39.44, -0.32), "GRPIR": (37.94, 23.64), "EGPSD": (31.26, 32.30),
    "SGSIN": (1.29, 103.85), "CNSHA": (31.23, 121.49), "CNNGB": (29.87, 121.55),
    "KRPUS": (35.10, 129.04), "MAPTM": (35.89, -5.50),  # Tanger Med
}

# porty "morskie" pod geofence — bez punktów lądowych (Warszawa/Łódź/Sławków itd.),
# żeby ciężarówkowy interior nie generował fałszywych "statek przy porcie"
_INLAND = {"MALASZEWICZE", "MAŁASZEWICZE", "DUISBURG", "WARSZAWA", "LODZ", "ŁÓDŹ",
           "SLAWKOW", "SŁAWKÓW", "SUEZ"}
SEA_PORTS = {name: xy for name, xy in PORT_COORDS.items() if name not in _INLAND}

GEOFENCE_NM = 15.0   # promień "przy porcie" w milach morskich

# histereza geofence: raz otwarty port call trzyma się, dopóki statek nie wyjdzie
# poza ten promień (szerszy niż promień wejścia) — Gdańsk i Gdynia leżą ~8 NM od
# siebie (mniej niż 2x GEOFENCE_NM), więc bez tego statek na redzie między nimi
# przełącza port przy każdej wiadomości (flip-flop = spam powiadomień)
PORT_EXIT_MARGIN_NM = GEOFENCE_NM * 1.2
# pasmo przełączenia na sąsiedni port: kandydat musi być bliższy od bieżącego
# portu o >2 NM — szum GPS i dryf na kotwicy to ułamki mili, więc nie przełączą,
# a realne zacumowanie w sąsiednim porcie (różnica rzędu całej odległości
# Gdańsk↔Gdynia ~8 NM) przełącza od razu
PORT_SWITCH_BAND_NM = 2.0


def locate(text: str) -> tuple[float, float] | None:
    upper = (text or "").upper()
    for name, coords in PORT_COORDS.items():
        if name in upper:
            return coords
    return None


def locate_destination(dest: str) -> tuple[float, float] | None:
    """Port docelowy z pola AIS Destination: najpierw LOCODE, potem nazwa."""
    squashed = "".join((dest or "").upper().split())
    return LOCODE_COORDS.get(squashed) or locate(dest)


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a1, o1, a2, o2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (math.sin((a2 - a1) / 2) ** 2
         + math.cos(a1) * math.cos(a2) * math.sin((o2 - o1) / 2) ** 2)
    return 3440.1 * 2 * math.asin(math.sqrt(a))


def nearest_port(lat: float, lon: float,
                 radius_nm: float = GEOFENCE_NM) -> str | None:
    """Najbliższy port morski w promieniu geofence — albo None (pełne morze)."""
    best_name, best_nm = None, radius_nm
    for name, (plat, plon) in SEA_PORTS.items():
        d = haversine_nm(lat, lon, plat, plon)
        if d < best_nm:
            best_name, best_nm = name, d
    return best_name


def resolve_port(current_port: str, new_lat: float, new_lon: float) -> str | None:
    """Port statku po nowej pozycji, z histerezą wyjścia/przełączenia.

    `current_port` = `vessel.near_port` (pusty string = brak). Bez histerezy
    statek na redzie między dwoma bliskimi portami (np. Gdańsk/Gdynia) przełącza
    port przy każdej wiadomości — patrz PORT_EXIT_MARGIN_NM/PORT_SWITCH_BAND_NM."""
    port = nearest_port(new_lat, new_lon)  # kandydat (w swoim GEOFENCE_NM albo None)
    current = PORT_COORDS.get(current_port) if current_port else None
    if current and port != current_port:
        d_cur = haversine_nm(new_lat, new_lon, *current)
        if d_cur <= PORT_EXIT_MARGIN_NM and not (
                port and haversine_nm(new_lat, new_lon, *PORT_COORDS[port])
                < d_cur - PORT_SWITCH_BAND_NM):
            # histereza: wciąż w promieniu wyjścia z otwartego portu, a kandydat
            # nie jest wyraźnie (>pasmo) bliższy — zostajemy przy bieżącym
            port = current_port
    return port


def hours_to_destination(lat: float | None, lon: float | None,
                         sog: float | None, dest: str) -> float | None:
    """Ile godzin żeglugi do portu docelowego — haversine / prędkość z AIS.

    Poniżej 3 kn (dryf/kotwica/manewry) nie prognozujemy — dzielenie przez
    szum dawałoby setki godzin.

    ponytail: wielkie koło, nie trasa morska — zaniża gdy ląd po drodze
    (Gibraltar→Bałtyk ~1.5x); wystarcza jako rząd wielkości „~4 dni", upgrade
    do routingu morskiego (searoute) gdyby ktoś planował po tych godzinach."""
    coords = locate_destination(dest)
    if coords is None or lat is None or lon is None or not sog or sog < 3:
        return None
    return round(haversine_nm(lat, lon, *coords) / sog, 1)

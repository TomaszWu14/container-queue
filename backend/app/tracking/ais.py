"""Kolektor AIS (aisstream.io): pozycje STATKÓW z kolejki na żywo.

Uzupełnienie osi zdarzeń kontenerów, nie zamiennik: AIS nie zna
kontenerów — zna statki. Kolejka trzyma nazwy statków przy kontenerach, więc:

1. bierzemy unikalne nazwy statków z aktywnych kontenerów,
2. dopasowujemy po ZNORMALIZOWANEJ nazwie z metadanych AIS (każda wiadomość
   aisstream niesie ShipName) i przy pierwszym trafieniu zapamiętujemy MMSI,
3. gdy wszystkie statki mają MMSI — subskrybujemy tylko ich pozycje (lekki
   strumień); dopóki są nieznane, jedziemy w trybie discovery na samych
   ShipStaticData (rzadsze wiadomości, znośny wolumen bez filtra).

aisstream.io to websocket (brak REST) — stąd pętla lifespan zamiast fetch().
"""
import asyncio
import datetime
import json
import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Container, TrackedVessel, VesselPortCall, VesselPosition, utcnow
from .geo import hours_to_destination, resolve_port

logger = logging.getLogger(__name__)

# świat w formacie aisstream: [[[lat_min, lon_min], [lat_max, lon_max]]]
WORLD_BBOX = [[[-90.0, -180.0], [90.0, 180.0]]]
MMSI_FILTER_MAX = 50   # limit aisstream na FiltersShipMMSI
AIS_MAX_BACKOFF_SECONDS = 15 * 60  # sufit eskalacji błędów sesji


# 20'GP, 40'NOR, 45'HC, a także bez separatora: 20GP, 40HC. Apostrof opcjonalny, ale
# sufiks z zamkniętej listy — wzorzec [A-Z0-9]{2,4} bez apostrofu zjadłby realny token
# nazwy statku (np. „4EVER”), a nazwa bez statku to statek, który nigdy się nie pokaże.
_CONTAINER_TYPE = re.compile(
    r"^\d{1,2}'(?:[A-Z0-9]{2,4})$|^\d{1,2}(?:GP|HC|HQ|DC|DV|NOR|RF|RH|OT|FR|TK|PW)$")


def normalize_name(name: str) -> str:
    """Nazwa statku porównywalna między kolejką a AIS.

    Dwa źródła brudu: AIS dopełnia nazwy '@' i spacjami; kolejka bywa wypełniana
    ręcznie z doklejonym typem kontenera („20'GP - MV DEMO CORAL", „MV DEMO FJORD - 40'NOR").
    Myślniki lecą do spacji (obustronnie, więc dopasowanie zostaje symetryczne),
    tokeny typu kontenera wypadają."""
    raw = (name.replace("@", " ").replace("-", " ")
           .replace("’", "'").replace("ʼ", "'").replace("`", "'")
           .upper().split())
    return " ".join(tok for tok in raw if not _CONTAINER_TYPE.match(tok))


# retencja punktów trasy: mapa rysuje bieżący rejs, a rejs Azja→Europa to ~6 tygodni.
# ponytail: stała, nie ustawienie — nikt tego nie stroi, a tabela rośnie w każdym cyklu.
POSITION_RETENTION_DAYS = 60


def prune_positions(db: Session, days: int = POSITION_RETENTION_DAYS) -> int:
    """Kasuje punkty trasy starsze niż `days`; zwraca liczbę skasowanych wierszy.

    Bez tego vessel_positions rośnie bez końca — nic jej nie czyściło, a każdy
    ruch statku o ~2 km dokłada wiersz."""
    cutoff = utcnow() - datetime.timedelta(days=days)
    deleted = db.query(VesselPosition).filter(VesselPosition.at < cutoff).delete()
    db.commit()
    if deleted:
        logger.info("AIS: retencja — skasowano %s punktów trasy starszych niż %s dni",
                    deleted, days)
    return deleted


def group_by_vessel(containers) -> dict[str, list[Container]]:
    """Kontenery pogrupowane po znormalizowanej nazwie statku.

    Jedno źródło reguły dopasowania (fix review: liczona w 3 miejscach) —
    wołający decyduje o zakresie (scoped/unscoped) przez to, co poda."""
    by_vessel: dict[str, list[Container]] = {}
    for c in containers:
        name = normalize_name(c.vessel)
        if name:
            by_vessel.setdefault(name, []).append(c)
    return by_vessel


def format_container_list(containers, limit: int = 5) -> str:
    """'MSCU…, TCLU… (+3)' — wspólny format list kontenerów w alertach."""
    nos = ", ".join(c.container_no for c in containers[:limit])
    more = f" (+{len(containers) - limit})" if len(containers) > limit else ""
    return nos + more


def earliest_eta(aboard) -> datetime.date | None:
    """Najwcześniejsze ETA wśród kontenerów na pokładzie — punkt odniesienia dla
    dryfu ETA i predykcji spóźnienia (drift = najgorszy przypadek na statku)."""
    etas = [c.eta for c in aboard if c.eta]
    return min(etas) if etas else None


def predicted_late(vessel: TrackedVessel, aboard) -> bool:
    """Predykcja PRZED faktem: pozycja+prędkość mówią, że statek fizycznie nie
    zdąży na najwcześniejsze ETA kontenera (niezależnie od deklarowanego AIS-ETA)."""
    hours = hours_to_destination(vessel.lat, vessel.lon, vessel.sog, vessel.destination)
    eta = earliest_eta(aboard)
    if hours is None or eta is None:
        return False
    predicted = (utcnow() + datetime.timedelta(hours=hours)).date()
    return predicted > eta


def active_vessel_names(db: Session) -> set[str]:
    """Unikalne, znormalizowane nazwy statków z niedostarczonych kontenerów."""
    rows = db.scalars(
        select(Container.vessel).distinct()
        .where(Container.vessel != "",
               Container.status.notin_(Container.FINISHED))).all()
    return {normalize_name(v) for v in rows if normalize_name(v)}


def sync_vessel_rows(db: Session, names: set[str]) -> dict[str, TrackedVessel]:
    """Dosiewa brakujące wiersze tracked_vessels; zwraca mapę nazwa→wiersz.

    Wierszy statków, które wypadły z kolejki, nie kasujemy — MMSI to zdobyta
    wiedza, a statek często wraca w następnym rejsie."""
    existing = {v.name: v for v in db.scalars(select(TrackedVessel)).all()}
    for name in names:
        if name not in existing:
            vessel = TrackedVessel(name=name)
            db.add(vessel)
            existing[name] = vessel
    db.commit()
    return {n: existing[n] for n in names}


def build_subscription(api_key: str, mmsis: list[int], rotation: int = 0) -> dict:
    """Subskrypcja aisstream: z pełną listą MMSI — pozycje; bez — discovery.

    Discovery = same ShipStaticData (statek nadaje je co ~6 min, wolumen bez
    filtra jest znośny; PositionReport bez filtra to tysiące wiadomości/s).

    Ponad limit filtra (50) kolejne sesje (`rotation`) biorą kolejne paczki
    z posortowanej listy — dawniej nadmiarowe statki (wybór wg kolejności słownika)
    trwale nie dostawały pozycji i zamrażały lat/lon/near_port."""
    sub: dict = {"APIKey": api_key, "BoundingBoxes": WORLD_BBOX}
    if mmsis:
        ordered = sorted(mmsis)
        if len(ordered) > MMSI_FILTER_MAX:
            start = rotation * MMSI_FILTER_MAX % len(ordered)
            ordered = (ordered + ordered)[start:start + MMSI_FILTER_MAX]
            logger.info("AIS: %s statków > limit filtra %s — paczka od %s (rotacja)",
                        len(mmsis), MMSI_FILTER_MAX, start)
        sub["FiltersShipMMSI"] = [str(m) for m in ordered]
        sub["FilterMessageTypes"] = ["PositionReport", "ShipStaticData"]
    else:
        sub["FilterMessageTypes"] = ["ShipStaticData"]
    return sub


def next_backoff(prev: float, base: float = 60.0,
                 max_backoff: float = AIS_MAX_BACKOFF_SECONDS,
                 jitter_fn=random.uniform) -> float:
    """Wykładniczy backoff (x2, sufit max_backoff) + jitter ±20% — rozbija efekt stada,
    gdy wiele instancji dostaje błąd tej samej sesji naraz. prev<=0 = pierwszy błąd (base)."""
    raw = min(max_backoff, base if prev <= 0 else prev * 2)
    return raw * jitter_fn(0.8, 1.2)


def ais_eta_to_datetime(eta: dict | None, now: datetime.datetime) -> datetime.datetime | None:
    """AIS ETA nie ma roku (Month/Day/Hour/Minute) — dobieramy najbliższy sensowny.

    Miesiąc „daleko wstecz" względem dziś oznacza przyszły rok (styczniowe ETA
    raportowane w grudniu). Zera/braki w polach = ETA nieustawione."""
    if not eta:
        return None
    month, day = eta.get("Month") or 0, eta.get("Day") or 0
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    hour = min(eta.get("Hour") or 0, 23)      # AIS używa 24 jako „brak godziny"
    minute = min(eta.get("Minute") or 0, 59)  # analogicznie 60
    year = now.year + (1 if month < now.month - 6 else 0)
    try:
        return datetime.datetime(year, month, day, hour, minute)
    except ValueError:  # np. 31 lutego z uszkodzonej ramki
        return None


def handle_message(db: Session, raw: str | bytes,
                   wanted: dict[str, TrackedVessel]) -> bool:
    """Aktualizuje wiersz statku, jeśli wiadomość dotyczy statku z kolejki."""
    try:
        msg = json.loads(raw)
    except (ValueError, TypeError):
        return False
    meta = msg.get("MetaData") or {}
    vessel = wanted.get(normalize_name(meta.get("ShipName") or ""))
    if vessel is None:
        return False

    now = utcnow()
    _learn_mmsi(db, vessel, meta)
    handler = _HANDLERS.get(msg.get("MessageType"))
    if handler is None:
        return False
    handler(db, vessel, msg.get("Message") or {}, meta, now)
    try:
        db.commit()
    except IntegrityError:
        # jedna zła wiadomość (np. wyścig na unikalnym mmsi) nie może ubić sesji —
        # rollback i porzucamy tę wiadomość, kolejne wciąż się przetworzą
        db.rollback()
        logger.warning("AIS: commit wiadomości nie powiódł się (IntegrityError) — pomijam")
        return False
    return True


def _learn_mmsi(db: Session, vessel: TrackedVessel, meta: dict) -> None:
    if vessel.mmsi is not None or not meta.get("MMSI"):
        return
    new_mmsi = int(meta["MMSI"])
    # mmsi jest unique — statek, który zmienił nazwę AIS, może już mieć wiersz
    # pod innym MMSI-właścicielem; zamiast łapać IntegrityError, sprawdzamy
    # taniej z góry i po prostu nie uczymy się (kolejna wiadomość i tak wróci)
    conflict = db.scalar(select(TrackedVessel.id)
                         .where(TrackedVessel.mmsi == new_mmsi,
                                TrackedVessel.id != vessel.id))
    if conflict:
        logger.warning("AIS: MMSI %s już przypisane innemu wierszowi (id=%s) — "
                       "pomijam dla %s", new_mmsi, conflict, vessel.name)
    else:
        vessel.mmsi = new_mmsi
        logger.info("AIS: nauczono MMSI %s dla statku %s", vessel.mmsi, vessel.name)


def _apply_position(db: Session, vessel: TrackedVessel, body: dict, _meta: dict,
                    now: datetime.datetime) -> None:
    report = body.get("PositionReport") or {}
    new_lat, new_lon = report.get("Latitude"), report.get("Longitude")
    # linia przebyta: dopisujemy punkt trasy, gdy statek realnie się przesunął
    # (~2 km; próg tnie szum kotwicowiska i objętość tabeli). ponytail: odległość
    # w stopniach zamiast haversine — przy tym progu różnica bez znaczenia.
    if (new_lat is not None and new_lon is not None
            and (vessel.lat is None
                 or abs(new_lat - vessel.lat) + abs(new_lon - vessel.lon) > 0.02)):
        db.add(VesselPosition(vessel_id=vessel.id, lat=new_lat, lon=new_lon, at=now))
    vessel.lat = new_lat
    vessel.lon = new_lon
    vessel.sog = report.get("Sog")
    vessel.cog = report.get("Cog")
    vessel.last_seen = now
    # geofence: wejście w promień portu = milestone "statek dopłynął w rejon
    # portu" (sugestia zmiany statusów kontenerów); wyjście czyści stan
    port = None
    if new_lat is not None and new_lon is not None:
        port = resolve_port(vessel.near_port, new_lat, new_lon)
    if (port or "") != vessel.near_port:
        _change_port(db, vessel, port, now)


def _change_port(db: Session, vessel: TrackedVessel, port: str | None,
                 now: datetime.datetime) -> None:
    """Zmiana strefy portu: domknij otwarty postój, otwórz nowy, powiadom o wejściu."""
    if vessel.near_port:   # zmiana lub wyjście — domknij otwarty postój
        open_call = db.scalars(
            select(VesselPortCall)
            .where(VesselPortCall.vessel_id == vessel.id,
                   VesselPortCall.port == vessel.near_port,
                   VesselPortCall.departed_at.is_(None))
            .order_by(VesselPortCall.id.desc())).first()
        if open_call:
            open_call.departed_at = now
    if port:
        db.add(VesselPortCall(vessel_id=vessel.id, port=port, arrived_at=now))
    vessel.near_port = port or ""
    vessel.near_port_since = now if port else None
    if port:
        _notify_port_arrival(db, vessel, port)


def _apply_static(_db: Session, vessel: TrackedVessel, body: dict, meta: dict,
                  now: datetime.datetime) -> None:
    static = body.get("ShipStaticData") or {}
    vessel.destination = (static.get("Destination") or "").strip()[:80]
    if vessel.imo is None and static.get("ImoNumber"):
        vessel.imo = int(static["ImoNumber"])
    vessel.ais_eta = ais_eta_to_datetime(static.get("Eta"), now) or vessel.ais_eta
    # wymiary: Dimension A/B (od anteny do dziobu/rufy) i C/D (do burt) —
    # długość = A+B, szerokość = C+D; zera = nadajnik nie zna wymiarów
    dim = static.get("Dimension") or {}
    length = (dim.get("A") or 0) + (dim.get("B") or 0)
    beam = (dim.get("C") or 0) + (dim.get("D") or 0)
    if length > 0:
        vessel.length_m = int(length)
    if beam > 0:
        vessel.beam_m = int(beam)
    vessel.last_seen = now
    # metadane ShipStaticData też niosą pozycję — discovery od razu daje punkt
    if vessel.lat is None and meta.get("latitude") is not None:
        vessel.lat, vessel.lon = meta.get("latitude"), meta.get("longitude")


# CODE-004: dispatch po typie komunikatu AIS zamiast jednego łańcucha if/elif
_HANDLERS = {"PositionReport": _apply_position, "ShipStaticData": _apply_static}


def _notify_port_arrival(db: Session, vessel: TrackedVessel, port: str) -> None:
    """Milestone geofence do obserwatorów kontenerów na pokładzie (best-effort) —
    każdy odbiorca widzi tylko kontenery swojego zakresu (notify_aboard)."""
    try:
        from ..notifications import notify_aboard
        aboard = group_by_vessel(db.scalars(
            select(Container).where(Container.vessel != "",
                                    Container.status.notin_(Container.FINISHED))).all()
        ).get(vessel.name, [])
        notify_aboard(db, aboard, kind="vessel_port", render=lambda group: (
            f"Statek {vessel.name} w rejonie portu {port} — "
            f"kontenery: {format_container_list(group)}. Sprawdź statusy.", ""))
    except Exception:  # noqa: BLE001 — milestone nie może wywrócić kolektora
        logger.exception("Geofence notify failed")


async def run_session(db_factory, deadline_seconds: float, *,
                      prefer_positions: bool = False, rotation: int = 0) -> bool:
    """Jedna sesja websocket: subskrypcja wg bieżącej kolejki, odbiór do deadline'u.

    prefer_positions=True wymusza tryb pozycji na znanych MMSI, nawet gdy część
    statków wciąż jest nieznana — bez tego jedna literówka w nazwie (nigdy nie
    dopasuje się w AIS) głodziłaby znane statki wiecznym discovery.

    Zwraca True, gdy sesja subskrybowała pozycje — tylko wtedy ais_loop
    przesuwa rotację paczek MMSI."""
    import websockets  # import lokalny — moduł zbędny, gdy AIS wyłączony

    # Praca na bazie (zapytania, commit per wiadomość, geofence → notify_aboard) poza pętlą
    # zdarzeń — wolna baza nie może blokować event loopa całej aplikacji. Session SQLAlchemy
    # nie jest thread-safe, więc CAŁA sesja żyje w jednym wątku roboczym (executor 1-wątkowy).
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="ais-db") as db_thread:
        def in_db(fn, *args):
            return loop.run_in_executor(db_thread, fn, *args)

        db = await in_db(db_factory)
        try:
            prepared = await in_db(_prepare_session, db, prefer_positions, rotation)
            if prepared is None:
                return False
            wanted, sub, discovery = prepared
            loop_deadline = loop.time() + deadline_seconds
            async with websockets.connect(settings.aisstream_url) as ws:
                await ws.send(json.dumps(sub))
                while True:
                    remaining = loop_deadline - loop.time()
                    if remaining <= 0:
                        break
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    except TimeoutError:
                        break
                    await in_db(handle_message, db, raw, wanted)
        finally:
            await in_db(db.close)
    return not discovery


def _prepare_session(db: Session, prefer_positions: bool, rotation: int):
    """Lista statków + subskrypcja (wątek bazy) → (wanted, sub, discovery) albo None."""
    names = active_vessel_names(db)
    if not names:
        return None
    wanted = sync_vessel_rows(db, names)
    prune_positions(db)   # raz na sesję wystarczy — tabela rośnie wolno
    mmsis = [v.mmsi for v in wanted.values() if v.mmsi is not None]
    discovery = len(mmsis) < len(wanted) and not (prefer_positions and mmsis)
    sub = build_subscription(settings.aisstream_api_key, [] if discovery else mmsis, rotation)
    logger.info("AIS: sesja %s, statków %s (znane MMSI: %s)",
                "discovery" if discovery else "positions", len(wanted), len(mmsis))
    return wanted, sub, discovery


async def ais_loop() -> None:
    """Pętla lifespan: sesja → (błąd? backoff) → nowa sesja ze świeżą listą statków.

    Co druga sesja wymusza tryb pozycji (prefer_positions) — statki ze zdobytym
    MMSI dostają pozycje na żywo, a discovery dla nieznanych wraca naprzemiennie."""
    from ..database import SessionLocal
    from ..jobs import job_lock
    flip = False
    backoff = 0.0
    rotation = 0   # kolejna paczka MMSI przy > 50 statkach (patrz build_subscription)
    while True:
        try:
            # ARCH-003: jeden kolektor na bazę (limit połączeń klucza aisstream) — gdy
            # sesję trzyma inny proces, ten czeka jak po pustej sesji i próbuje znowu
            # pg_try_advisory_lock to też I/O bazy — wejście/wyjście z locka poza event loopem
            stack = ExitStack()
            got = await asyncio.to_thread(stack.enter_context, job_lock("ais"))
            try:
                positions = (await run_session(SessionLocal, settings.ais_resubscribe_seconds,
                                               prefer_positions=flip, rotation=rotation)
                             if got else False)
            finally:
                await asyncio.to_thread(stack.close)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — pętla tła nie może paść od błędu sesji
            logger.exception("AIS session failed")
            backoff = next_backoff(backoff, settings.ais_error_backoff_seconds)
            await asyncio.sleep(backoff)
        else:
            # pusta kolejka (return bez połączenia) — nie młócimy w kółko; sesja udana
            # (nawet pusta) resetuje eskalację backoffu
            backoff = 0.0
            # rotacja tylko po sesji pozycji: w trybie mieszanym pozycje idą co drugą
            # sesję — wspólny licznik dawałby im same nieparzyste rotacje i przy
            # N=100 dolna paczka 50 MMSI nigdy nie dostałaby pozycji
            if positions:
                rotation += 1
            await asyncio.sleep(min(60.0, settings.ais_error_backoff_seconds))
        flip = not flip

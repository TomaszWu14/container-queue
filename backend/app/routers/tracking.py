"""Tracking: oś zdarzeń kontenera, statki AIS, pogoda, kongestia portów, mapa."""
from ..models import today_pl
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import AdminOnly as admin_only
from ..deps import ViewerOrSales as viewer_or_sales
from ..models import TrackedVessel, TrackingEvent, User
from ..schemas import TimelineEntryOut, TrackedVesselOut, TrackingEventOut
from ..tracking.timeline import build_timeline
from .containers import get_container_checked
from .containers_common import hidden_fields

router = APIRouter(prefix="/api", tags=["tracking"])


@router.get("/containers/{container_id}/events", response_model=list[TrackingEventOut])
def container_events(container_id: int, db: Session = Depends(get_db), user: User = viewer_or_sales):
    get_container_checked(db, container_id, user)
    return db.scalars(
        select(TrackingEvent)
        .where(TrackingEvent.container_id == container_id)
        .order_by(TrackingEvent.occurred_at.asc().nulls_last(), TrackingEvent.id)).all()


@router.get("/containers/{container_id}/timeline", response_model=list[TimelineEntryOut])
def container_timeline(container_id: int, db: Session = Depends(get_db), user: User = viewer_or_sales):
    container = get_container_checked(db, container_id, user)
    return build_timeline(db, container, hide_orders="order_number" in hidden_fields(user))


@router.get("/tracking/vessels", response_model=list[TrackedVesselOut])
def tracked_vessels(db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Pozycje AIS statków z aktywnej kolejki + trasa przebyta, spółki i pilność.

    Zwracamy tylko statki obecne w niedostarczonych kontenerach — tabela trzyma
    też historyczne wiersze (zdobyte MMSI), których nie ma po co pokazywać."""
    from ..deps import scope_containers
    from ..models import Container, VesselPosition, WatchedContainer, WatchedVessel
    from ..tracking.ais import earliest_eta, group_by_vessel, predicted_late
    from .watchers import watchers_by_target

    # izolacja per-zasób: statki wyprowadzamy WYŁĄCZNIE z kontenerów w zakresie
    # usera (fix review: unscoped active_vessel_names ujawniał pozycje statków
    # z cudzym ładunkiem każdemu viewerowi)
    containers = db.scalars(scope_containers(
        select(Container).where(Container.vessel != "",
                                Container.status.notin_(Container.FINISHED)), user)).all()
    by_vessel = group_by_vessel(containers)
    if not by_vessel:
        return []
    vessels = db.scalars(
        select(TrackedVessel).where(TrackedVessel.name.in_(by_vessel.keys()))
        .order_by(TrackedVessel.name)).all()

    # trasy jednym zapytaniem (zamiast N) — punkty rosną chronologicznie po id
    rows = db.execute(
        select(VesselPosition.vessel_id, VesselPosition.lat, VesselPosition.lon)
        .where(VesselPosition.vessel_id.in_([v.id for v in vessels]))
        .order_by(VesselPosition.vessel_id, VesselPosition.id)).all()
    trails: dict[int, list[list[float]]] = {}
    for vid, lat, lon in rows:
        trails.setdefault(vid, []).append([lat, lon])
    watch = watchers_by_target(db, WatchedVessel, WatchedVessel.vessel_id,
                               [v.id for v in vessels], user)
    # gwiazdka nad statkiem: obserwacje ZALOGOWANEGO usera (per user, jak „Moje") —
    # tylko kontenery z zakresu (aboard pochodzi z scope_containers)
    my_reasons = dict(db.execute(
        select(WatchedContainer.container_id, WatchedContainer.reason)
        .where(WatchedContainer.user_id == user.id,
               WatchedContainer.container_id.in_([c.id for c in containers]))).all())

    out = []
    for v in vessels:
        aboard = by_vessel.get(v.name, [])
        companies = sorted({("TRANZYT" if c.is_transit else (c.company.code if c.company else "?"))
                            for c in aboard})
        # ETA drift: o ile dni ETA statku z AIS wyprzedza NAJWCZEŚNIEJSZE ETA
        # kontenera na pokładzie (drift per statek = najgorszy przypadek)
        drift_days = None
        earliest = earliest_eta(aboard)
        if v.ais_eta is not None and earliest is not None:
            drift_days = (v.ais_eta.date() - earliest).days
        out.append(TrackedVesselOut(
            id=v.id, name=v.name, mmsi=v.mmsi, imo=v.imo, lat=v.lat, lon=v.lon, sog=v.sog,
            cog=v.cog, destination=v.destination, ais_eta=v.ais_eta,
            last_seen=v.last_seen,
            trail=trails.get(v.id, [])[-200:],   # ogon tnie payload przy długich rejsach
            companies=companies,
            containers=len(aboard),
            delayed=sum(1 for c in aboard if c.is_delayed),
            drift_days=drift_days,
            eta_alert=(drift_days is not None
                       and drift_days >= settings.tracking_eta_alert_days),
            near_port=v.near_port,
            predicted_late=predicted_late(v, aboard),
            length_m=v.length_m, beam_m=v.beam_m, has_photo=bool(v.photo),
            hours_to_dest=hours_to_destination(v.lat, v.lon, v.sog, v.destination),
            watchers=watch.get(v.id, []),
            watched=[{"id": c.id, "container_no": c.container_no, "reason": my_reasons[c.id]}
                     for c in aboard if c.id in my_reasons]))
    return out


def get_vessel_visible(db: Session, vessel_id: int, user: User):
    """Statek + jego kontenery W ZAKRESIE usera; statek bez naszego ładunku → 404.

    Jedno miejsce reguły widoczności statku (historia portów, karta, cargo, zdjęcie) —
    izolacja wyprowadzona WYŁĄCZNIE przez scope_containers (deps.py)."""
    from ..deps import scope_containers
    from ..models import Container
    from ..tracking.ais import group_by_vessel

    vessel = db.get(TrackedVessel, vessel_id)
    if vessel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    containers = db.scalars(scope_containers(
        select(Container).where(Container.vessel != "",
                                Container.status.notin_(Container.FINISHED)), user)).all()
    aboard = group_by_vessel(containers).get(vessel.name)
    if not aboard:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return vessel, aboard


# --- karta statku: nasze kontenery + zawartość (pozycje zamówień) ---

@router.get("/tracking/vessels/{vessel_id}/cargo")
def vessel_cargo(vessel_id: int, db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Kontenery usera na pokładzie + pozycje zamówień (akordeon karty statku).

    Izolacja: kontenery TYLKO z scope_containers (get_vessel_visible). Pozycje
    zamówień to dane handlowe — warehouse/customs dostają listę kontenerów bez
    pozycji (spójnie z /containers/{id}/items)."""
    from ..models import Order, OrderItem, Role
    from .containers import container_order_numbers

    _, aboard = get_vessel_visible(db, vessel_id, user)
    items_allowed = user.role not in (Role.warehouse, Role.customs)
    numbers_of: dict[int, list[str]] = {}
    by_key: dict[tuple[int, str], list] = {}
    if items_allowed:
        # PO do identity map jednym zapytaniem — c.order w container_order_numbers bez SQL
        # (referencja trzyma obiekty: identity map jest słaba)
        orders = db.scalars(select(Order).where(Order.id.in_({c.order_id for c in aboard}))).all()  # noqa: F841
        numbers_of = {c.id: container_order_numbers(c) for c in aboard}
        all_numbers = {n for ns in numbers_of.values() for n in ns}
        # pozycje wszystkich kontenerów jednym zapytaniem (nie N+1), dopasowanie spółka+numer
        if all_numbers:
            for i in db.scalars(
                    select(OrderItem)
                    .where(OrderItem.company_id.in_({c.company_id for c in aboard}),
                           OrderItem.order_number.in_(all_numbers))
                    .order_by(OrderItem.order_number, OrderItem.position)):
                by_key.setdefault((i.company_id, i.order_number), []).append(i)
    out = []
    for c in sorted(aboard, key=lambda x: x.container_no):
        items = [{"material": i.material, "description": i.description,
                  "quantity": i.quantity, "unit": i.unit}
                 for n in numbers_of.get(c.id, []) for i in by_key.get((c.company_id, n), [])]
        out.append({
            "id": c.id, "container_no": c.container_no,
            "company": "TRANZYT" if c.is_transit else (c.company.code if c.company else "?"),
            "status": c.status.value, "eta": c.eta.isoformat() if c.eta else None,
            "is_special": c.is_special, "items": items,
        })
    return {"containers": out, "items_visible": items_allowed}


# --- zdjęcie statku: upload admina + auto-fetch z Wikimedia Commons, pliki
#     w uploads/vessels/ (poza katalogiem załączników kontenerowych) ---

def vessel_photos_dir():
    import pathlib
    path = pathlib.Path(settings.uploads_dir) / "vessels"
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.get("/tracking/vessels/{vessel_id}/photo")
def vessel_photo(vessel_id: int, db: Session = Depends(get_db), user: User = viewer_or_sales):
    from fastapi.responses import FileResponse

    vessel, _ = get_vessel_visible(db, vessel_id, user)
    path = vessel_photos_dir() / vessel.photo if vessel.photo else None
    if path is None or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brak zdjęcia statku.")
    # Content-Type ustalony przy zapisie (tylko obrazy przechodzą walidację sygnatur)
    return FileResponse(path, media_type="image/jpeg" if path.suffix != ".png" else "image/png")


def _store_vessel_photo(db: Session, vessel: TrackedVessel, content: bytes) -> None:
    """Walidacja sygnatury + zapis pliku pod losową nazwą + podmiana starego zdjęcia."""
    import secrets

    from .complaints import _looks_like_image

    if not _looks_like_image(content[:16]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Dozwolone są tylko obrazy (JPG/PNG/WEBP/GIF).")
    ext = ".png" if content.startswith(b"\x89PNG") else ".jpg"
    stored = f"v{vessel.id}_{secrets.token_hex(8)}{ext}"
    old = vessel.photo
    vessel.photo = stored
    from .forwarding import commit_with_file
    commit_with_file(db, vessel_photos_dir() / stored, content)
    if old:
        (vessel_photos_dir() / old).unlink(missing_ok=True)


@router.post("/tracking/vessels/{vessel_id}/photo", status_code=status.HTTP_201_CREATED)
def upload_vessel_photo(vessel_id: int, file: UploadFile,
                              db: Session = Depends(get_db), user: User = admin_only):
    from .forwarding import read_upload_capped

    vessel = db.get(TrackedVessel, vessel_id)
    if vessel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    content = read_upload_capped(file, settings.max_upload_mb, "Zdjęcie")
    _store_vessel_photo(db, vessel, content)
    return {"has_photo": True}


@router.post("/tracking/vessels/{vessel_id}/photo/fetch",
             status_code=status.HTTP_201_CREATED)
def fetch_vessel_photo(vessel_id: int, db: Session = Depends(get_db),
                       user: User = admin_only):
    """Auto-pobranie miniatury z Wikimedia Commons (jedyne zbadane źródło bez klucza
    i bez łamania licencji — VesselFinder/MarineTraffic wymagają licencji API).

    Szukamy po „IMO {imo}" (Commons kategoryzuje zdjęcia statków numerem IMO);
    brak trafienia → 404 i zostaje upload ręczny/placeholder."""
    import httpx

    vessel = db.get(TrackedVessel, vessel_id)
    if vessel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not vessel.imo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Statek nie ma jeszcze numeru IMO (AIS się uczy).")
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"IMO {vessel.imo}", "gsrnamespace": 6, "gsrlimit": 1,
        "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 640,
    }
    try:
        with httpx.Client(timeout=10.0,
                          headers={"User-Agent": "timporye/1.0 (vessel photo)"}) as client:
            data = client.get("https://commons.wikimedia.org/w/api.php",
                              params=params).raise_for_status().json()
            pages = (data.get("query") or {}).get("pages") or {}
            thumb = next((p["imageinfo"][0].get("thumburl")
                          for p in pages.values() if p.get("imageinfo")), None)
            if not thumb:
                raise HTTPException(status.HTTP_404_NOT_FOUND,
                                    "Nie znaleziono zdjęcia dla tego IMO na Wikimedia Commons.")
            content = client.get(thumb).raise_for_status().content
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Nie udało się pobrać zdjęcia: {exc}") from exc
    _store_vessel_photo(db, vessel, content)
    return {"has_photo": True}


# --- pogoda przy statkach: proxy open-meteo (wiatr + fala), cache w tracking/weather.py ---

@router.get("/tracking/weather")
def vessel_weather(db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Wiatr i fala w pozycjach śledzonych statków — przycięte do statków
    widocznych dla usera (izolacja per-zasób jak w tracked_vessels)."""
    from ..deps import scope_containers
    from ..models import Container
    from ..tracking import weather
    from ..tracking.ais import group_by_vessel

    # statki widoczne dla usera — wyprowadzone WYŁĄCZNIE z jego kontenerów
    containers = db.scalars(scope_containers(
        select(Container).where(Container.vessel != "",
                                Container.status.notin_(Container.FINISHED)), user)).all()
    visible_names = set(group_by_vessel(containers).keys())
    if not visible_names:
        return []
    visible_ids = set(db.scalars(
        select(TrackedVessel.id).where(TrackedVessel.name.in_(visible_names))).all())
    return [x for x in weather.fetch_weather(db) if x["vessel_id"] in visible_ids]


# --- kongestia portów: trend 14 dni + alert 2× mediana (zapis w tracking_loop) ---

@router.get("/tracking/congestion")
def port_congestion(db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Trend kongestii per port (ostatnie 14 dni) do mini-wykresu przy chipie portu.

    Zwraca wyłącznie zagregowane liczniki statków per port — bez nazw statków,
    kontenerów i spółek, więc nie zdradza cudzego ładunku (dlatego bez scope)."""
    import datetime as _dt
    import statistics

    from ..models import PortCongestion
    from ..tracking.congestion import MIN_HISTORY_DAYS, TREND_DAYS

    today = today_pl()
    since = today - _dt.timedelta(days=TREND_DAYS)
    rows = db.scalars(select(PortCongestion).where(PortCongestion.day >= since)
                      .order_by(PortCongestion.port, PortCongestion.day)).all()
    by_port: dict[str, list[PortCongestion]] = {}
    for r in rows:
        by_port.setdefault(r.port, []).append(r)
    out = []
    for port, items in by_port.items():
        current = next((r.waiting for r in items if r.day == today), None)
        history = [r.waiting for r in items if r.day != today]
        median = statistics.median(history) if history else 0
        alert = (current is not None and len(history) >= MIN_HISTORY_DAYS
                 and median > 0 and current > 2 * median)
        out.append({"port": port, "alert": alert,
                    "days": [{"day": r.day.isoformat(), "waiting": r.waiting}
                             for r in items]})
    return out


# --- mapa śledzenia: pozycje kontenerów wg ostatniego zdarzenia ---

# geografia portów przeniesiona do tracking/geo.py (kolektor AIS też z niej korzysta);
# re-eksport locate_destination utrzymuje import w testach (test_ais)
from ..tracking.geo import (  # noqa: E402, I001
    hours_to_destination,
    locate,
    locate_destination,  # noqa: F401
)


@router.get("/tracking/map")
def tracking_map(db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Punkty na mapę: ostatnie znane położenie każdego ŚLEDZONEGO kontenera.

    Śledzony = service.TRACKED (numer RF + numer kontenera), jeszcze nie rozładowany (poza Container.FINISHED). Wcześniej mapa brała WSZYSTKIE aktywne
    kontenery i te bez trackingu pinowała na porcie (setki „śledzonych" znikąd).
    """
    from ..deps import scope_containers
    from ..models import Container, WatchedContainer, utcnow
    from ..tracking.service import TRACKED
    from .watchers import watchers_by_target

    query = scope_containers(
        select(Container).where(
            Container.status.notin_(Container.FINISHED), TRACKED), user)  # rozładowany ≠ w drodze
    containers = db.scalars(query).all()
    ids = [c.id for c in containers]
    watch = watchers_by_target(db, WatchedContainer, WatchedContainer.container_id, ids, user)
    events = db.scalars(select(TrackingEvent)
                        .where(TrackingEvent.container_id.in_(ids))
                        .order_by(TrackingEvent.occurred_at.asc().nulls_first(),
                                  TrackingEvent.id)).all() if ids else []
    # pozycja = ostatnie FAKTYCZNE zdarzenie, które już nastąpiło — prognozy (ARRIVE
    # w porcie docelowym z datą w przyszłości) „teleportowały" kontener w rejsie do Gdańska
    now = utcnow()
    last_event: dict[int, TrackingEvent] = {}
    etd: dict[int, str] = {}
    etd_estimated: dict[int, str] = {}
    for event in events:
        is_fact = not event.is_estimated and (event.occurred_at is None
                                              or event.occurred_at <= now)
        if is_fact:
            last_event[event.container_id] = event
        if event.event_code == "DEPART" and event.occurred_at:
            # ETD z faktycznego wyjścia; prognoza tylko gdy faktu jeszcze nie ma
            target = etd if is_fact else etd_estimated
            target.setdefault(event.container_id, event.occurred_at.date().isoformat())
    etd = {**etd_estimated, **etd}

    points, unlocated = [], []
    for c in containers:
        event = last_event.get(c.id)
        location = event.location if event else (c.port.name if c.port else "")
        entry = {
            "id": c.id, "container_no": c.container_no, "vessel": c.vessel,
            "is_special": c.is_special,
            "status": c.status.value, "eta": c.eta.isoformat() if c.eta else None,
            "etd": etd.get(c.id),
            "location": location,
            "event": event.description if event else "",
            "occurred_at": event.occurred_at.isoformat() if event and event.occurred_at else None,
            "watchers": watch.get(c.id, []),
        }
        coords = locate(location)
        if coords:
            entry["lat"], entry["lon"] = coords
            points.append(entry)
        elif event or location:
            unlocated.append(entry)
    return {"points": points, "unlocated": unlocated,
            "tracked": len(points) + len(unlocated), "total": len(containers)}

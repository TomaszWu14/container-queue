"""Pulpit, statystyki (miesięczne, transit time, obłożenie) i analizy rozładunków."""
from ..models import today_pl
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, extract, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import NonWarehouseViewers as non_warehouse
from ..deps import Viewer as viewer
from ..deps import check_company_access, scope_containers
from ..holidays import is_free_day
from ..models import (
    CUSTOMS_IN_PROGRESS,
    Company,
    Container,
    ContainerStatus,
    DocumentStatus,
    Port,
    SapOrder,
    TrackingEvent,
    User,
    Warehouse,
)
from ..schemas import (
    MonthlyStat,
    OccupancyForecastOut,
    OccupancyWeek,
    TransitTrendOut,
    TransitTrendPoint,
    TransitTrendPort,
)
from ..signals import SIGNAL_WEIGHTS, compute_signals
from .containers_common import daily_limits_map, hidden_fields, mask_row
from .customer_orders import care_risk_by_company

# sub-router bez prefiksu — podpinany w routers/containers.py (prefiks /api, tag kolejka)
router = APIRouter()

# pulpit pokazuje tylko nazwy spółki/dostawcy/portu — bez 6 pozostałych relacji z _LOAD
_BRIEF = (selectinload(Container.company), selectinload(Container.supplier),
          selectinload(Container.port))


# --- dashboard ---

@router.get("/stats/dashboard")
def dashboard(today: datetime.date | None = Query(
                  None, description="Lokalna data klienta (YYYY-MM-DD); brak = UTC"),
              db: Session = Depends(get_db), user: User = non_warehouse):
    """Kafelki dashboardu + listy wymagające uwagi (w zakresie użytkownika)."""
    from ..notifications import demurrage_deadlines

    # „dziś" rządzi zegar użytkownika (W4); strefy to max ±1 dzień od UTC — reszta to śmieć
    utc_today = today_pl()
    if today is None or abs((today - utc_today).days) > 1:
        today = utc_today
    tomorrow = today + datetime.timedelta(days=1)

    def open_q(*cols):   # kolejka (bez ZREALIZOWANY) w zakresie usera — izolacja w deps
        return scope_containers(select(*cols).where(Container.open_in_queue()), user)

    # is_delayed liczy wg kalendarza PL (today_pl), nie zegara klienta — jak dotąd
    delayed_sql = Container.delayed_clause(utc_today)
    # PERF-003: kafelki = jedno COUNT … FILTER, zamiast hydratacji całej kolejki
    (n_today, n_tomorrow, n_transit, n_port, n_customs, n_delayed) = db.execute(open_q(
        func.count().filter(Container.notify_date == today),
        func.count().filter(Container.notify_date == tomorrow),
        func.count().filter(Container.status == ContainerStatus.W_TRANSPORCIE),
        func.count().filter(Container.status == ContainerStatus.W_PORCIE),
        func.count().filter(Container.customs_status.in_(CUSTOMS_IN_PROGRESS)),
        func.count().filter(delayed_sql))).one()

    def top15(clause):
        return db.scalars(open_q(Container).options(*_BRIEF).where(clause)
                          .order_by(Container.id).limit(15)).all()

    # #9: zamówienia SAP niepotwierdzone przez dostawcę po X dniach → mapa dla silnika
    orders_map: dict[int, dict] = {}
    po_days = SIGNAL_WEIGHTS["po_confirm_days"]
    for so in db.scalars(select(SapOrder).where(
            SapOrder.container_id.in_(open_q(Container.id)),
            SapOrder.supplier_confirmed.is_(False))):
        ref = so.doc_date or so.required_ship_date
        days = (today - ref).days if ref else 0
        if days >= po_days:
            cur = orders_map.get(so.container_id)
            if cur is None or days > cur["days"]:
                orders_map[so.container_id] = {"unconfirmed": True, "days": days}
    care = care_risk_by_company(
        db, set(db.scalars(open_q(Container.company_id).distinct())), today, user)

    # do sygnałów i demurrage ładujemy tylko kandydatów: NADZBIÓR warunków compute_signals
    # (silnik i tak sprawdza je dokładnie). Nowy typ sygnału = dopisz tu jego warunek.
    active = Container.status.in_((ContainerStatus.W_TRANSPORCIE, ContainerStatus.W_PORCIE))
    soon = today + datetime.timedelta(days=max(3, SIGNAL_WEIGHTS["demurrage_days"],
                                               SIGNAL_WEIGHTS["avizo_lead_days"]))
    arrived = select(TrackingEvent.container_id).where(   # termin od wyładunku (demurrage)
        TrackingEvent.event_code.in_(("DISCHARGE", "ARRIVE")),
        TrackingEvent.is_estimated.is_(False), TrackingEvent.occurred_at.is_not(None))
    candidates = db.scalars(open_q(Container).options(*_BRIEF).where(
        Container.status.not_in(Container.FINISHED),
        or_(Container.document_status == DocumentStatus.BRAK,
            delayed_sql,
            Container.eta <= soon,                       # demurrage od ETA, awizacja, utknięty
            Container.demurrage_free_days < 0,
            Container.id.in_(arrived),
            and_(active, Container.eta.is_(None)),       # brak ETA
            and_(active, Container.planning_eta_at_send.is_not(None),
                 Container.eta != Container.planning_eta_at_send),   # przesunięcie ETA
            Container.id.in_(list(orders_map)),
            Container.id.in_(list(care))))
        .order_by(Container.id)).all()

    deadlines = demurrage_deadlines(db, candidates)   # jedno zapytanie zamiast N+1
    demurrage_soon = []
    for c in candidates:
        deadline = deadlines[c.id]
        if deadline and (deadline - today).days <= 3:
            demurrage_soon.append((deadline, c))
    demurrage_soon.sort(key=lambda pair: pair[0])

    def delay_days(c: Container) -> int:
        # dni po terminie: najpierw po ETA (transport), inaczej po awizacji; 0 = na czas
        ref = c.eta if (c.eta and c.eta < today) else (
            c.notify_date if (c.notify_date and c.notify_date < today) else None)
        return (today - ref).days if ref else 0

    def brief(c: Container, extra: dict | None = None) -> dict:
        return mask_row({"id": c.id, "container_no": c.container_no,
                "supplier_name": c.supplier.name if c.supplier else None,
                "company_name": c.company.name if c.company else None,
                "port_name": c.port.name if c.port else None,
                "notify_date": c.notify_date.isoformat() if c.notify_date else None,
                "eta": c.eta.isoformat() if c.eta else None,
                "delay_days": delay_days(c),
                "status": c.status.value, **(extra or {})}, user)

    return {
        "today": n_today,
        "tomorrow": n_tomorrow,
        "in_transit": n_transit,
        "at_port": n_port,
        # None = rola nie widzi odprawy (spedytor, 2026-09-28) — pulpit chowa kafelek
        "customs_in_progress": None if "customs_status" in hidden_fields(user) else n_customs,
        "delayed": n_delayed,
        "delayed_list": [brief(c) for c in top15(delayed_sql)],
        "today_list": [brief(c) for c in top15(Container.notify_date == today)],
        "demurrage_list": [brief(c, {"deadline": deadline.isoformat()})
                           for deadline, c in demurrage_soon[:15]],
        # cap jak inne listy dashboardu; pełny scoring po stronie silnika
        "action_feed": [mask_row(s, user) for s in compute_signals(
            candidates, deadlines, today, orders=orders_map, care=care)[:50]],
    }


# --- raport: kontenery / miesiąc / spółka ---

@router.get("/stats/monthly", response_model=list[MonthlyStat])
def monthly_stats(db: Session = Depends(get_db), user: User = non_warehouse):
    year_col = extract("year", Container.notify_date)
    month_col = extract("month", Container.notify_date)
    query = (select(year_col, month_col, Container.company_id, Company.name,
                    func.count(Container.id))
             .join(Company, Company.id == Container.company_id)
             .where(Container.notify_date.is_not(None))
             .group_by(year_col, month_col, Container.company_id, Company.name)
             .order_by(year_col, month_col))
    query = scope_containers(query, user)
    return [MonthlyStat(year=int(y), month=int(m), company_id=cid,
                        company_name=name, count=count)
            for y, m, cid, name, count in db.execute(query).all()]


# --- #56 trend transit time (ETD→ATD) per miesiąc, ostatnie 12 mies. ---

def _transit_days_col(db: Session):
    """Różnica dni ATD-ETD jako wyrażenie SQL, zależnie od dialektu."""
    if db.get_bind().dialect.name == "sqlite":
        return func.julianday(Container.atd) - func.julianday(Container.etd)
    return Container.atd - Container.etd  # Postgres: date - date = integer dni


@router.get("/stats/transit-trend", response_model=TransitTrendOut)
def transit_trend(db: Session = Depends(get_db), user: User = viewer):
    """Średni czas transportu (ETD→ATD) zakończonych kontenerów per miesiąc ATD.

    Rozbicie per port załadunku: top 3 porty wg liczby zakończonych kontenerów
    w oknie (osobne linie na FE — prostsze niż select portu, bez dodatkowego stanu).
    Agregacja w SQL (GROUP BY rok/miesiąc), scope przez scope_containers.
    """
    since = today_pl().replace(day=1) - datetime.timedelta(days=365)
    days = _transit_days_col(db)
    year_col, month_col = extract("year", Container.atd), extract("month", Container.atd)
    base = scope_containers(
        select(year_col, month_col, func.avg(days), func.count(Container.id))
        .where(Container.status.in_(Container.FINISHED),
               Container.etd.is_not(None), Container.atd.is_not(None),
               Container.atd >= since, Container.atd >= Container.etd),
        user).group_by(year_col, month_col).order_by(year_col, month_col)

    def pt(y, m, avg, cnt):
        return TransitTrendPoint(month=f"{int(y):04d}-{int(m):02d}",
                                 avg_days=round(float(avg), 1), count=cnt)

    overall = [pt(*row) for row in db.execute(base).all()]

    # top 3 porty wg liczby zakończonych kontenerów w oknie
    top_ports = db.execute(scope_containers(
        select(Port.name, func.count(Container.id))
        .join(Port, Port.id == Container.port_id)
        .where(Container.status.in_(Container.FINISHED),
               Container.etd.is_not(None), Container.atd.is_not(None),
               Container.atd >= since, Container.atd >= Container.etd),
        user).group_by(Port.name)
        .order_by(func.count(Container.id).desc()).limit(3)).all()

    by_port = []
    for port_name, _ in top_ports:
        rows = db.execute(scope_containers(
            select(year_col, month_col, func.avg(days), func.count(Container.id))
            .join(Port, Port.id == Container.port_id)
            .where(Container.status.in_(Container.FINISHED),
                   Container.etd.is_not(None), Container.atd.is_not(None),
                   Container.atd >= since, Container.atd >= Container.etd,
                   Port.name == port_name),
            user).group_by(year_col, month_col).order_by(year_col, month_col)).all()
        by_port.append(TransitTrendPort(port=port_name, points=[pt(*r) for r in rows]))
    return TransitTrendOut(overall=overall, by_port=by_port)


# --- #58 prognoza obłożenia: najbliższe 4 tygodnie ---

@router.get("/stats/occupancy-forecast", response_model=OccupancyForecastOut)
def occupancy_forecast(db: Session = Depends(get_db), user: User = viewer):
    """Suma kontenerów i palet z notify_date w każdym z najbliższych 4 tygodni.

    Agregacja SQL per dzień (GROUP BY notify_date), bucketowanie 28 wierszy
    w tygodnie w Pythonie. Tydzień = od dziś, okna 7-dniowe (nie ISO-pn-nd).
    """
    start = today_pl()
    end = start + datetime.timedelta(days=27)
    rows = db.execute(scope_containers(
        select(Container.notify_date, func.count(Container.id),
               func.coalesce(func.sum(Container.pallet_count), 0))
        .where(Container.notify_date >= start, Container.notify_date <= end),
        user).group_by(Container.notify_date)).all()

    weeks = [OccupancyWeek(week_start=start + datetime.timedelta(days=7 * i),
                           week_end=start + datetime.timedelta(days=7 * i + 6),
                           containers=0, pallets=0) for i in range(4)]
    for day, cnt, pallets in rows:
        w = weeks[(day - start).days // 7]
        w.containers += cnt
        w.pallets += int(pallets)
    return OccupancyForecastOut(weeks=weeks)


# --- analiza wpłynięć i możliwości rozładunków (per magazyn, dzień po dniu) ---

@router.get("/analysis/unloading")
def unloading_analysis(
    db: Session = Depends(get_db),
    user: User = non_warehouse,
    company_code: str = "ACME",
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
):
    """Dzienna liczba kontenerów morskich/kolejowych per magazyn vs limity rozładunków."""
    company = db.scalar(select(Company).where(Company.code == company_code))
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spółki.")
    check_company_access(user, company.id)

    warehouses = db.scalars(select(Warehouse).where(
        Warehouse.company_id == company.id, Warehouse.is_active)
        .order_by(Warehouse.name)).all()
    containers = db.scalars(
        select(Container).where(Container.company_id == company.id,
                                Container.notify_date.is_not(None))).all()
    if not containers:
        return {"warehouses": [], "days": []}

    all_days = [c.notify_date for c in containers]
    date_from = date_from or min(all_days)
    date_to = date_to or min(max(all_days), date_from + datetime.timedelta(days=400))

    by_day: dict = {}
    for c in containers:
        if date_from <= c.notify_date <= date_to:
            by_day.setdefault(c.notify_date, []).append(c)

    # wszystkie nadpisania limitów dla magazynów spółki w oknie — jedno zapytanie
    # zamiast osobnego SELECT-a na każdą parę dzień×magazyn (do 400 dni × N magazynów)
    limits = daily_limits_map(db, [w.id for w in warehouses], date_from, date_to)

    days = []
    day = date_from
    while day <= date_to:
        items = by_day.get(day, [])
        per_warehouse = []
        for w in warehouses:
            mine = [c for c in items if c.warehouse_id == w.id]
            rail = sum(1 for c in mine if c.transport_type is not None
                       and c.transport_type.value == "kolej")
            limit = limits.get((w.id, day), w.default_daily_limit)
            per_warehouse.append({
                "warehouse_id": w.id, "name": w.name,
                "rail": rail, "sea": len(mine) - rail, "total": len(mine),
                "limit": limit,
                "over": limit is not None and len(mine) > limit,
            })
        days.append({
            "day": day.isoformat(),
            "is_free_day": is_free_day(day, "PL"),
            "warehouses": per_warehouse,
            "total": len(items),
        })
        day += datetime.timedelta(days=1)
    return {"warehouses": [{"id": w.id, "name": w.name} for w in warehouses], "days": days}


# --- prognoza obciążenia magazynów (Analityka F2) ---

@router.get("/analysis/forecast")
def warehouse_forecast(
    db: Session = Depends(get_db),
    user: User = non_warehouse,
    company_code: str = "ACME",
    weeks: int = 4,
):
    """Prognoza rozładunków 4 tyg. w przód: kontenery/dzień vs limit + palety.

    Data planowana = notify_date (spójnie z kolejką i analizą rozładunków).
    Braki pallet_count uzupełniane średnią historyczną dostawcy (fallback: średnia
    globalna z zakończonych kontenerów) — takie wartości mają pallets_estimated=True."""
    company = db.scalar(select(Company).where(Company.code == company_code))
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spółki.")
    check_company_access(user, company.id)
    weeks = max(1, min(weeks, 8))
    date_from = today_pl()
    date_to = date_from + datetime.timedelta(days=weeks * 7 - 1)

    warehouses = db.scalars(select(Warehouse).where(
        Warehouse.company_id == company.id, Warehouse.is_active)
        .order_by(Warehouse.name)).all()
    containers = db.scalars(select(Container).where(
        Container.company_id == company.id,
        Container.status.not_in(Container.FINISHED),
        Container.notify_date.is_not(None),
        Container.notify_date >= date_from,
        Container.notify_date <= date_to)).all()
    limits = daily_limits_map(db, [w.id for w in warehouses], date_from, date_to)

    # średnie palet z historii (zakończone kontenery z pallet_count>0): per dostawca + globalna
    hist = db.execute(
        select(Container.supplier_id, func.avg(Container.pallet_count),
               func.count(Container.id))
        .where(Container.company_id == company.id,
               Container.status.in_(Container.FINISHED),
               Container.pallet_count.is_not(None), Container.pallet_count > 0)
        .group_by(Container.supplier_id)).all()
    supplier_avg = {sid: float(avg) for sid, avg, _ in hist if sid is not None}
    total_n = sum(n for _, _, n in hist)
    global_avg = (sum(float(avg) * n for _, avg, n in hist) / total_n) if total_n else None

    by_key: dict[tuple[int | None, datetime.date], list[Container]] = {}
    for c in containers:
        by_key.setdefault((c.warehouse_id, c.notify_date), []).append(c)

    def pallets_for(items: list[Container]) -> tuple[int | None, bool]:
        total, estimated = 0.0, False
        for c in items:
            if c.pallet_count:
                total += c.pallet_count
            else:
                guess = supplier_avg.get(c.supplier_id, global_avg)
                if guess is None:
                    continue   # brak jakiejkolwiek historii — nie zgadujemy
                total += guess
                estimated = True
        return (round(total) if total else None), estimated

    out = []
    for w in warehouses:
        days = []
        day = date_from
        while day <= date_to:
            items = by_key.get((w.id, day), [])
            limit = limits.get((w.id, day), w.default_daily_limit)
            pallets, estimated = pallets_for(items)
            days.append({
                "date": day.isoformat(),
                "is_free_day": is_free_day(day, "PL"),
                "containers": len(items),
                "limit": limit,
                "over": limit is not None and len(items) > limit,
                "pallets": pallets,
                "pallets_estimated": estimated,
                "container_ids": [c.id for c in items],
            })
            day += datetime.timedelta(days=1)
        out.append({"id": w.id, "name": w.name, "days": days})
    return {"date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
            "warehouses": out}

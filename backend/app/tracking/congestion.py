"""Kongestia portów: dzienny zapis liczby naszych statków na redzie + alert trendu.

Zapis odpalany z własnego joba „congestion" (włączany kluczem AIS — near_port
pochodzi wyłącznie z AIS, nie z providera trackingu; lekki upsert per port), alert porównuje dzisiejszą
liczbę z medianą 14 poprzednich dni (dziś > 2× mediana → powiadomienie do teamu Acme,
raz per port i dzień)."""
import datetime
import logging
import statistics

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Notification, PortCongestion, TrackedVessel, pl_midnight_utc, today_pl
from .ais import active_vessel_names

logger = logging.getLogger(__name__)

TREND_DAYS = 14
MIN_HISTORY_DAYS = 7   # bez sensownej historii mediana z 1-2 dni krzyczałaby od razu


def record_port_congestion(db: Session, today: datetime.date | None = None) -> int:
    """Upsert dzisiejszych liczników na redzie per port; zwraca liczbę portów.

    Bierzemy maksimum z dnia — cykl biegnie kilka razy dziennie, a chwilowy spadek
    (statek wypłynął rano) nie powinien zamazywać szczytu kongestii."""
    today = today or today_pl()
    names = active_vessel_names(db)
    counts: dict[str, int] = {}
    if names:
        for vessel in db.scalars(select(TrackedVessel).where(
                TrackedVessel.name.in_(names), TrackedVessel.near_port != "")):
            counts[vessel.near_port] = counts.get(vessel.near_port, 0) + 1
    for port, waiting in counts.items():
        row = db.scalar(select(PortCongestion).where(
            PortCongestion.port == port, PortCongestion.day == today))
        if row is None:
            db.add(PortCongestion(port=port, day=today, waiting=waiting))
        elif waiting > row.waiting:
            row.waiting = waiting
    db.commit()
    return len(counts)


def check_congestion_alerts(db: Session, today: datetime.date | None = None) -> int:
    """Alert, gdy dzisiejsza kongestia portu > 2× mediana z 14 poprzednich dni.

    Dedup: jedno powiadomienie per port i dzień — po prefiksie tytułu i dacie
    utworzenia, bo sam tytuł niesie licznik, który w ciągu dnia rośnie (upsert max)."""
    from ..models import Role, User
    from ..notifications import notify, acme_team
    today = today or today_pl()
    since = today - datetime.timedelta(days=TREND_DAYS)
    rows = db.scalars(select(PortCongestion).where(
        PortCongestion.day >= since, PortCongestion.day <= today)).all()
    by_port: dict[str, dict[datetime.date, int]] = {}
    for r in rows:
        by_port.setdefault(r.port, {})[r.day] = r.waiting
    sent = 0
    for port, days in by_port.items():
        current = days.get(today)
        history = [w for d, w in days.items() if d != today]
        if current is None or len(history) < MIN_HISTORY_DAYS:
            continue
        median = statistics.median(history)
        if median <= 0 or current <= 2 * median:
            continue
        title = (f"Kongestia portu {port}: {current} statków na redzie {today} "
                 f"(mediana 14 dni: {median:g})")
        already = db.scalar(select(Notification.id).where(
            Notification.kind == "port_congestion",
            Notification.title.startswith(f"Kongestia portu {port}:", autoescape=True),
            Notification.created_at >= pl_midnight_utc(today))
            .limit(1))
        if already:
            continue
        # centralny team Acme (transport) + systemowi admini (kongestia nie ma spółki)
        recipients = {u.id: u for u in acme_team(db)}
        for u in db.scalars(select(User).where(User.is_active, User.role == Role.admin)):
            recipients[u.id] = u
        sent += notify(db, list(recipients.values()),
                       kind="port_congestion", title=title)
    db.commit()
    return sent

"""Seed sezonowego transit time portów (dane od klienta, styczeń–wrzesień).

Dane są w tym pliku, nie w migracji: to dane klienta, nie schemat — migracja
powtarzałaby je na każdym środowisku i nie dałoby się ich poprawić bez kolejnej.
Idempotencja: dopasowanie po (port, miesiąc) — ponowne uruchomienie aktualizuje
wartość, nie dokłada wiersza. Porty spoza słownika są raportowane i pomijane.

Uruchomienie (z katalogu backend/):
  python -m scripts.seed_port_transit            → podglad, NIC nie zapisuje
  python -m scripts.seed_port_transit --commit   → zapis do bazy
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Port, PortTransitTime  # noqa: E402

# nazwa portu -> dni tranzytu dla miesięcy 1..9 (paźdz.–grudzień: klient nie ma danych,
# zadziała fallback na Port.transit_time_days)
DANE = {
    "SHANGHAI": [50, 52, 53, 60, 60, 60, 62, 65, 65],
    "WUHAN": [68, 68, 75, 75, 75, 75, 75, 75, 75],
    "QINGDAO": [57, 60, 60, 65, 65, 65, 65, 65, 65],
    "KLANG": [63, 60, 50, 55, 55, 55, 55, 55, 55],
    "SONGKHLA": [69, 69, 70, 58, 58, 58, 58, 58, 58],
    "JIUJIANG": [68, 68, 70, 75, 75, 75, 75, 75, 75],
    "XINGANG": [58, 62, 60, 62, 62, 62, 62, 62, 62],
}


def seed(db) -> tuple[int, int, list[str]]:
    """Zwraca (nowych, zaktualizowanych, brakujące porty)."""
    ports = {p.name.strip().upper(): p for p in db.scalars(select(Port)).all()}
    new = updated = 0
    missing: list[str] = []
    for name, days_per_month in DANE.items():
        port = ports.get(name)
        if port is None:
            missing.append(name)
            continue
        existing = {row.month: row for row in port.transit_rows}
        for month, days in enumerate(days_per_month, start=1):
            row = existing.get(month)
            if row is None:
                port.transit_rows.append(PortTransitTime(month=month, days=days))
                new += 1
            elif row.days != days:
                row.days = days
                updated += 1
    return new, updated, missing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="zapisz zmiany w bazie")
    args = parser.parse_args()
    with SessionLocal() as db:
        new, updated, missing = seed(db)
        print(f"nowych: {new}, zaktualizowanych: {updated}")
        if missing:
            print("UWAGA — brak w slowniku portow (pominiete): " + ", ".join(missing))
        if args.commit:
            db.commit()
            print("Zapisano.")
        else:
            db.rollback()
            print("Podglad — nic nie zapisano. Dodaj --commit, zeby zapisac.")


if __name__ == "__main__":
    main()

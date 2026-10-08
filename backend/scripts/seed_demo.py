"""Instancja portfolio: KASUJE wszystkie dane i załączniki, wgrywa zmyślone dane pokazowe
(dostawcy, kontenery, kierowcy, konta) + konto demo tylko do odczytu.

Bezpieczniki (oba wymagane — na zwykłej instancji skrypt odmawia):
  1. DEMO_READONLY_LOGINS ustawione (tylko instancja pokazowa je ma),
  2. flaga --wyczysc-wszystko.
Uruchom z backend/ (w kontenerze app):
  DEMO_PASSWORD='<min. 12 znaków>' python -m scripts.seed_demo --wyczysc-wszystko
Schemat i alembic_version zostają (czyszczone są wiersze), więc kolejne wdrożenia działają normalnie.
"""
import datetime as dt
import os
import pathlib
import random
import sys

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.main import bootstrap  # przez app.main: kolejność importów omija cykl modułów (ARCH-002)
from app.iso6346 import check_digit
from app.models import Company, Container, CustomsAgency, Forwarder, User, Warehouse
from app.models.enums import ContainerStatus, Role, today_pl
from app.security import hash_password, validate_password_policy

FLAG = "--wyczysc-wszystko"
SUPPLIERS = ["Ningbo Demo Trading Co.", "Qingdao Przykładowe Tekstylia", "Shenzhen Pokazowa Elektronika",
             "Xiamen Wzorcowe Meble", "Dostawca Portugalski Demo Lda", "Foshan Testowe Oświetlenie"]
VESSELS = ["DEMO EXPRESS", "SAMPLE STAR", "PRZYKŁAD MAERSK", "TEST HORIZON"]


def refuse(msg: str) -> None:
    raise SystemExit(f"seed_demo: ODMOWA — {msg}")


def check_guards(argv: list[str]) -> list[str]:
    demo = [x.strip() for x in settings.demo_readonly_logins.split(",") if x.strip()]
    if not demo:
        refuse("brak DEMO_READONLY_LOGINS — to nie jest instancja pokazowa.")
    if FLAG not in argv:
        refuse(f"brak flagi {FLAG} (skrypt kasuje WSZYSTKIE dane).")
    return demo


def wipe() -> None:
    Base.metadata.create_all(engine)   # idempotentne (jak start aplikacji) — pusta baza też zadziała
    with engine.begin() as conn:   # wiersze, nie schemat — alembic_version zostaje
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    uploads = pathlib.Path(settings.uploads_dir)
    if uploads.is_dir():
        for f in uploads.rglob("*"):
            if f.is_file():
                f.unlink()


def container_no(i: int) -> str:
    prefix = ["MSKU", "TCLU", "CMAU", "HLXU", "MSDU"][i % 5]
    serial = 100000 + i * 13
    while check_digit(f"{prefix}{serial:06d}") == 10:
        serial += 1
    body = f"{prefix}{serial:06d}"
    return body + str(check_digit(body))


def seed(demo_logins: list[str], password: str, n: int = 150) -> int:
    random.seed(2026)
    bootstrap()   # domyślne spółki, słowniki, admin z ADMIN_PASSWORD
    db = SessionLocal()
    acme = db.query(Company).filter_by(code="ACME").one()
    dlt = Warehouse(name="DLT", company_id=acme.id)
    wz = Warehouse(name="ACME", company_id=acme.id)
    agency = CustomsAgency(name="Agencja Celna Demo Sp. z o.o.")
    fw = db.query(Forwarder).first() or Forwarder(name="Spedycja Demo")
    db.add_all([dlt, wz, agency, fw])
    db.flush()
    for login in demo_logins:   # logistyka (nie admin: bez logów serwera i monitora hosta)
        db.add(User(login=login, hashed_password=hash_password(password), role=Role.logistics,
                    company_id=acme.id, view_all_companies=True, full_name="Konto demo",
                    email=f"{login}@example.com"))
    statuses, today = list(ContainerStatus), today_pl()
    for i in range(n):
        eta = today + dt.timedelta(days=random.randint(-45, 90))
        driver = i % 4 == 0
        db.add(Container(
            container_no=container_no(i), company_id=acme.id, status=statuses[i % len(statuses)],
            warehouse_id=[dlt.id, wz.id, None][i % 3], supplier_raw=SUPPLIERS[i % len(SUPPLIERS)],
            vessel=VESSELS[i % len(VESSELS)], eta=eta, notify_date=eta + dt.timedelta(days=5) if i % 3 else None,
            forwarder_id=fw.id if i % 2 == 0 else None, customs_agency_id=agency.id if i % 5 == 0 else None,
            # zmyślone dane kierowcy: numer 000 nie istnieje w polskiej numeracji
            driver_name=f"Kierowca Demo {i}" if driver else "",
            driver_phone=f"+48 000 000 {i:03d}" if driver else "",
            truck_no=f"DEMO{i:03d}" if driver else "",
        ))
    db.commit()
    count = db.query(Container).count()
    db.close()
    return count


def main(argv: list[str]) -> None:
    demo = check_guards(argv)
    password = os.environ.get("DEMO_PASSWORD", "")
    validate_password_policy(password)
    wipe()
    print(f"seed_demo: gotowe — {seed(demo, password)} kontenerów, konta demo: {', '.join(demo)}")


if __name__ == "__main__":
    main(sys.argv[1:])

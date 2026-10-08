"""ARCH-009: domena kontenerów (routers/containers*.py) tylko w stylu SQLAlchemy 2.0
(`select`/`delete` + `db.execute`) — bez legacy `db.query(...)`. Strażnik dla tego wycinka;
reszta repo przechodzi na 2.0 przy okazji zmian."""
import pathlib
import re

ROUTERS = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers"


def test_containers_routers_have_no_legacy_query():
    offenders = [f"{path.name}:{no}"
                 for path in sorted(ROUTERS.glob("containers*.py"))
                 for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if re.search(r"\.query\(", line)]
    assert not offenders, f"legacy Query API (użyj select/delete + db.execute): {offenders}"


def test_purge_returns_deleted_count(client):
    """_delete_where zwraca rowcount jak Query.delete — clear_queue raportuje liczbę kontenerów."""
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import Company, Container
    from app.routers.containers_purge import _purge_containers
    with SessionLocal() as db:
        company = db.scalar(select(Company).where(Company.code == "ACME"))
        ids = []
        for no in ("MSKU7026499", "TCLU1234567"):
            container = Container(company_id=company.id, container_no=no)
            db.add(container)
            db.flush()
            ids.append(container.id)
        db.commit()
        assert _purge_containers(db, ids + [10**9]) == 2
        db.commit()
        assert db.scalar(select(Container).where(Container.id.in_(ids))) is None

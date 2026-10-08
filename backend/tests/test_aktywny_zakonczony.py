"""BIZ-004: dwa pojęcia „zakończenia” kontenera (docs/REGULY-PROCESU.md).

DOSTARCZONY (rozładowany, nierozliczony) jest OTWARTY W KOLEJCE (lista, liczniki,
wyszukiwarka), ale FIZYCZNIE ZAKOŃCZONY — nie ma go na mapie śledzenia ani w „w drodze”.
"""
import pathlib
import re

from app.database import SessionLocal
from app.models import Container, ContainerStatus
from tests.test_tracking import _borealis_id

NO = "MSDU5050505"


def _delivered() -> int:
    with SessionLocal() as db:
        c = Container(container_no=NO, company_id=_borealis_id(db),
                      status=ContainerStatus.DOSTARCZONY, rf_number="6200000099")
        db.add(c)
        db.commit()
        return c.id


def test_delivered_open_in_queue_but_not_tracked(client, admin_headers):
    cid = _delivered()
    get = lambda url, **p: client.get(url, params=p, headers=admin_headers).json()  # noqa: E731

    # kolejka: aktywne tak, archiwum nie; licznik zakładki spółki go liczy
    assert cid in [c["id"] for c in get("/api/containers", completed="false")]
    assert cid not in [c["id"] for c in get("/api/containers", completed="true")]
    assert get("/api/containers/counts")["BOREALIS"] >= 1
    # wyszukiwarka kolejki
    assert [s["container_id"] for s in get("/api/search/suggest", q="5050505",
                                           completed="false")] == [cid]
    # fizycznie zakończony: nie „w drodze” i nie na mapie śledzenia statków
    assert get("/api/stats/dashboard")["in_transit"] == 0
    body = get("/api/tracking/map")
    assert body["total"] == 0, body


ALLOWED = {  # świadome, dosłowne porównania z samym ZREALIZOWANY
    "models/container.py",       # definicja Container.open_in_queue()
    "avizo_workflow.py",         # retencja nr dokumentu 30 dni po realizacji (D8)
    "routers/share.py",          # wygasanie linku udostępnienia po realizacji
    "importers/queue.py",        # N-20: numer tylko z zrealizowanych = nowy kontener (per rekord)
    "routers/containers_write.py",  # completed_at = moment realizacji
}


def test_no_bare_zrealizowany_comparisons():
    app = pathlib.Path(__file__).resolve().parents[1] / "app"
    pat = re.compile(r"[!=]=\s*ContainerStatus\.ZREALIZOWANY")
    bad = [str(p.relative_to(app)).replace("\\", "/") for p in app.rglob("*.py")
           if pat.search(p.read_text(encoding="utf-8"))]
    assert sorted(set(bad) - ALLOWED) == [], (
        "użyj Container.open_in_queue() (kolejka) albo Container.FINISHED (fizycznie zakończony)")

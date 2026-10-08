"""Podpowiedzi wyszukiwarki (2026-09-24): kontener / PO / statek / dostawca po fragmencie.

Ta sama separacja danych co lista kontenerów (`scope_containers`). Zapytanie przycinane
do 50 znaków i normalizowane (białe znaki → pojedyncza spacja). Postgres: ILIKE plus
podobieństwo trigramowe (pg_trgm, łapie drobne literówki w numerze/statku); SQLite
(testy, dev): samo ILIKE.
"""
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..deps import ViewerOrSales as viewer_or_sales
from ..deps import scope_containers
from ..models import Container, Supplier, User
from ..order_numbers import split_order_numbers
from .containers_common import fk_matches, hidden_fields, searchable

router = APIRouter(prefix="/api/search", tags=["wyszukiwarka"])

MAX_Q = 50
MIN_Q = 2
LIMIT = 10
CANDIDATES = 60   # kontenerów branych pod uwagę przed podziałem na typy
TYPES = ("container", "po", "vessel", "supplier")
TRGM_MIN = 0.3   # próg podobieństwa pg_trgm dla literówek
_trgm: bool | None = None   # czy pg_trgm jest zainstalowane (sprawdzane raz na proces)


def _has_trgm(db: Session) -> bool:
    global _trgm
    if _trgm is None:
        _trgm = (db.bind.dialect.name == "postgresql" and bool(db.scalar(
            text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))))
    return _trgm


def normalize_query(raw: str) -> str:
    return re.sub(r"\s+", " ", raw or "").strip()[:MAX_Q]


def _hits(c: Container, q: str, hidden: frozenset[str]) -> list[tuple[str, str]]:
    """Wszystkie trafienia (typ, etykieta) kontenera — numer, każde pasujące PO, statek, dostawca.
    Pól ukrytych dla roli (`hidden`, jak to_out) nie pokazujemy jako trafień."""
    low = q.lower()
    out = [("po", n) for n in split_order_numbers(c.order_numbers)
           if "order_numbers" not in hidden and low in n.lower()]
    if low in (c.vessel or "").lower():
        out.append(("vessel", c.vessel))
    if ("supplier_name" not in hidden and c.supplier
            and low in (c.supplier.name or "").lower()):
        out.append(("supplier", c.supplier.name))
    # numer pasuje wprost albo tylko trigramowo (literówka) — wtedy też pokaż kontener
    if low in (c.container_no or "").lower() or not out:
        out.insert(0, ("container", c.container_no))
    return out


def _balanced(buckets: dict[str, list[dict]]) -> list[dict]:
    """Po kolei z każdego typu (kontener → PO → statek → dostawca), razem max LIMIT —
    10 kontenerów jednego statku nie wypycha trafień PO/dostawcy."""
    out: list[dict] = []
    while len(out) < LIMIT and any(buckets.values()):
        for kind in TYPES:
            if buckets[kind] and len(out) < LIMIT:
                out.append(buckets[kind].pop(0))
    return out


@router.get("/suggest")
def suggest(q: str = Query(default="", max_length=500), completed: bool | None = None,
            db: Session = Depends(get_db), user: User = viewer_or_sales):
    """q > 50 znaków jest PRZYCINANE (nie 422) — pole ma maxlength=50, a wklejka z innego
    klienta nie powinna kończyć się błędem. max_length=500 odcina tylko nadużycia."""
    term = normalize_query(q)
    if len(term) < MIN_Q:
        return []
    like = f"%{term}%"
    # tylko pola widoczne dla roli (magazyn/agencja: bez PO i dostawcy — jak to_out i lista
    # kontenerów), inaczej podpowiedź zdradzałaby dane handlowe (wyrocznia istnienia)
    hidden = hidden_fields(user)
    # każda gałąź OR ma indeks na containers (GIN pg_trgm / FK) — PERF-007
    conds = searchable(user, {
        "container_no": Container.container_no.ilike(like),
        "order_numbers": Container.order_numbers.ilike(like),
        "vessel": Container.vessel.ilike(like),
        "supplier_name": fk_matches(db, Container.supplier_id,
                                    select(Supplier.id).where(Supplier.name.ilike(like)))})
    order = [Container.notify_date.desc().nulls_last(), Container.id.desc()]
    if _has_trgm(db):
        # `a % b` ≡ similarity(a, b) > pg_trgm.similarity_threshold, ale w odróżnieniu od
        # `similarity(...) > x` idzie po GIN; próg = TRGM_MIN tylko w tej transakcji
        db.execute(select(func.set_config("pg_trgm.similarity_threshold", str(TRGM_MIN), True)))
        conds += [Container.container_no.op("%")(term), Container.vessel.op("%")(term)]
        sim = func.greatest(func.similarity(Container.container_no, term),
                            func.similarity(func.coalesce(Container.vessel, ""), term))
        order = [sim.desc(), *order]
    query = (select(Container)
             .options(joinedload(Container.supplier), joinedload(Container.warehouse))
             .where(or_(*conds)).order_by(*order).limit(CANDIDATES))
    if completed is not None:   # kolejka (False) / archiwum (True) — jak lista kontenerów
        done = ~Container.open_in_queue()
        query = query.where(done if completed else ~done)
    buckets: dict[str, list[dict]] = {k: [] for k in TYPES}
    seen: set[tuple[str, str]] = set()
    for c in db.scalars(scope_containers(query, user)).unique():
        for kind, label in _hits(c, term, hidden):
            # PO/statek/dostawca raz na etykietę (najświeższy kontener); kontener zawsze
            key = (kind, label.lower() if kind != "container" else str(c.id))
            if key in seen:
                continue
            seen.add(key)
            buckets[kind].append({
                "type": kind, "label": label, "container_id": c.id,
                "container_no": c.container_no, "notify_date": c.notify_date,
                "warehouse": c.warehouse.name if c.warehouse else None,
                "vessel": c.vessel or None,
                "supplier_id": None if "supplier_id" in hidden else c.supplier_id})
    return _balanced(buckets)

"""Walidator jakości master data (#16) + wiek importów (#17).

Wszystkie reguły w JEDNYM miejscu — dokładanie nowej to wpis do RULES
(klucz, zakładka Master data, funkcja zwracająca [(id, etykieta)]).
Endpoint: GET /api/master-data/quality (Editors).
"""
import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .deps import Editors as editors
from .deps import company_filter_ids, scope_suppliers
from .models import (
    AuditLog,
    Container,
    ContainerPort,
    ContainerStatus,
    MaterialUnit,
    Supplier,
    User,
    utcnow,
)

router = APIRouter(prefix="/api/master-data", tags=["master-data"])

# ile pozycji listujemy per problem (licznik zawsze pełny)
ITEMS_CAP = 50


def _company_scope(query, column, user: User):
    company_ids = company_filter_ids(user)
    return query if company_ids is None else query.where(column.in_(company_ids))


def suppliers_without_sap(db: Session, user: User) -> list[tuple[int, str]]:
    rows = db.execute(scope_suppliers(select(Supplier.id, Supplier.name).where(
        Supplier.is_active, Supplier.sap_code == ""), user)).all()
    return [(i, n) for i, n in rows]


def suppliers_without_country(db: Session, user: User) -> list[tuple[int, str]]:
    rows = db.execute(scope_suppliers(select(Supplier.id, Supplier.name).where(
        Supplier.is_active, Supplier.country == ""), user)).all()
    return [(i, n) for i, n in rows]


def duplicate_supplier_names(db: Session, user: User) -> list[tuple[int, str]]:
    """Duplikaty nazw w obrębie właściciela (kartoteka / nadawcy spółki), bez wielkości liter."""
    dup = db.execute(scope_suppliers(select(Supplier.client_company_id, func.lower(Supplier.name))
                                     .where(Supplier.is_active)
                                     .group_by(Supplier.client_company_id, func.lower(Supplier.name))
                                     .having(func.count() > 1), user)).all()
    out: list[tuple[int, str]] = []
    for owner, lname in dup:
        rows = db.execute(select(Supplier.id, Supplier.name).where(
            Supplier.client_company_id.is_not_distinct_from(owner), Supplier.is_active,
            func.lower(Supplier.name) == lname)).all()
        out.extend((i, n) for i, n in rows)
    return out


def cports_without_coords(db: Session, user: User) -> list[tuple[int, str]]:
    rows = db.execute(select(ContainerPort.id, ContainerPort.code, ContainerPort.name)
                      .where(ContainerPort.is_active,
                             (ContainerPort.lat.is_(None)) | (ContainerPort.lon.is_(None)))).all()
    return [(i, f"{c} {n}") for i, c, n in rows]


def materials_without_pal(db: Session, user: User) -> list[tuple[int, str]]:
    """Materiały bez jednostki PAL w MARM (przelicznik palet niepoliczalny)."""
    with_pal = select(MaterialUnit.material_no).where(MaterialUnit.unit == "PAL")
    rows = db.execute(select(func.min(MaterialUnit.id), MaterialUnit.material_no)
                      .where(MaterialUnit.material_no.not_in(with_pal))
                      .group_by(MaterialUnit.material_no)).all()
    return [(i, m) for i, m in rows]


def units_without_dimensions(db: Session, user: User) -> list[tuple[int, str]]:
    """Jednostki PAL/KAR bez kompletu wymiarów w MARM (pakowanie 3D nie zadziała)."""
    rows = db.execute(select(MaterialUnit.id, MaterialUnit.material_no, MaterialUnit.unit)
                      .where(MaterialUnit.unit.in_(("PAL", "KAR")),
                             (MaterialUnit.length.is_(None))
                             | (MaterialUnit.width.is_(None))
                             | (MaterialUnit.height.is_(None)))).all()
    return [(i, f"{m} {u}") for i, m, u in rows]


def containers_without_warehouse(db: Session, user: User) -> list[tuple[int, str]]:
    """Aktywne kontenery bez magazynu ze słownika (import nie dopasował wartości)."""
    rows = db.execute(_company_scope(
        select(Container.id, Container.container_no).where(
            Container.warehouse_id.is_(None),
            Container.open_in_queue()),  # otwarte w kolejce
        Container.company_id, user)).all()
    return [(i, n) for i, n in rows]


# kontener już płynie/stoi w porcie — ETA musi być znane (wcześniej bywa jeszcze nieustalone)
ETA_REQUIRED = (ContainerStatus.W_TRANSPORCIE, ContainerStatus.W_PORCIE,
                ContainerStatus.ODPRAWA, ContainerStatus.AWIZOWANY)
DELIVERED = (ContainerStatus.DOSTARCZONY, ContainerStatus.ZREALIZOWANY)


def containers_without_po(db: Session, user: User) -> list[tuple[int, str]]:
    """Kontenery w obiegu bez żadnego numeru zamówienia (PO) — nie da się ich rozliczyć."""
    rows = db.execute(_company_scope(
        select(Container.id, Container.container_no).where(
            func.trim(func.coalesce(Container.order_numbers, "")) == "",
            Container.status.not_in(DELIVERED)),
        Container.company_id, user)).all()
    return [(i, n) for i, n in rows]


def containers_without_eta(db: Session, user: User) -> list[tuple[int, str]]:
    """Kontenery w transporcie/porcie/odprawie bez ETA — planowanie rampy działa na ślepo."""
    rows = db.execute(_company_scope(
        select(Container.id, Container.container_no).where(
            Container.eta.is_(None), Container.status.in_(ETA_REQUIRED)),
        Container.company_id, user)).all()
    return [(i, n) for i, n in rows]


# klucz (etykieta po stronie frontu, i18n) → (zakładka Master data, funkcja)
RULES: list[tuple[str, str, object]] = [
    ("suppliers_no_sap", "suppliers", suppliers_without_sap),
    ("suppliers_no_country", "suppliers", suppliers_without_country),
    ("suppliers_dup_names", "suppliers", duplicate_supplier_names),
    ("cports_no_coords", "cports", cports_without_coords),
    ("materials_no_pal", "units", materials_without_pal),
    ("units_no_dims", "units", units_without_dimensions),
    ("containers_no_warehouse", "", containers_without_warehouse),
    ("containers_no_po", "", containers_without_po),
    ("containers_no_eta", "", containers_without_eta),
]

# typ importu → entity_type w AuditLog (wpisy field='import' robią importery)
IMPORT_TYPES: list[tuple[str, str]] = [
    ("marm", "material_units"),
    ("ekko", "sap_orders"),
    ("lfa1", "suppliers"),
    ("cports", "container_ports"),
]


def import_freshness(db: Session, now: datetime.datetime | None = None) -> list[dict]:
    """Wiek ostatniego importu per typ (z AuditLog); stale = starszy niż STALE_IMPORT_DAYS
    (albo nigdy nie wykonany)."""
    now = now or utcnow()
    out = []
    for key, entity_type in IMPORT_TYPES:
        last = db.scalar(select(func.max(AuditLog.created_at)).where(
            AuditLog.entity_type == entity_type, AuditLog.field == "import"))
        age = (now - last).days if last else None
        out.append({"type": key, "last_at": last.isoformat() if last else None,
                    "age_days": age,
                    "stale": age is None or age > settings.stale_import_days})
    return out


def run_quality(db: Session, user: User) -> list[dict]:
    issues = []
    for key, tab, fn in RULES:
        found = fn(db, user)
        issues.append({
            "key": key, "tab": tab, "count": len(found),
            "items": [{"id": i, "label": label} for i, label in found[:ITEMS_CAP]],
        })
    return issues


@router.get("/quality")
def master_data_quality(db: Session = Depends(get_db), user: User = editors):
    """Raport jakości master data: problemy per reguła + wiek importów."""
    return {"issues": run_quality(db, user),
            "imports": import_freshness(db),
            "stale_import_days": settings.stale_import_days}

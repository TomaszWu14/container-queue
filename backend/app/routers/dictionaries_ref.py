"""Słowniki: porty (z sezonowym transit time), typy kontenerów, kontakty u dostawcy,
przelicznik NBP, armatorzy oraz master data globalne (porty kontenerowe, jednostki MARM).

Router bez prefiksu — prefiks /api i tag nadaje dictionaries.router, który go dołącza.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..deps import (
    AdminOnly as admins,
)
from ..deps import (
    Editors as editors,
)
from ..deps import (
    Viewer as viewer,
)
from ..deps import ViewerOrSales as viewer_or_sales
from ..deps import get_scoped, scope_suppliers, supplier_catalog_access
from ..models import (
    Carrier,
    ContainerPort,
    ContainerType,
    MaterialUnit,
    Port,
    PortTransitTime,
    Role,
    Supplier,
    SupplierContact,
    User,
)
from ..schemas import (
    ContainerPortOut,
    ContainerTypeIn,
    ContainerTypeOut,
    FxConvertOut,
    MaterialUnitOut,
    MergeIn,
    MergeOut,
    CarrierIn,
    CarrierOut,
    PortIn,
    PortOut,
    SupplierContactIn,
    SupplierContactOut,
)
from .dictionaries_merge import CARRIERS, PORTS, _delete, _get_or_404, _merge, guarded_delete

router = APIRouter()
# nazwa loggera sprzed podziału modułu — filtry/alerty logów bez zmian
_logger = logging.getLogger("app.routers.dictionaries")


def _container_type_out(ct: ContainerType) -> ContainerTypeOut:
    out = ContainerTypeOut.model_validate(ct)
    out.volume_m3 = ct.volume_m3
    return out


def _set_monthly_transit(db: Session, port: Port, months: dict[int, int]) -> None:
    """Nadpisuje cały profil sezonowy portu (mapa miesiąc→dni).

    Pełne nadpisanie, nie merge: formularz zawsze wysyła komplet, więc usunięty
    miesiąc ma zniknąć. Braki są normalne — fallback robi `planning.transit_days_for`.
    """
    existing = {row.month: row for row in port.transit_rows}
    for month, days in months.items():
        row = existing.pop(month, None)
        if row is None:
            port.transit_rows.append(PortTransitTime(month=month, days=days))
        elif row.days != days:
            row.days = days
    for row in existing.values():
        port.transit_rows.remove(row)


@router.get("/ports", response_model=list[PortOut])
def list_ports(db: Session = Depends(get_db), user: User = viewer_or_sales,
               include_inactive: bool = False):
    # bez include_inactive panel admina nie zobaczyłby dezaktywowanego portu,
    # więc nie dałoby się go już reaktywować — byłby skasowany „na zawsze”.
    query = select(Port).order_by(Port.name)
    if not include_inactive:
        query = query.where(Port.is_active)
    return db.scalars(query).all()


@router.post("/ports", response_model=PortOut, status_code=201)
def create_port(body: PortIn, db: Session = Depends(get_db), user: User = admins):
    if db.scalar(select(Port).where(Port.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki port już istnieje.")
    data = body.model_dump()
    months = data.pop("monthly_transit")
    port = Port(**data)
    db.add(port)
    audit.record_created(db, port, user)
    _set_monthly_transit(db, port, months)
    db.commit()
    return port


@router.patch("/ports/{port_id}", response_model=PortOut)
def update_port(port_id: int, body: PortIn, db: Session = Depends(get_db), user: User = admins):
    port = db.get(Port, port_id)
    if not port:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono portu.")
    clash = db.scalar(select(Port).where(Port.id != port_id, Port.name == body.name))
    if clash:
        # jak u dostawców: kolizja nazwy to zwykle duplikat z importu, nie literówka
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Taki port już istnieje (id={clash.id}) — scal duplikaty.")
    data = body.model_dump(exclude_unset=True)
    months = data.pop("monthly_transit", None)
    audit.record_changes(db, port, data, user)
    if months is not None:   # brak klucza = profil sezonowy bez zmian (nie kasujemy)
        _set_monthly_transit(db, port, months)
    db.commit()
    return port


@router.post("/ports/{port_id}/merge", response_model=MergeOut)
def merge_port(port_id: int, body: MergeIn, db: Session = Depends(get_db), user: User = admins):
    return _merge(db, PORTS, port_id, body, user)


@router.delete("/ports/{port_id}", status_code=204)
def delete_port(port_id: int, db: Session = Depends(get_db), user: User = admins):
    _delete(db, PORTS, port_id, user)


# --- typy kontenerów (z kubaturą) ---

@router.get("/container-types", response_model=list[ContainerTypeOut])
def list_container_types(db: Session = Depends(get_db), user: User = viewer_or_sales):
    types = db.scalars(select(ContainerType).where(ContainerType.is_active)
                       .order_by(ContainerType.sort_order, ContainerType.name)).all()
    return [_container_type_out(ct) for ct in types]


@router.post("/container-types", response_model=ContainerTypeOut, status_code=201)
def create_container_type(body: ContainerTypeIn, db: Session = Depends(get_db),
                          user: User = admins):
    if db.scalar(select(ContainerType).where(ContainerType.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki typ kontenera już istnieje.")
    ct = ContainerType(**body.model_dump())
    db.add(ct)
    audit.record_created(db, ct, user)
    db.commit()
    return _container_type_out(ct)


# --- kontakty u dostawcy ---

@router.get("/supplier-contacts", response_model=list[SupplierContactOut])
def list_supplier_contacts(supplier_id: int | None = None,
                           db: Session = Depends(get_db), user: User = viewer):
    # kontakty dostawców to dane wewnętrzne — konta zewnętrzne (spedycja) nie mają wglądu,
    # a pozostali — wg reguł kartoteki (deps.scope_suppliers)
    if user.role == Role.forwarder:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Brak dostępu.")
    q = (select(SupplierContact).join(Supplier, SupplierContact.supplier_id == Supplier.id)
         .where(SupplierContact.is_active))
    q = scope_suppliers(q, user)
    if not supplier_catalog_access(user):
        # kontakty kartoteki to dane Acme — konto bez dostępu widzi tylko swoich nadawców
        q = q.where(Supplier.client_company_id.is_not(None))
    if supplier_id is not None:
        get_scoped(db, Supplier, supplier_id, user)
        q = q.where(SupplierContact.supplier_id == supplier_id)
    return db.scalars(q.order_by(SupplierContact.full_name)).all()


@router.post("/supplier-contacts", response_model=SupplierContactOut, status_code=201)
def create_supplier_contact(body: SupplierContactIn, db: Session = Depends(get_db),
                            user: User = editors):
    get_scoped(db, Supplier, body.supplier_id, user)
    contact = SupplierContact(**body.model_dump())
    db.add(contact)
    audit.record_created(db, contact, user)
    db.commit()
    return contact


# --- przewalutowanie wartości towaru wg NBP ---

@router.get("/fx", response_model=FxConvertOut)
def fx_convert(amount: float, currency: str = "USD", user: User = viewer):
    """Przelicza kwotę na PLN/EUR/USD wg kursów NBP (best-effort — available=False gdy brak).

    Nie dotyka bazy (brak zależności get_db) — to czysty przelicznik na kursach z cache NBP.
    """
    from ..nbp import convert
    return convert(amount, currency)


@router.get("/carriers", response_model=list[CarrierOut])
def list_carriers(db: Session = Depends(get_db), user: User = viewer_or_sales,
                  include_inactive: bool = False):
    # spójnie z pozostałymi słownikami: domyślnie tylko aktywni (dezaktywowany armator
    # znika z list wyboru, ale zostaje przy historycznych kontenerach i wycenach).
    # Panel admina prosi o pełną listę przez include_inactive=true.
    query = select(Carrier).order_by(Carrier.name)
    if not include_inactive:
        query = query.where(Carrier.is_active)
    return db.scalars(query).all()


@router.post("/carriers", response_model=CarrierOut, status_code=201)
def create_carrier(body: CarrierIn, db: Session = Depends(get_db), user: User = admins):
    if db.scalar(select(Carrier).where(Carrier.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki armator już istnieje.")
    carrier = Carrier(name=body.name, demurrage_free_days=body.demurrage_free_days)
    db.add(carrier)
    audit.record_created(db, carrier, user)
    db.commit()
    return carrier


@router.patch("/carriers/{carrier_id}", response_model=CarrierOut)
def update_carrier(carrier_id: int, body: CarrierIn,
                   db: Session = Depends(get_db), user: User = admins):
    carrier = _get_or_404(db, CARRIERS, carrier_id, user)
    clash = db.scalar(select(Carrier).where(Carrier.id != carrier_id, Carrier.name == body.name))
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Taki armator już istnieje (id={clash.id}) — scal duplikaty.")
    audit.record_changes(db, carrier, body.model_dump(exclude_unset=True), user)
    db.commit()
    return carrier


@router.post("/carriers/{carrier_id}/merge", response_model=MergeOut)
def merge_carrier(carrier_id: int, body: MergeIn,
                  db: Session = Depends(get_db), user: User = admins):
    return _merge(db, CARRIERS, carrier_id, body, user)


@router.delete("/carriers/{carrier_id}", status_code=204)
def delete_carrier(carrier_id: int, db: Session = Depends(get_db), user: User = admins):
    _delete(db, CARRIERS, carrier_id, user)


# mapa nie udźwignie nieograniczonej liczby kropek; realny słownik ma ~kilka tysięcy
CPORTS_MAP_LIMIT = 5000


@router.get("/container-ports", response_model=list[ContainerPortOut])
def list_container_ports(q: str = "", with_coords: bool = False,
                         db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Słownik portów kontenerowych (master data globalne, read-only).
    with_coords=true → tylko porty ze współrzędnymi (warstwa mapy trackingu)."""
    query = select(ContainerPort).where(ContainerPort.is_active) \
        .order_by(ContainerPort.code)
    if with_coords:
        query = query.where(ContainerPort.lat.isnot(None), ContainerPort.lon.isnot(None))
    if q.strip():
        needle = f"%{q.strip()}%"
        query = query.where(ContainerPort.code.ilike(needle)
                            | ContainerPort.name.ilike(needle))
    rows = db.scalars(query.limit(CPORTS_MAP_LIMIT + 1)).all()
    if len(rows) > CPORTS_MAP_LIMIT:
        _logger.warning("container-ports: przycięto wynik do %s wierszy", CPORTS_MAP_LIMIT)
        rows = rows[:CPORTS_MAP_LIMIT]
    return rows


@router.delete("/container-ports/{port_id}", status_code=204)
def delete_container_port(port_id: int, db: Session = Depends(get_db), user: User = admins):
    guarded_delete(db, ContainerPort, port_id, user, "port kontenerowy",
                   describe=lambda p: f"{p.code} {p.name}")


@router.get("/material-units", response_model=list[MaterialUnitOut])
def list_material_units(q: str = "", limit: int = Query(default=500, ge=1, le=1000),
                        db: Session = Depends(get_db), user: User = viewer):
    """Jednostki materiałów z MARM (master data globalne, read-only) — wyszukiwarka
    po numerze materiału, paginacja przez limit."""
    query = select(MaterialUnit).order_by(MaterialUnit.material_no, MaterialUnit.unit)
    if q.strip():   # icontains = lower() LIKE lower(): na Postgresie LIKE rozróżnia wielkość liter
        query = query.where(MaterialUnit.material_no.icontains(q.strip(), autoescape=True))
    return db.scalars(query.limit(min(max(limit, 1), 2000))).all()


@router.delete("/material-units/{unit_id}", status_code=204)
def delete_material_unit(unit_id: int, db: Session = Depends(get_db), user: User = admins):
    # master data globalne, nic nie wskazuje na nie FK — ale guard liczy z metadanych,
    # więc ewentualna przyszła tabela z FK zablokuje usuwanie automatycznie
    guarded_delete(db, MaterialUnit, unit_id, user, "jednostka materiału",
                   describe=lambda u: f"{u.material_no} {u.unit}")

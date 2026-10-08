"""Słowniki: dostawcy (per spółka), spedytorzy, magazyny (per spółka), porty, armatorzy.

Tu: dostawcy, spedytorzy, magazyny. Porty/typy kontenerów/kontakty/armatorzy/master data
globalne — dictionaries_ref.py; historia wpisów — dictionaries_audit.py; scalanie i usuwanie
duplikatów — dictionaries_merge.py.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..deps import (
    AdminOnly as admins,
)
from ..deps import CommercialReaders as commercial_readers
from ..deps import ViewerOrSales as viewer_or_sales
from ..deps import (
    apply_company_code_filter,
    filter_suppliers_by_company_code,
    get_scoped,
    is_material_company,
    resolve_company_id,
    scope_company,
    scope_containers,
    scope_suppliers,
    supplier_catalog_access,
)
from ..models import (
    Company,
    Container,
    Forwarder,
    Role,
    Supplier,
    User,
    Warehouse,
)
from ..schemas import (
    ForwarderIn,
    ForwarderOut,
    MergeIn,
    MergeOut,
    SupplierIn,
    SupplierOut,
    SupplierStatsOut,
    WarehouseIn,
    WarehouseOut,
)
from . import dictionaries_audit, dictionaries_ref
from .dictionaries_merge import (  # noqa: F401 — re-eksport: publiczne importy z .dictionaries
    CARRIERS,
    FORWARDERS,
    PORTS,
    SUPPLIERS,
    _delete,
    _Dict,
    _get_or_404,
    _merge,
    _usage,
    fk_usage,
    guarded_delete,
)
from .dictionaries_ref import CPORTS_MAP_LIMIT  # noqa: F401

router = APIRouter(prefix="/api", tags=["słowniki"])

# Zapis słowników = tylko admin. Odczyt (GET) zostaje pod Viewer — słowniki zasilają listy
# wyboru w całej aplikacji. Wcześniej POST/PATCH stały pod Editors (admin + logistyka), choć
# panel administracji front pokazuje wyłącznie adminowi (routing.tsx, canAccess) — logistyk bez
# UI mógł przez samo API przemianować albo dezaktywować port czy dostawcę. Reguła po stronie
# serwera ma odpowiadać temu, co obiecuje interfejs.
# Wyjątek: POST /supplier-contacts zostaje pod Editors — to ekran roboczy zamówień
# (FoundOrderModal), nie panel admina, i logistyk musi tam dodać kontakt u dostawcy.


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db), user: User = viewer_or_sales,
                   company_code: str | None = None,
                   exclude_company_code: str | None = None,
                   include_inactive: bool = False):
    # jak przy portach: panel admina musi widzieć też dezaktywowanych, by móc ich przywrócić
    q = select(Supplier).order_by(Supplier.name)
    if not include_inactive:
        q = q.where(Supplier.is_active)
    q = scope_suppliers(q, user)
    # zawężenie do modułu/zakładki spółki (dostawcy do użycia w tej spółce)
    q = filter_suppliers_by_company_code(q, db, company_code, exclude_company_code)
    rows = db.scalars(q).all()
    full = supplier_catalog_access(user)
    # bez dostępu do kartoteki (magazyn, agencja, spedytor) — same nazwy do list wyboru i filtrów;
    # spedytor nie dostaje też szczegółów nadawców klientów
    return [s if (full if s.client_company_id is None else user.role != Role.forwarder)
            else SupplierOut(id=s.id, name=s.name, is_active=s.is_active,
                             client_company_id=s.client_company_id)
            for s in rows]


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierIn, db: Session = Depends(get_db), user: User = admins):
    client_id = None
    if body.company_id is not None:
        company = db.get(Company, body.company_id)
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spółki.")
        client_id = None if is_material_company(company) else company.id
    if db.scalar(select(Supplier.id).where(
            Supplier.client_company_id.is_not_distinct_from(client_id),
            Supplier.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki dostawca już istnieje.")
    supplier = Supplier(name=body.name, client_company_id=client_id,
                        address=body.address, note=body.note, column_map=body.column_map)
    db.add(supplier)
    audit.record_created(db, supplier, user)
    db.commit()
    return supplier


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, body: SupplierIn,
                    db: Session = Depends(get_db), user: User = admins):
    supplier = _get_or_404(db, SUPPLIERS, supplier_id, user)
    # sprawdzamy tylko zmianę nazwy nadawcy spółki-klienta: w kartotece kluczem jest kod SAP
    # i po migracji każda dawna kopia ACME/PT ma bliźniaka o tej samej nazwie (inaczej każdy
    # PATCH, np. „Nieaktywny" z niezmienioną nazwą, kończyłby się 409)
    clash = None
    if supplier.client_company_id is not None and body.name != supplier.name:
        clash = db.scalar(select(Supplier).where(
            Supplier.id != supplier_id,
            Supplier.client_company_id == supplier.client_company_id,
            Supplier.name == body.name))
    if clash:
        # celowo: nazwa zajęta przez inny wpis tego samego właściciela to najczęściej duplikat
        # do scalenia, a nie pomyłka — podpowiadamy właściwe narzędzie zamiast suchego 409.
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Taki dostawca już istnieje (id={clash.id}) — scal duplikaty.")
    audit.record_changes(db, supplier, body.model_dump(exclude_unset=True, exclude={"company_id"}),
                         user)
    db.commit()
    return supplier


@router.post("/suppliers/{supplier_id}/merge", response_model=MergeOut)
def merge_supplier(supplier_id: int, body: MergeIn,
                   db: Session = Depends(get_db), user: User = admins):
    return _merge(db, SUPPLIERS, supplier_id, body, user)


@router.delete("/suppliers/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int, db: Session = Depends(get_db), user: User = admins):
    _delete(db, SUPPLIERS, supplier_id, user)


@router.get("/suppliers/{supplier_id}/stats", response_model=SupplierStatsOut)
def supplier_stats(supplier_id: int, db: Session = Depends(get_db),
                   user: User = commercial_readers):   # magazyn/agencja nie widzą dostawcy
    """#39: KPI karty dostawcy — liczone w zakresie usera (scope_containers), nie
    globalnie. Dwa zapytania: jedno na dostawy zakończone (on-time/transit), jedno
    na ostatnie 20 kontenerów; liczba aktywnych to trzeci, trywialny count()."""
    _get_or_404(db, SUPPLIERS, supplier_id, user)  # 404 + izolacja per spółka

    active_containers = db.scalar(scope_containers(
        select(func.count()).select_from(Container).where(
            Container.supplier_id == supplier_id, Container.open_in_queue()),  # otwarte w kolejce
        user)) or 0

    completed = db.execute(scope_containers(
        select(Container.eta, Container.etd, Container.atd).where(
            Container.supplier_id == supplier_id, Container.atd.isnot(None)),
        user)).all()
    on_time_pct = None
    with_eta = [r for r in completed if r.eta is not None]
    if with_eta:
        on_time = sum(1 for r in with_eta if r.atd <= r.eta)
        on_time_pct = round(on_time / len(with_eta) * 100, 1)
    avg_transit_days = None
    transits = [(r.atd - r.etd).days for r in completed if r.etd is not None]
    if transits:
        avg_transit_days = round(sum(transits) / len(transits), 1)

    recent = db.scalars(scope_containers(
        select(Container).where(Container.supplier_id == supplier_id)
        .order_by(Container.created_at.desc()).limit(20),
        user)).all()

    return SupplierStatsOut(active_containers=active_containers, on_time_pct=on_time_pct,
                            avg_transit_days=avg_transit_days,
                            recent_containers=[
                                {"id": c.id, "container_no": c.container_no,
                                 "status": c.status.value, "eta": c.eta, "atd": c.atd,
                                 "notify_date": c.notify_date}
                                for c in recent])


@router.get("/forwarders", response_model=list[ForwarderOut])
def list_forwarders(include_inactive: bool = False,
                    db: Session = Depends(get_db), user: User = viewer_or_sales):
    query = select(Forwarder).order_by(Forwarder.name)
    # panel admina (include_inactive) widzi też dezaktywowanych, by móc ich przywrócić;
    # spedytor i listy wyboru w reszcie panelu — tylko aktywni
    if not (include_inactive and user.role != Role.forwarder):
        query = query.where(Forwarder.is_active)
    forwarders = db.scalars(query).all()
    if user.role in (Role.forwarder, Role.customs, Role.sales):
        # dane kontaktowe spedytorów (e-mail, osoba, telefon, adres, notatka) są wewnętrzne:
        # partnerzy zewnętrzni (konkurencja) i sprzedaż dostają tylko nazwy do list/filtrów
        return [ForwarderOut(id=f.id, name=f.name, is_active=f.is_active) for f in forwarders]
    return forwarders


@router.post("/forwarders", response_model=ForwarderOut, status_code=201)
def create_forwarder(body: ForwarderIn, db: Session = Depends(get_db), user: User = admins):
    if db.scalar(select(Forwarder).where(Forwarder.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki spedytor już istnieje.")
    forwarder = Forwarder(name=body.name, email=body.email, is_active=body.is_active,
                          contact_person=body.contact_person, contact_phone=body.contact_phone,
                          address=body.address, note=body.note, language=body.language)
    db.add(forwarder)
    audit.record_created(db, forwarder, user)
    db.commit()
    return forwarder


@router.patch("/forwarders/{forwarder_id}", response_model=ForwarderOut)
def update_forwarder(forwarder_id: int, body: ForwarderIn,
                     db: Session = Depends(get_db), user: User = admins):
    forwarder = db.get(Forwarder, forwarder_id)
    if not forwarder:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spedytora.")
    if db.scalar(select(Forwarder).where(Forwarder.id != forwarder_id, Forwarder.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki spedytor już istnieje.")
    audit.record_changes(db, forwarder, body.model_dump(exclude_unset=True), user)
    db.commit()
    return forwarder


@router.post("/forwarders/{forwarder_id}/merge", response_model=MergeOut)
def merge_forwarder(forwarder_id: int, body: MergeIn,
                    db: Session = Depends(get_db), user: User = admins):
    return _merge(db, FORWARDERS, forwarder_id, body, user)


@router.delete("/forwarders/{forwarder_id}", status_code=204)
def delete_forwarder(forwarder_id: int, db: Session = Depends(get_db), user: User = admins):
    _delete(db, FORWARDERS, forwarder_id, user)


@router.get("/warehouses", response_model=list[WarehouseOut])
def list_warehouses(db: Session = Depends(get_db), user: User = viewer_or_sales,
                    company_code: str | None = None,
                    exclude_company_code: str | None = None):
    q = select(Warehouse).where(Warehouse.is_active).order_by(Warehouse.name)
    if user.role != Role.forwarder:
        q = scope_company(q, Warehouse.company_id, user)
    # zawężenie do modułu/zakładki (np. tylko magazyny spółki Acme w e-mailu do spedycji)
    q = apply_company_code_filter(q, db, Warehouse.company_id, company_code, exclude_company_code)
    warehouses = db.scalars(q).all()
    if user.role == Role.forwarder:
        # spedytor nie potrzebuje e-maili magazynów obcych spółek
        for w in warehouses:
            w.email = ""
    return warehouses


@router.post("/warehouses", response_model=WarehouseOut, status_code=201)
def create_warehouse(body: WarehouseIn, db: Session = Depends(get_db), user: User = admins):
    company_id = resolve_company_id(db, user, body.company_id)
    existing = db.scalar(select(Warehouse).where(
        Warehouse.company_id == company_id, Warehouse.name == body.name))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki magazyn już istnieje.")
    warehouse = Warehouse(name=body.name, company_id=company_id, email=body.email,
                          country=body.country, default_daily_limit=body.default_daily_limit,
                          address=body.address, contact_phone=body.contact_phone,
                          entry_instructions=body.entry_instructions,
                          slot_windows=body.slot_windows.replace(' ', ''), slot_capacity=body.slot_capacity)
    db.add(warehouse)
    audit.record_created(db, warehouse, user)
    db.commit()
    return warehouse


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseOut)
def update_warehouse(warehouse_id: int, body: WarehouseIn,
                     db: Session = Depends(get_db), user: User = admins):
    warehouse = get_scoped(db, Warehouse, warehouse_id, user)
    if db.scalar(select(Warehouse).where(
            Warehouse.id != warehouse_id, Warehouse.company_id == warehouse.company_id,
            Warehouse.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki magazyn już istnieje.")
    # tylko pola przysłane — edycja w słownikach nie wysyła slotów i nie może ich zerować
    changes = body.model_dump(exclude_unset=True, exclude={"company_id"})
    if "slot_windows" in changes:
        changes["slot_windows"] = changes["slot_windows"].replace(' ', '')
    audit.record_changes(db, warehouse, changes, user)
    db.commit()
    return warehouse


@router.delete("/warehouses/{warehouse_id}", status_code=204)
def delete_warehouse(warehouse_id: int, db: Session = Depends(get_db), user: User = admins):
    get_scoped(db, Warehouse, warehouse_id, user)
    guarded_delete(db, Warehouse, warehouse_id, user, "magazyn")


# porty, typy kontenerów, kontakty, armatorzy, master data globalne i historia wpisów —
# osobne moduły; dołączone na końcu, więc kolejność tras (prefiks /api, tag) bez zmian
router.include_router(dictionaries_ref.router)
router.include_router(dictionaries_audit.router)

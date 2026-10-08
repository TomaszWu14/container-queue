from fastapi import Depends, HTTPException, status
from sqlalchemy import ColumnElement, and_, false, func, or_, select, true
from sqlalchemy.orm import Session

from .config import settings
from .models import Attachment, Company, Container, DocumentType, Role, Supplier, User
from .security import PARTNER_ROLES, can_view_all, require_roles


def apply_company_code_filter(query, db: Session, column, company_code: str | None,
                              exclude_company_code: str | None):
    """Zawęża/wyklucza zapytanie po kodzie spółki (moduł/zakładka).

    Wspólne dla kolejki (Container.company_id) i słowników z company_id (magazyny) —
    dostawcy mają własny `filter_suppliers_by_company_code` — nieznany kod daje pusty
    wynik (sentinel -1), a wykluczenie działa tylko dla istniejącej spółki.
    """
    if company_code:
        company = db.scalar(select(Company).where(Company.code == company_code))
        query = query.where(column == (company.id if company else -1))
    if exclude_company_code:
        company = db.scalar(select(Company).where(Company.code == exclude_company_code))
        if company:
            query = query.where(column != company.id)
    return query


def own_company_id(user: User) -> int | None:
    """Spółka konta na osi separacji spółek. Partner zewnętrzny (spedytor, agencja celna)
    nie należy do żadnej spółki: company_id ustawione mu przez pomyłkę (stare dane) jest
    ignorowane — fail-closed, bez migracji."""
    return None if user.role in PARTNER_ROLES else user.company_id


def company_filter_ids(user: User) -> list[int] | None:
    """None = widzi wszystkie spółki; lista = tylko wskazane."""
    if can_view_all(user):
        return None
    own = own_company_id(user)
    if own is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Konto bez przypisanej spółki.")
    return [own]


def company_column(model):
    """Kolumna wyznaczająca spółkę rekordu danego modelu albo None (model globalny).
    Company nie ma company_id — spółką jest sam rekord, więc jego `id`."""
    if model is Company:
        return Company.id
    return getattr(model, "company_id", None)


def scope_company(query, column, user: User):
    """Zawęża zapytanie po kolumnie company_id wg separacji spółek (modele inne niż
    Container — dla kontenerów użyj scope_containers, który zna też role)."""
    ids = company_filter_ids(user)
    if ids is not None:
        query = query.where(column.in_(ids))
    return query


def scope_containers(query, user: User):
    """Zawęża zapytanie o kontenery do zakresu użytkownika.

    Spedytor widzi kontenery przypisane do jego firmy spedycyjnej (wszystkich
    spółek, które mu zleciły); konto magazynowe z przypisanym magazynem
    (np. firma zewnętrzna DLT) — tylko kontenery swojego magazynu;
    pozostali — wg separacji spółek.
    """
    if user.role == Role.forwarder:
        if user.forwarder_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Konto bez przypisanego spedytora.")
        return query.where(Container.forwarder_id == user.forwarder_id)
    if user.role == Role.customs:
        # agencja celna widzi tylko kontenery, których odprawę jej zlecono
        if user.customs_agency_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Konto bez przypisanej agencji celnej.")
        return query.where(Container.customs_agency_id == user.customs_agency_id)
    ids = company_filter_ids(user)
    if ids is not None:
        query = query.where(Container.company_id.in_(ids))
    # W14 #91: logistyk z ustawioną listą magazynów widzi tylko ich kontenery;
    # pusta/NULL lista = wszystkie (dotychczasowe zachowanie). Inne role bez zmian.
    if user.role == Role.logistics and user.allowed_warehouse_ids:
        query = query.where(
            Container.warehouse_id.in_([int(i) for i in user.allowed_warehouse_ids]))
    if user.role == Role.warehouse:
        # fail-closed: konto magazynu (np. zewnętrzny DLT) bez przypisanego magazynu nie
        # może widzieć całej spółki — brak warehouse_id = brak dostępu (jak spedytor bez firmy)
        if user.warehouse_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Konto magazynu bez przypisanego magazynu.")
        query = query.where(Container.warehouse_id == user.warehouse_id)
    return query


def _scope_forwarder_resource(query, user: User, model):
    """Zasób z własnym spedytorem i spółką (zlecenie transportowe, awizacja): magazyn bez
    wglądu; spedytor widzi przypisane do NIEGO; reszta — wg separacji spółek."""
    if user.role == Role.warehouse:
        return query.where(false())
    if user.role == Role.forwarder:
        if user.forwarder_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Konto bez przypisanego spedytora.")
        return query.where(model.forwarder_id == user.forwarder_id)
    ids = company_filter_ids(user)
    if ids is not None:
        query = query.where(model.company_id.in_(ids))
    return query


def scope_transport_orders(query, user: User):
    """Lista zleceń transportowych — odpowiednik `_enforce_scope` dla TransportOrder
    (spedytor zlecenia bywa inny niż kontenera)."""
    from .models import TransportOrder
    return _scope_forwarder_resource(query, user, TransportOrder)


def scope_avizo_requests(query, user: User):
    """Lista awizacji — spedytor widzi tylko swoje (awizacja w aplikacji, 2026-10-07)."""
    from .models import AvizoRequest
    return _scope_forwarder_resource(query, user, AvizoRequest)


def check_container_access(user: User, container: Container) -> None:
    if user.role == Role.forwarder:
        if container.forwarder_id != user.forwarder_id or user.forwarder_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
        return
    if user.role == Role.customs:
        if container.customs_agency_id != user.customs_agency_id \
                or user.customs_agency_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
        return
    check_company_access(user, container.company_id)
    # W14 #91: ta sama reguła co w scope_containers — lista i dostęp po id spójne
    if user.role == Role.logistics and user.allowed_warehouse_ids \
            and container.warehouse_id not in {int(i) for i in user.allowed_warehouse_ids}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
    if user.role == Role.warehouse:
        if user.warehouse_id is None or container.warehouse_id != user.warehouse_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")


# magazyn (też zewnętrzny DLT) rozładowuje — CMR, packing lista i inne operacyjne tak;
# faktury z cenami, B/L i SAD niosą dostawcę i wartości (2026-10-05)
_WAREHOUSE_HIDDEN_TILES = frozenset({"PI", "CI", "BL", "SAD_DRAFT", "SAD_PZ", "SAD_PW"})


def forwarder_may_see(attachment: Attachment, user: User) -> bool:
    """Spedytor widzi tylko CMR i pliki, które sam wgrał — dokumenty odprawowe i handlowe są
    dla niego ukryte (decyzja 2026-09-28; faktury za transport to osobny moduł FreightInvoice).
    Magazyn: wszystko poza typami handlowymi/odprawowymi (_WAREHOUSE_HIDDEN_TILES); plik bez
    typu tylko własny (decyzja 2026-10-05 — nieopisany plik może być fakturą; packing list widoczny).
    Filtr list załączników; pojedynczy rekord egzekwuje `_enforce_scope` (get_scoped(Attachment)).
    Typ dokumentu poznajemy po nazwie — CMR nie ma kodu kafelka (`DocumentType.tile_code`)."""
    if user.role == Role.warehouse:
        if attachment.document_type is None:
            return attachment.uploaded_by_id == user.id
        return attachment.document_type.tile_code not in _WAREHOUSE_HIDDEN_TILES
    if user.role != Role.forwarder:
        return True
    doc_type = attachment.document_type.name if attachment.document_type else ""
    return attachment.uploaded_by_id == user.id or "CMR" in doc_type.upper()


def may_see_intake(batch, user: User) -> bool:
    """Wgranie w poczekalni: spedytor tylko własne (jak forwarder_may_see — cudze części mogą być
    fakturami/SAD); reszta wg kontenera (check_container_access)."""
    return user.role != Role.forwarder or batch.created_by_id == user.id


def forwarder_may_see_sql(user: User) -> ColumnElement[bool]:
    """`forwarder_may_see` jako warunek SQL — do zapytań z limitem (filtr po limicie dawałby
    mniej wyników). Zapytanie musi mieć outer join DocumentType po Attachment.document_type_id.
    Zgodność z wersją Pythonową pilnuje test (tests/test_documents_search_scope.py)."""
    if user.role == Role.warehouse:
        return or_(and_(DocumentType.id.is_(None), Attachment.uploaded_by_id == user.id),
                   and_(DocumentType.id.is_not(None),
                        or_(DocumentType.tile_code.is_(None),
                            DocumentType.tile_code.not_in(_WAREHOUSE_HIDDEN_TILES))))
    if user.role != Role.forwarder:
        return true()
    return or_(Attachment.uploaded_by_id == user.id,
               func.upper(func.coalesce(DocumentType.name, "")).like("%CMR%"))


def resolve_company_id(db: Session, user: User, requested: int | None) -> int:
    """Ustala spółkę dla tworzonych rekordów, pilnując separacji."""
    if can_view_all(user):
        if requested is None:
            if user.company_id is not None:
                return user.company_id
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Wskaż spółkę (company_id).")
        if not db.get(Company, requested):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spółki.")
        return requested
    own = own_company_id(user)
    if own is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Konto bez przypisanej spółki.")
    if requested is not None and requested != own:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Brak dostępu do tej spółki.")
    return own


def check_company_access(user: User, company_id: int) -> None:
    if not can_view_all(user) and own_company_id(user) != company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")


# --- kartoteka dostawców (spec 2026-09-25-kartoteka-dostawcy §2 „Widoczność") ---
# Kartoteka (Supplier.client_company_id IS NULL) należy do Acme i spółek pracujących na jego
# materiałach (settings.supplier_company_codes). Nadawcy spółek-klientów (client_company_id =
# spółka) są widoczni tylko dla tej spółki. Routery wołają wyłącznie te funkcje.

CATALOG_ROLES = (Role.admin, Role.logistics, Role.purchasing)


def material_company_codes() -> set[str]:
    return {c.strip().upper() for c in settings.supplier_company_codes.split(",") if c.strip()}


def is_material_company(company: Company | None) -> bool:
    return company is not None and company.code.upper() in material_company_codes()


def supplier_clause_for_company(company: Company):
    """Dostawcy, których wolno użyć w rekordach spółki (kontener, zamówienie, alias, faktura):
    jej nadawcy + kartoteka, gdy spółka pracuje na materiałach Acme."""
    own = Supplier.client_company_id == company.id
    return or_(Supplier.client_company_id.is_(None), own) if is_material_company(company) else own


def supplier_catalog_access(user: User) -> bool:
    """Szczegóły kartoteki (adres, kod SAP, kontakty, profil, statystyki): admin, logistyka,
    zakupy — konta grupowe albo spółki z materiałami. Magazyn, spedytor, agencja, klienci: nie."""
    if user.role not in CATALOG_ROLES:
        return False
    return can_view_all(user) or is_material_company(user.company)


def scope_suppliers(query, user: User):
    """Lista dostawców (listy wyboru, filtry kolejki). Spedytor i konta grupowe — wszyscy
    (spedytor i konta bez dostępu do kartoteki dostają same nazwy — list_suppliers); konto
    spółki — jej nadawcy + kartoteka, gdy spółka pracuje na materiałach Acme."""
    if user.role == Role.forwarder or can_view_all(user):
        return query
    own = Supplier.client_company_id.in_(company_filter_ids(user))
    if is_material_company(user.company):
        return query.where(or_(Supplier.client_company_id.is_(None), own))
    return query.where(own)


def filter_suppliers_by_company_code(query, db: Session, company_code: str | None,
                                     exclude_company_code: str | None):
    """Zakładka/moduł spółki na liście dostawców: `company_code` = dostawcy do użycia w tej
    spółce; `exclude_company_code` = wszyscy poza nimi. Nieznany kod = pusty wynik."""
    if company_code:
        company = db.scalar(select(Company).where(Company.code == company_code))
        query = query.where(supplier_clause_for_company(company) if company else false())
    if exclude_company_code:
        company = db.scalar(select(Company).where(Company.code == exclude_company_code))
        if company:
            query = query.where(Supplier.id.not_in(
                select(Supplier.id).where(supplier_clause_for_company(company))))
    return query


def check_supplier_access(user: User, supplier: Supplier) -> None:
    """Dostęp do jednego dostawcy (404 jak brak — bez enumeracji)."""
    if supplier.client_company_id is not None:
        return check_company_access(user, supplier.client_company_id)
    if not supplier_catalog_access(user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")


def get_company_by_code(db: Session, user: User, code: str) -> Company:
    """Spółka po kodzie z kontrolą dostępu. Poza zakresem → 404 (jak brak), by nie
    zdradzać istnienia cudzej spółki (spójnie z check_company_access)."""
    company = db.scalar(select(Company).where(Company.code == code))
    if not company or (not can_view_all(user) and own_company_id(user) != company.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spółki.")
    return company


# współdzielone zależności FastAPI (Depends jest wyliczany per-request — bezpieczne globalnie)
# Czytelnicy: role wymienione JAWNIE (fail-closed jak oś izolacji danych). Nowa wartość
# w enum Role NIE dziedziczy po cichu dostępu do endpointów gated `Viewer` — trzeba dopisać
# ją tutaj świadomie. (Bliźniaczy `ViewerNoPurchasing` niżej to ta sama lista minus zakupy.)
READER_ROLES = (Role.admin, Role.logistics, Role.warehouse,
                Role.forwarder, Role.customs, Role.purchasing)
Viewer = Depends(require_roles(*READER_ROLES))
# odczyty dostępne też dla sprzedaży (Role.sales jest POZA READER_ROLES — fail-closed):
# kolejka, karta kontenera, kalendarz, śledzenie, słowniki, powiadomienia, wiedza
# (+ osobiste: oznacz przeczytane, potwierdź komunikat, obserwuj kontener/statek).
# Każda inna trasa (i każdy zapis) pozostaje dla sprzedaży zamknięta.
ViewerOrSales = Depends(require_roles(*READER_ROLES, Role.sales))
# Baza wiedzy (pinezki, tematy): wspólna dla spółek grupy, BEZ partnerów zewnętrznych —
# spedytor i agencja celna jej nie widzą (ACL-001, decyzja 2026-09-28). Komunikaty do ról osobno.
INTERNAL_ROLES = tuple(r for r in (*READER_ROLES, Role.sales)
                       if r not in (Role.forwarder, Role.customs))
InternalReaders = Depends(require_roles(*INTERNAL_ROLES))
InternalWriters = Depends(require_roles(*(r for r in INTERNAL_ROLES if r != Role.sales)))
# dane wewnętrzne grupy (wywołania DLT, PAZ, cele zapasu, mapy dostawca↔materiał, obsada
# magazynu): czytelnicy BEZ partnerów zewnętrznych i bez sprzedaży
StaffReaders = Depends(require_roles(*(r for r in READER_ROLES if r not in PARTNER_ROLES)))
# Specjalna troska — podgląd: logistyka/admin + sprzedaż (edycja zostaje Editors)
CareReaders = Depends(require_roles(Role.admin, Role.logistics, Role.sales))
Editors = Depends(require_roles(Role.admin, Role.logistics))
WarehouseOrEditors = Depends(require_roles(Role.admin, Role.logistics, Role.warehouse))
# potwierdzanie daty dostawy zapisuje notify_date — zakres jak Editors, plus spedytor
PlanConfirmers = Depends(require_roles(Role.admin, Role.logistics, Role.forwarder))
AdminOnly = Depends(require_roles(Role.admin))
# operacje spedytora na SWOICH kontenerach (zakres: scope_containers/check_container_access):
# braki dokumentów celnych, SMS do kierowcy (audyt UI S10, 2026-09-27)
ForwarderOrEditors = Depends(require_roles(Role.admin, Role.logistics, Role.forwarder))
# dane zakupowe/kosztowe (zamówienia, konsolidacja, faktury transportowe): bez magazynu,
# spedytora i agencji celnej — allow-lista jak READER_ROLES
PurchasingReaders = Depends(require_roles(Role.admin, Role.logistics, Role.purchasing))
# dane handlowe/analizy spółki (zamówienia, dashboard, statystyki): czytelnicy BEZ magazynu
NonWarehouseViewers = Depends(require_roles(*(r for r in READER_ROLES if r != Role.warehouse)))
# pozycje zamówień i linki SENT: dodatkowo bez agencji celnej
CommercialReaders = Depends(require_roles(
    *(r for r in READER_ROLES if r not in (Role.warehouse, Role.customs))))
# zawartość kontenera (pozycje REF): jak CommercialReaders + magazyn TYLKO do odczytu
# (audyt UI C13, 2026-09-27) — zakres magazynu pilnuje check_container_access
ContentsReaders = Depends(require_roles(
    *(r for r in READER_ROLES if r != Role.customs), Role.sales))  # + sprzedaż: odczyt (2026-09-27)


def can_edit_global_data(user: User) -> bool:
    """Dane WSPÓLNE grupy (PAZ, cele zapasu, stany DLT, MARM, porty kontenerowe; ACL-003):
    admin, logistyka grupowa (view_all) albo logistyka spółki-właściciela materiałów
    (SUPPLIER_COMPANY_CODES, np. Acme). Logistyk innej spółki tylko czyta."""
    if user.role == Role.admin:
        return True
    return user.role == Role.logistics and (can_view_all(user) or is_material_company(user.company))


def check_global_data_editor(user: User) -> None:
    if not can_edit_global_data(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Dane wspólne dla spółek grupy zmienia admin, logistyka grupowa "
                            "albo logistyka spółki-właściciela materiałów.")


def _global_data_editor(user: User = Depends(require_roles(Role.admin, Role.logistics))) -> User:
    check_global_data_editor(user)
    return user


# zapis danych wspólnych grupy — permissions.yaml: logistyka „?” (konto jednej spółki → 403)
GlobalDataEditors = Depends(_global_data_editor)


# Wyceny (koszty): allow-lista — czytelnicy bez działu zakupów (i bez sprzedaży, która jest
# poza READER_ROLES). Nowa rola NIE dziedziczy dostępu do wycen po cichu.
ViewerNoPurchasing = Depends(require_roles(*(r for r in READER_ROLES if r != Role.purchasing)))


# --- D1: strukturalny scoping (fundament; wpinany w migracji PR-2+) ---

def _enforce_scope(db: Session, user: User, obj) -> None:
    """Jednolita reguła izolacji per zasób. Fail-closed: nieznany kształt → 403.

    - Container → check_container_access (spółka + rola: forwarder/customs/warehouse),
    - cokolwiek z `container_id` (TransportOrder/Job, Attachment, SentLink-per-kontener,
      TrackingEvent…) → dostęp przez kontener-rodzica,
    - ComplaintPhoto → przez reklamację → kontener,
    - Supplier → check_supplier_access (kartoteka / nadawca spółki-klienta),
    - cokolwiek z samym `company_id` (Order, SentLink-per-spółka) → check_company_access.
    """
    from .models import (AvizoRequest, Complaint, ComplaintPhoto, IntakeBatch, IntakeItem, InvoiceJob,
                         TransportOrder)
    if isinstance(obj, Container):
        return check_container_access(user, obj)
    if isinstance(obj, (IntakeBatch, IntakeItem)):
        # poczekalnia: przez wgranie → kontener kontekstu; musi wyprzedzać gałąź container_id
        batch = obj if isinstance(obj, IntakeBatch) else obj.batch
        if batch.container_id is None:   # poczta bez dopasowania: admin/logistyka spółki wgrania
            if user.role not in (Role.admin, Role.logistics) or (
                    batch.company_id is None and not can_view_all(user)):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
            return check_company_access(user, batch.company_id) if batch.company_id else None
        parent = db.get(Container, batch.container_id)
        if parent is None or not may_see_intake(batch, user):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
        return check_container_access(user, parent)
    if isinstance(obj, InvoiceJob):
        # dokument faktury: przez paczkę → kontener (InvoiceBatch ma container_id — gałąź niżej)
        parent = db.get(Container, obj.batch.container_id) if obj.batch else None
        if parent is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
        return check_container_access(user, parent)
    if isinstance(obj, (TransportOrder, AvizoRequest)):
        # zlecenie transportowe / awizacja: magazyn poza zakresem; spedytor wg spedytora
        # ZLECENIA (nie kontenera — bywają różni); reszta wg spółki zlecenia.
        # Musi wyprzedzać ogólną gałąź container_id poniżej (TransportOrder też ją ma).
        if user.role == Role.warehouse:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
        if user.role == Role.forwarder:
            if obj.forwarder_id != user.forwarder_id or user.forwarder_id is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
            return
        return check_company_access(user, obj.company_id)
    if isinstance(obj, Supplier):
        # dostawca nie ma company_id: kartoteka (reguła ról/spółek) albo nadawca klienta
        return check_supplier_access(user, obj)
    if isinstance(obj, Attachment):
        # wspólny plik (attachment_links): wystarczy dostęp do właściciela ALBO któregoś
        # powiązanego kontenera; spedytor/magazyn i tak tylko CMR i własne — jednolite 404
        if not (_sees_any(db, user, [obj.container_id, *(link.container_id for link in obj.links)])
                and forwarder_may_see(obj, user)):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
        return
    container_id = getattr(obj, "container_id", None)
    if container_id is not None:
        parent = db.get(Container, container_id)
        if parent is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
        return check_container_access(user, parent)
    if isinstance(obj, ComplaintPhoto):
        complaint = db.get(Complaint, obj.complaint_id)
        parent = db.get(Container, complaint.container_id) if complaint else None
        if parent is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
        return check_container_access(user, parent)
    company_id = getattr(obj, "company_id", None)
    if company_id is not None:
        return check_company_access(user, company_id)
    # brak znanej ścieżki izolacji — nie zgadujemy, blokujemy
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Brak reguły izolacji dla zasobu.")


def _sees_any(db: Session, user: User, container_ids: list[int]) -> bool:
    for container_id in container_ids:
        parent = db.get(Container, container_id)
        try:
            if parent is not None:
                check_container_access(user, parent)
                return True
        except HTTPException:
            continue
    return False


def visible_overrides(material, user: User) -> list:
    """Nadpisania master daty materiału widoczne dla użytkownika: admin/logistyka grupy —
    wszystkie spółki; konto spółki — tylko własne (cudze nadpisania to dane cudzej spółki)."""
    if can_view_all(user):
        return list(material.overrides)
    return [o for o in material.overrides if o.company_id == own_company_id(user)]


def _fetch_or_404(db: Session, model, obj_id: int, options):
    obj = db.scalar(select(model).options(*options).where(model.id == obj_id))
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
    return obj


def get_scoped(db: Session, model, obj_id: int, user: User, *, options=()):
    """Obowiązkowy fetch-po-id z egzekwowaną izolacją. Zastępuje rozsiane
    „db.get(...) + ręczny check" (avizo, forwarding, complaints, sent-links…).
    Brak rekordu i rekord poza zakresem dają to samo 404 (bez enumeracji)."""
    obj = _fetch_or_404(db, model, obj_id, options)
    _enforce_scope(db, user, obj)
    return obj


def get_company_scoped(db: Session, model, obj_id: int, user: User, *, options=()):
    """Fetch-po-id z izolacją WYŁĄCZNIE po company_id rekordu — dla modeli, w których
    container_id to opcjonalne powiązanie, nie właściciel (PurchaseOrder: zamówienie
    w koszyku/cudzym kontenerze należy do swojej spółki). get_scoped routowałby je
    przez kontener."""
    obj = _fetch_or_404(db, model, obj_id, options)
    check_company_access(user, obj.company_id)
    return obj

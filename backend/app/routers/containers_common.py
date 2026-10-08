"""Wspólne helpery routerów kolejki kontenerów: eager-load, serializacja z maskowaniem
pól per rola, izolacja spółki, numeracja transportu, limity dzienne i kolizje paczek."""
import datetime
from collections.abc import Mapping
from typing import cast

from fastapi import HTTPException, status
from sqlalchemy import CursorResult, any_, case, func, select, update
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import set_committed_value

from ..deps import get_scoped, scope_containers, supplier_clause_for_company
from ..models import (
    CUSTOMS_CLEARED,
    CUSTOMS_IN_PROGRESS,
    AuditLog,
    CalendarDay,
    Company,
    Container,
    ContainerStatus,
    CustomsStatus,
    DailyLimit,
    Order,
    Role,
    Supplier,
    TransportJob,
    TransportJobContainer,
    TransportJobStatus,
    User,
    Warehouse,
    utcnow,
)
from ..notifications import notify, warehouse_users
from ..planning import estimated_eta
from ..schemas import ContainerOut

_LOAD = (
    selectinload(Container.company), selectinload(Container.order),
    selectinload(Container.supplier), selectinload(Container.forwarder),
    selectinload(Container.customs_agency_rel),
    selectinload(Container.customs_case_status_rel),
    selectinload(Container.warehouse), selectinload(Container.port),
    selectinload(Container.carrier),
)


def _fk_filter(query, column, raw: str | None):
    """Filtr po kluczu obcym z obsługą wartości „empty" (brak przypisania — IS NULL)."""
    if not raw:
        return query
    if raw == "empty":
        return query.where(column.is_(None))
    if raw.isascii() and raw.isdigit():   # "²" przechodzi isdigit(), ale int() rzuca
        return query.where(column == int(raw))
    return query  # nieznana wartość — ignorujemy zamiast błędu


def _enum_filter(query, column, raw: str | None, enum_cls):
    """Filtr po kolumnie enum z sentinelem „empty" (spójnie z _fk_filter, #5/C3).

    Przyjmuje wartość enuma („empty" → IS NULL); nieznana wartość → 422 (nie cichy
    pusty wynik). Dzięki temu wariant „lista z pustym" na kolumnie enum nie wywali
    całego żądania 422, a złe wejście dostaje jawny błąd walidacji.
    """
    if not raw:
        return query
    if raw == "empty":
        return query.where(column.is_(None))
    try:
        value = enum_cls(raw)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Nieprawidłowa wartość filtra: {raw}") from None
    return query.where(column == value)


def _transport_prefix(company: Company, year: int) -> str:
    return f"{(company.code or 'X')[0].upper()}T-{year}-"


def _max_transport_seq(db: Session, prefix: str) -> int:
    """Najwyższa część liczbowa istniejących ID transportu dla prefiksu.

    Numer ma zera wiodące do 4 cyfr, więc (długość malejąco, tekst malejąco) = liczbowo
    malejąco — pierwszy numer z samych cyfr to maksimum (tekstowo „...-9999” > „...-10000”).
    Baza zwraca kilka wierszy zamiast wszystkich numerów roku (DB-011).
    """
    query = (select(Container.transport_id).where(Container.transport_id.like(f"{prefix}%"))
             .order_by(func.length(Container.transport_id).desc(),
                       Container.transport_id.desc()))
    for batch in (query.limit(50), query):   # pełny odczyt tylko, gdy 50 śmieciowych sufiksów
        for tid in db.scalars(batch):
            suffix = tid[len(prefix):]
            if suffix.isascii() and suffix.isdigit():
                return int(suffix)
    return 0


def reserve_transport_seqs(db: Session, prefix: str, count: int = 1) -> int:
    """DB-011: rezerwuje `count` kolejnych numerów dla prefiksu, zwraca pierwszy.

    Upsert licznika (transport_id_counters) w transakcji żądania: wiersz licznika jest
    zablokowany do commitu, więc równoległa transakcja czeka i dostaje następne numery
    (wcześniej obie liczyły ten sam max+1 → IntegrityError). GREATEST z istniejącym maksimum
    naprawia licznik, gdyby numer nadano poza nim (np. stary proces w trakcie deployu).
    Wycofana transakcja cofa też licznik — bez dziur po nieudanym imporcie."""
    from ..models import TransportIdCounter
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as upsert
    else:
        from sqlalchemy.dialects.sqlite import insert as upsert
    floor = _max_transport_seq(db, prefix)
    current = TransportIdCounter.last_seq
    stmt = upsert(TransportIdCounter).values(prefix=prefix, last_seq=floor + count)
    stmt = stmt.on_conflict_do_update(
        index_elements=[TransportIdCounter.prefix],
        set_={"last_seq": case((current > floor, current), else_=floor) + count},
    ).returning(TransportIdCounter.last_seq)
    return db.execute(stmt).scalar_one() - count + 1


def next_transport_id(db: Session, company: Company, year: int) -> str:
    """Kolejny identyfikator transportu, np. AT-2026-0001 (A = spółka, T = transport)."""
    prefix = _transport_prefix(company, year)
    return f"{prefix}{reserve_transport_seqs(db, prefix):04d}"


# pola handlowe/wewnętrzne ukrywane przed zewnętrznym magazynem (np. DLT) — widzi
# tylko dane operacyjne potrzebne do przyjęcia i rozładunku kontenera
_WAREHOUSE_HIDDEN = {
    "supplier_id": None, "supplier_name": None, "supplier_raw": "",
    "order_id": None, "order_number": None, "order_numbers": "",
    "forwarder_id": None, "forwarder_name": None,
    "carrier_id": None, "carrier_name": None,
    "notes": "", "purchase_note": "", "document_flow": "",
    "driver_id_no": "",   # wrażliwe PII — nr dokumentu tożsamości kierowcy
    "customer_name": "", "customer_address": "", "customer_contact": "",
}

# Agencja celna to partner zewnętrzny — widzi dane potrzebne do odprawy (kontener,
# spółka, statek, ETA, port, status/dane odprawy), ale NIE dane handlowe ani PII kierowcy.
_CUSTOMS_HIDDEN = {
    "supplier_id": None, "supplier_name": None, "supplier_raw": "",
    "order_id": None, "order_number": None, "order_numbers": "",
    "purchase_note": "", "delivery_note": "", "document_flow": "",
    "notes": "", "sent_number": "", "sent_status": "",
    "driver_id_no": "", "driver_name": "", "driver_phone": "",
    "truck_no": "", "trailer_no": "",
    "materials_list": "", "palletization_note": "",
    "customer_name": "", "customer_address": "", "customer_contact": "",
}

# Sprzedaż (tylko odczyt, 2026-09-27): dane operacyjne i handlowe tak, bez PII kierowcy.
# Kosztów ContainerOut nie ma — moduły z kwotami (pulpit, wyceny, faktury) są dla sprzedaży zamknięte.
_SALES_HIDDEN = {"driver_id_no": "", "driver_phone": "", "driver_name": "",
                 "truck_no": "", "trailer_no": ""}

# Spedycja wycenia i wiezie transport — odprawa to wyłącznie agencja celna (decyzja 2026-09-28;
# ta sama firma może mieć oba konta, ale role są rozdzielone): bez statusu, dat, notatek i agencji.
_FORWARDER_HIDDEN = {
    "customs_t1": False, "customs_status": CustomsStatus.BRAK, "customs_note": "",
    "customs_date": None, "customs_agency": "", "customs_agency_id": None,
    "customs_agency_name": None, "customs_agent_name": "", "customs_agent_phone": "",
    "customs_agent_email": "", "customs_assigned_at": None, "customs_case_status_id": None,
    "customs_case_status_name": None, "missing_documents": None,
}

_HIDDEN_BY_ROLE: dict[Role, Mapping[str, object]] = {
    Role.warehouse: _WAREHOUSE_HIDDEN, Role.customs: _CUSTOMS_HIDDEN,
    Role.forwarder: _FORWARDER_HIDDEN, Role.sales: _SALES_HIDDEN}


def hidden_fields(user: User | None) -> frozenset[str]:
    """Pola ContainerOut maskowane dla roli użytkownika (to_out, historia zmian).

    JEDNO źródło także dla wyszukiwania i filtrów: po polu, którego rola nie widzi, nie
    wolno jej szukać — inaczej wynik (jest/nie ma) zdradza wartość (wyrocznia istnienia PO,
    dostawcy, uwag…)."""
    return frozenset(_HIDDEN_BY_ROLE.get(user.role, ()) if user is not None else ())


def mask_row(row: dict, user: User | None) -> dict:
    """Maskuje słownik z polami kontenera (sygnały, listy pulpitu…) jak to_out — te same
    pola i puste wartości. Agregaty poza ContainerOut muszą przez to przejść, inaczej
    omijają maskowanie roli (dostawca u agencji celnej, 2026-10-05)."""
    for field, blank in (_HIDDEN_BY_ROLE.get(user.role, {}) if user is not None else {}).items():
        if field in row:
            row[field] = blank
    return row


def searchable(user: User | None, columns: dict) -> list:
    """Kolumny {pole ContainerOut: kolumna SQL} po których rola może szukać (bez ukrytych)."""
    hidden = hidden_fields(user)
    return [col for field, col in columns.items() if field not in hidden]


def fk_matches(db: Session, fk, ids):
    """`fk IN (ids)` do OR-a wyszukiwarki po polu tabeli powiązanej (PERF-007).

    Postgres: `fk = ANY(ARRAY(ids))` — podzapytanie liczone raz (InitPlan), warunek idzie
    po indeksie FK i składa się z GIN-ami pg_trgm kontenera w BitmapOr. LEFT JOIN z
    warunkiem na tabeli obcej albo `IN (podzapytanie)` w OR wymuszają Seq Scan kontenerów.
    SQLite (testy/dev): zwykłe IN."""
    if db.get_bind().dialect.name == "postgresql":
        return fk == any_(func.array(ids.scalar_subquery()))
    return fk.in_(ids)


def to_out(c: Container, user: User | None) -> ContainerOut:
    # user obowiązkowy: bez niego pola maskowane dla roli (odprawa, PII…) wyciekały (2026-10-05)
    out = ContainerOut.model_validate(c)
    out.company_name = c.company.name if c.company else None
    out.order_number = c.order.number if c.order else None
    # bez dopasowania w słowniku pokazujemy nazwę z pliku (UI rozpoznaje ją po supplier_id null)
    out.supplier_name = c.supplier.name if c.supplier else (c.supplier_raw or None)
    out.forwarder_name = c.forwarder.name if c.forwarder else None
    out.customs_agency_name = c.customs_agency_rel.name if c.customs_agency_rel else None
    out.customs_case_status_name = (
        c.customs_case_status_rel.name if c.customs_case_status_rel else None)
    out.warehouse_name = c.warehouse.name if c.warehouse else None
    out.port_name = c.port.name if c.port else None
    out.carrier_name = c.carrier.name if c.carrier else None
    out.eta_estimate = estimated_eta(c)
    if user is not None:
        for field, blank in _HIDDEN_BY_ROLE.get(user.role, {}).items():
            setattr(out, field, blank)
    return out


def _attach_status_ages(db: Session, items: list[ContainerOut]) -> list[ContainerOut]:
    """#27: dni od ostatniej zmiany statusu — JEDNO zapytanie grupowane dla całej listy."""
    ids = [it.id for it in items]
    if not ids:
        return items
    rows = db.execute(
        select(AuditLog.entity_id, func.max(AuditLog.created_at))
        .where(AuditLog.entity_type == "containers", AuditLog.field == "status",
               AuditLog.entity_id.in_(ids))
        .group_by(AuditLog.entity_id)).all()
    now = utcnow()
    ages = {eid: (now - ts).days for eid, ts in rows}
    for it in items:
        it.status_age_days = ages.get(it.id)
    return items


def _notify_new_delivery(db: Session, container: Container, user: User) -> None:
    """Q66: powiadom magazyn (np. DLT) o dostawie skierowanej do niego — wywoływane
    przy utworzeniu kontenera oraz przy (prze)przypisaniu magazynu."""
    if not container.warehouse_id:
        return
    notify(db, warehouse_users(db, container.company_id, container.warehouse_id), kind="order",
           title=f"Nowa dostawa: {container.container_no}",
           body=f"Zaplanowano dostawę kontenera {container.container_no}"
                + (f" (awizacja {container.notify_date})." if container.notify_date else "."),
           container_id=container.id, exclude_user_id=user.id)
    db.commit()


def get_container_checked(db: Session, container_id: int, user: User) -> Container:
    return get_scoped(db, Container, container_id, user, options=_LOAD)


def _check_company_fks(db: Session, company_id: int, supplier_id: int | None,
                       warehouse_id: int | None, order_id: int | None) -> None:
    """Walidacja, że wskazane rekordy należą do spółki kontenera (dostawca — do użycia w
    tej spółce: deps.supplier_clause_for_company) — bez tego można doczepić dostawcę/
    magazyn/zamówienie innej spółki i wyciekać jej nazwy (izolacja)."""
    if supplier_id is not None:
        company = db.get(Company, company_id)
        if company is None or db.scalar(select(Supplier.id).where(
                Supplier.id == supplier_id, supplier_clause_for_company(company))) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono dostawcy.")
    if warehouse_id is not None:
        w = db.get(Warehouse, warehouse_id)
        if not w or w.company_id != company_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono magazynu.")
    if order_id is not None:
        o = db.get(Order, order_id)
        if not o or o.company_id != company_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono zamówienia.")


def _resolve_order(db: Session, company_id: int, order_id: int | None,
                   order_number: str | None, supplier_id: int | None) -> int | None:
    if order_id is not None:
        order = db.get(Order, order_id)
        if not order or order.company_id != company_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono zamówienia.")
        return order_id
    if order_number:
        order = db.scalar(select(Order).where(
            Order.company_id == company_id, Order.number == order_number))
        if not order:
            order = Order(number=order_number, company_id=company_id, supplier_id=supplier_id)
            db.add(order)
            db.flush()
        return order.id
    return None
# statusy, w których kontener jest śledzony —
# wyjście poza nie kasuje zapamiętany błąd trackingu
_TRACKABLE_STATUSES = (ContainerStatus.ZAPOWIEDZIANY, ContainerStatus.W_PRODUKCJI,
                       ContainerStatus.TRANSPORT_WSTEPNY, ContainerStatus.W_TRANSPORCIE,
                       ContainerStatus.W_PORCIE)
# maszyna stanów statusu (D2): kolejność enuma = kolejność procesu. W przód dowolnie,
# wstecz o 1 krok z obowiązkową notatką, większe cofnięcie tylko admin (też z notatką)
STATUS_FLOW = tuple(ContainerStatus)


def check_not_modified(db: Session, container: Container,
                       expected: datetime.datetime | None) -> None:
    """Blokada optymistyczna (audyt DB-005): formularz odsyła pełny stan, więc zapis na starym
    `updated_at` nadpisałby cudzą zmianę. Brak `expected` = stary klient, bez kontroli.

    Sprawdzenie i zajęcie wiersza to JEDEN warunkowy UPDATE (nie odczyt + zapis): równoległy
    zapis na tym samym stanie czeka na blokadę wiersza do commitu pierwszego, po czym jego
    warunek już nie pasuje → 409 (sam odczyt `updated_at` przepuściłby oba)."""
    if expected is None:
        return
    if expected.tzinfo is not None:
        expected = expected.astimezone(datetime.UTC).replace(tzinfo=None)
    now = utcnow()
    res = cast(CursorResult, db.execute(
        update(Container).where(Container.id == container.id, Container.updated_at == expected)
        .values(updated_at=now).execution_options(synchronize_session=False)))
    if res.rowcount != 1:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ktoś zmienił ten kontener w międzyczasie — odśwież i wprowadź zmiany ponownie.")
    set_committed_value(container, "updated_at", now)   # bez ponownego UPDATE przy flushu


def check_status_transition(old: ContainerStatus, new: ContainerStatus,
                            user: User, note: str) -> None:
    back = STATUS_FLOW.index(old) - STATUS_FLOW.index(new)
    if back <= 0:
        return
    if back > 1 and user.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Cofnięcie statusu o więcej niż jeden krok może zrobić tylko admin.")
    if not note.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Cofnięcie statusu wymaga notatki z powodem.")


# kto zmienia status odprawy — także automaty (wgrany SAD-PZ/PW) sprawdzają tę samą listę
CUSTOMS_EDITORS = (Role.customs, Role.logistics, Role.admin)


def check_customs_status_change(old: CustomsStatus, new: CustomsStatus | None,
                                user: User, note: str | None) -> None:
    """Reguły statusu odprawy (decyzje właściciela 2026-09-28, audyt BIZ-001) — JEDNO miejsce dla
    wszystkich ścieżek zapisu: zmienia agencja celna, logistyka/admin awaryjnie, spedytor nie;
    cofnięcie z ODPRAWIONY/ROZLICZONY tylko logistyka/admin i zawsze z notatką „dlaczego”."""
    if new is None or new == old:
        return
    if user.role not in CUSTOMS_EDITORS:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Status odprawy zmienia agencja celna (awaryjnie logistyka).")
    if new == CustomsStatus.REWIZJA and not (note or "").strip():   # spec §2: „z datą i notatką”
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Rewizja wymaga notatki (powód / ustalenia kontroli).")
    if old in CUSTOMS_CLEARED and new not in CUSTOMS_CLEARED:
        if user.role not in (Role.logistics, Role.admin):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Cofnięcie odprawionego kontenera może zrobić tylko logistyka.")
        if not (note or "").strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Cofnięcie odprawy wymaga notatki z powodem.")


def transport_job_conflicts(db: Session, user: User,
                            date_from: datetime.date, date_to: datetime.date,
                            container_ids: list[int] | None = None) -> list[dict]:
    """Kolizje transportu: kontenery TEGO SAMEGO zlecenia transportowego (paczki)
    z dostawą tego samego dnia w RÓŻNYCH magazynach — jedno zapytanie.

    Uwaga: transport_id kontenera jest unikatowy w bazie, więc „ten sam transport"
    dla wielu kontenerów wyraża TransportJob (paczka RFQ), nie kolumna transport_id."""
    query = (select(TransportJobContainer.job_id, TransportJob.number, Container.id,
                    Container.notify_date, Container.warehouse_id, Warehouse.name)
             .join(Container, TransportJobContainer.container_id == Container.id)
             .join(TransportJob, TransportJobContainer.job_id == TransportJob.id)
             .join(Warehouse, Container.warehouse_id == Warehouse.id)
             .where(TransportJob.status != TransportJobStatus.ANULOWANE,
                    Container.status.not_in(Container.FINISHED),
                    Container.notify_date >= date_from,
                    Container.notify_date <= date_to))
    query = scope_containers(query, user)
    if container_ids is not None:
        # zawężenie do paczek, w których uczestniczą wskazane kontenery
        sub = select(TransportJobContainer.job_id).where(
            TransportJobContainer.container_id.in_(container_ids))
        query = query.where(TransportJobContainer.job_id.in_(sub))
    groups: dict[tuple[int, datetime.date], list] = {}
    for row in db.execute(query):
        groups.setdefault((row[0], row[3]), []).append(row)
    conflicts = []
    for (_job_id, day), rows in groups.items():
        wh_ids = {r[4] for r in rows}
        if len(wh_ids) < 2:
            continue
        names = sorted({r[5] for r in rows})
        for r in rows:
            conflicts.append({"container_id": r[2], "job_number": r[1],
                              "day": day.isoformat(), "warehouses": names})
    return conflicts


def day_limit(db: Session, warehouse: Warehouse | None, day: datetime.date) -> int | None:
    if warehouse is None:
        return None
    override = db.scalar(select(DailyLimit).where(
        DailyLimit.warehouse_id == warehouse.id, DailyLimit.day == day))
    return override.limit if override else warehouse.default_daily_limit


def daily_limits_map(db: Session, warehouse_ids: list[int], date_from: datetime.date,
                     date_to: datetime.date) -> dict[tuple[int, datetime.date], int]:
    """Nadpisania limitów dziennych dla wielu magazynów w oknie dat — JEDNYM zapytaniem
    (zamiast osobnego SELECT-a na każdą parę dzień×magazyn)."""
    if not warehouse_ids:
        return {}
    rows = db.execute(
        select(DailyLimit.warehouse_id, DailyLimit.day, DailyLimit.limit)
        .where(DailyLimit.warehouse_id.in_(warehouse_ids),
               DailyLimit.day >= date_from, DailyLimit.day <= date_to)).all()
    return {(wid, day): limit for wid, day, limit in rows}


def calendar_overrides_map(db: Session, warehouse_ids: list[int], date_from: datetime.date,
                           date_to: datetime.date) -> dict[tuple[int, datetime.date], bool]:
    """Wyjątki kalendarza (is_working) dla wielu magazynów w oknie dat — JEDNYM zapytaniem."""
    if not warehouse_ids:
        return {}
    rows = db.execute(
        select(CalendarDay.warehouse_id, CalendarDay.day, CalendarDay.is_working)
        .where(CalendarDay.warehouse_id.in_(warehouse_ids),
               CalendarDay.day >= date_from, CalendarDay.day <= date_to)).all()
    return {(wid, day): working for wid, day, working in rows}


def sync_status_from_customs(db: Session, container: Container, user: User) -> None:
    """Status kontenera wynika ze statusu odprawy (decyzja 2026-09-28) — tylko do przodu:
    odprawa w toku → ODPRAWA; odprawiony/rozliczony + data awizacji → AWIZOWANY."""
    from ..audit import record
    customs = CustomsStatus(container.customs_status)
    target = None
    if customs in CUSTOMS_IN_PROGRESS:
        target = ContainerStatus.ODPRAWA
    elif customs in CUSTOMS_CLEARED:
        target = ContainerStatus.AWIZOWANY if container.notify_date else ContainerStatus.ODPRAWA
    if target is None or STATUS_FLOW.index(target) <= STATUS_FLOW.index(container.status):
        return
    record(db, entity_type="containers", entity_id=container.id, field="status",
           old_value=container.status.value, new_value=target.value, user=user,
           note="automatycznie ze statusu odprawy")
    container.status = target

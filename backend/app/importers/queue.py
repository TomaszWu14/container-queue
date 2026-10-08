"""Import/sync arkusza kolejki (układ 2026 — kolejka Acme): parsowanie wierszy,
budowa pól kontenera i uzgodnienie three-way z DB (sync_baseline)."""
from ..models import today_pl
import datetime
import logging
import re

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import iso6346
from ..audit import record
from ..date_pl import date_pl
from ..deps import supplier_clause_for_company
from ..models import (
    AuditLog,
    Company,
    Container,
    ContainerStatus,
    CustomsAgency,
    CustomsStatus,
    Forwarder,
    PlanningStatus,
    Supplier,
    SupplierAlias,
    TransportType,
    Warehouse,
    customs_rank,
    normalize_alias,
    utcnow,
)
from ..planning import reset_plan
from ..routers.containers import next_transport_id
from .excel import _cap, _cell_getter, _date, _load_workbook, _map_headers, _text

logger = logging.getLogger(__name__)


# nagłówek Excela -> klucz pola (dopasowanie po fragmencie, wielkość liter bez znaczenia)
HEADER_MAP = [
    ("DOSTAWCA", "supplier"),
    ("STATEK", "vessel"),
    ("ETA", "eta"),
    ("KOLEJ", "transport"),
    ("NR KONTENERA", "container_no"),
    ("NUMER ZAM", "order_numbers"),
    ("DOSTAWA", "delivery_note"),
    ("MAGAZYN - ZAKUPY", "purchase_note"),
    ("MAGAZYN", "warehouse"),
    ("NUMER DOSTAWY", "incoming_delivery_no"),
    ("NUMER RF", "rf_number"),
    ("SPEDYTOR", "forwarder"),
    ("PRZEP", "document_flow"),
    ("AGENCJA", "customs_agency"),
    ("STATUS ODPRAWY", "customs"),
    ("DATA ROZ", "notify_date"),
    ("SENT WYMAGANY", "sent_required"),
    ("NUMER SENT", "sent_number"),
    ("STATUS SENT", "sent_status"),
]


def _pick_sheet(workbook, company, sheet_name: str | None = None):
    """Arkusz pasujący do spółki (tytuł zawiera kod, np. „Borealis" dla BOREALIS) — pozwala
    trzymać moduły w jednym pliku, po kilka zakładek. Fallback: aktywny, potem pierwszy.

    `sheet_name` (SYNC_SHEET agenta, np. „2026") ma pierwszeństwo przed heurystyką:
    agent zapisuje zwrotnie do tej zakładki, więc odczyt musi czytać dokładnie tę samą —
    inaczej zapis i odczyt trafiają w różne arkusze. Nieznana nazwa → heurystyka."""
    if sheet_name and sheet_name in workbook.sheetnames:
        return workbook[sheet_name]
    code = (getattr(company, "code", "") or "").upper()
    if code:
        for ws in workbook.worksheets:
            if code in (ws.title or "").upper():
                return ws
    return workbook.active or workbook.worksheets[0]


def _parse_rows(content: bytes, company=None, sheet_name: str | None = None) -> list[dict]:
    sheet = _pick_sheet(_load_workbook(content), company, sheet_name)
    rows = sheet.iter_rows(values_only=True)
    columns: dict[str, int] = {}
    parsed: list[dict] = []
    for row in rows:
        if not columns:
            columns = _map_headers(row, HEADER_MAP)
            if "container_no" in columns:
                continue
            columns = {}
            continue
        get = _cell_getter(row, columns)
        raw_no = _text(get("container_no"))
        if not raw_no:
            continue  # wiersz-separator daty / pusty
        record_row = {key: get(key) for _, key in HEADER_MAP}
        record_row["container_no"] = raw_no
        parsed.append(record_row)
    if not columns:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie znaleziono wiersza nagłówków (kolumna „NR KONTENERA”).")
    return parsed


def _get_or_create(db: Session, model, defaults: dict | None = None, **filters):
    obj = db.scalar(select(model).filter_by(**filters))
    if obj:
        return obj
    obj = model(**filters, **(defaults or {}))
    db.add(obj)
    db.flush()
    return obj


def _match_customs_agency(db: Session, name: str) -> CustomsAgency | None:
    """Dopasowuje nazwę agencji z Excela do rejestru (bez rozróżniania wielkości liter).
    Nie tworzy nowych agencji — rejestr prowadzi admin; brak dopasowania = tylko tekst."""
    if not name:
        return None
    return db.scalar(select(CustomsAgency).where(
        CustomsAgency.is_active, func.lower(CustomsAgency.name) == name.lower()))


def _classify_transport(text: str) -> tuple[TransportType | None, str]:
    stripped = text.strip().lower()
    words = set(re.findall(r"\w+", stripped))
    if "morsk" in stripped or "statek" in stripped or "sea" in words:
        return TransportType.morski, "" if stripped in ("morski", "morze") else text
    if "lotnicz" in stripped or "samolot" in stripped or "air" in words:
        return TransportType.lotniczy, "" if stripped == "lotniczy" else text
    if "kolej" in stripped:
        return TransportType.kolej, "" if stripped == "kolej" else text
    if any(k in stripped for k in ("koł", "kola", "drogow", "truck")):
        # porównanie bez diakrytyków, by „kola"/„koła" nie zostawiały śmieciowego detalu
        return TransportType.kola, "" if stripped in ("koła", "kola") else text
    return (None, text) if text else (None, "")


def _parse_forwarder_name(raw_text: str) -> str:
    """Nazwa spedytora z pierwszej linii komórki (pusta komórka → '')."""
    lines = raw_text.splitlines()
    return lines[0].split(" - ")[0].strip() if lines else ""


def _map_warehouse(raw: str) -> tuple[str | None, str]:
    """Zwraca (nazwa magazynu ACME/DLT/oryginał, dopisek do uwag)."""
    cleaned = raw.strip()
    upper = cleaned.upper()
    if upper.startswith("ACME"):
        extra = cleaned[5:].strip(" -!:") if len(cleaned) > 5 else ""
        return "ACME", extra
    if "DLT" in upper.split() or upper == "DLT" or upper.startswith("DLT"):
        return "DLT", ""
    return (None, cleaned) if cleaned else (None, "")


def _derive_status(notify_date, customs: CustomsStatus, eta) -> ContainerStatus:
    today = today_pl()
    if notify_date and customs == CustomsStatus.ODPRAWIONY:
        return ContainerStatus.AWIZOWANY
    if eta and eta <= today:
        return ContainerStatus.W_PORCIE
    if eta:
        return ContainerStatus.W_TRANSPORCIE
    return ContainerStatus.ZAPOWIEDZIANY


_ORDER = list(ContainerStatus)


def _synced_status(current: ContainerStatus, derived: ContainerStatus) -> ContainerStatus:
    """Status z Excela dla istniejącego kontenera: TYLKO w przód — synchronizacja nigdy nie cofa
    statusu z aplikacji, także tego, który arkusz umie wyliczyć (decyzja 2026-09-28: praca
    dwutorowa, nieaktualny Excel nie może psuć danych w apce)."""
    return derived if _ORDER.index(derived) > _ORDER.index(current) else current


def _synced_customs(current: CustomsStatus | None, derived: CustomsStatus) -> CustomsStatus:
    """Status odprawy z Excela — jak status kontenera: TYLKO w przód. Arkusz zna tylko
    BRAK/ZLECONA/ODPRAWIONY, więc nie może cofnąć np. ROZLICZONY/REWIZJA z apki."""
    if current is None or customs_rank(derived) > customs_rank(current):
        return derived
    return current


def resolve_supplier_id(db: Session, company_id: int, name: str) -> int | None:
    """Nazwa z pliku → dostawca do użycia w spółce (kartoteka dla spółek z materiałami
    Acme + własni nadawcy): dokładna nazwa (bez wielkości liter), potem alias spółki. Import NIE
    tworzy dostawców (kartoteka przychodzi z SAP, nadawców prowadzi się ręcznie)."""
    if not name:
        return None
    company = db.get(Company, company_id)
    sid = db.scalar(select(Supplier.id).where(
        supplier_clause_for_company(company), func.lower(Supplier.name) == name.lower())
        .order_by(Supplier.id).limit(1))
    return sid or db.scalar(select(SupplierAlias.supplier_id).where(
        SupplierAlias.company_id == company_id,
        SupplierAlias.alias_norm == normalize_alias(name)))


def build_container_fields(db: Session, company, raw: dict) -> dict:
    """Buduje kwargs kolumn Container z surowego wiersza Excela (bez identity:
    company_id/container_no/transport_id). Wspólne dla importu (insert) i sync (update)."""
    transport_type, transport_details = _classify_transport(_text(raw["transport"]))
    warehouse_name, warehouse_extra = _map_warehouse(_text(raw["warehouse"]))
    warehouse = _get_or_create(db, Warehouse, {"country": "PL"},
                               company_id=company.id, name=warehouse_name) if warehouse_name else None
    supplier_raw = _cap(_text(raw["supplier"]), 160)
    forwarder_raw = _text(raw["forwarder"])
    forwarder_name = _parse_forwarder_name(forwarder_raw)
    forwarder = _get_or_create(db, Forwarder, {}, name=forwarder_name) if forwarder_name else None
    forwarder_extra = forwarder_raw if forwarder_raw != forwarder_name else ""
    customs_raw = _text(raw["customs"]).lower()
    customs = CustomsStatus.ODPRAWIONY if "odprawiony" in customs_raw \
        else (CustomsStatus.ZLECONA if customs_raw else CustomsStatus.BRAK)
    agency_name = _cap(_text(raw["customs_agency"]), 160)
    agency = _match_customs_agency(db, agency_name)
    sent_raw = _text(raw["sent_required"]).upper()
    notify_date = _date(raw["notify_date"])
    eta = _date(raw["eta"])
    notes = "\n".join(x for x in (warehouse_extra, forwarder_extra) if x)
    return {
        "vessel": _cap(_text(raw["vessel"]), 160),
        "eta": eta, "notify_date": notify_date,
        "transport_type": transport_type,
        "transport_details": _cap(transport_details, 200),
        "supplier_id": resolve_supplier_id(db, company.id, supplier_raw),
        "supplier_raw": supplier_raw,
        "forwarder_id": forwarder.id if forwarder else None,
        "warehouse_id": warehouse.id if warehouse else None,
        "order_numbers": _text(raw["order_numbers"]),
        "delivery_note": _text(raw["delivery_note"]),
        "purchase_note": _text(raw["purchase_note"]),
        "document_flow": _text(raw["document_flow"]),
        "incoming_delivery_no": _cap(_text(raw["incoming_delivery_no"]), 80),
        "rf_number": _cap(_text(raw["rf_number"]), 80),
        "customs_status": customs,
        "customs_agency": agency_name,
        "customs_agency_id": agency.id if agency else None,
        "customs_assigned_at": utcnow() if agency else None,
        "sent_required": True if sent_raw == "TAK" else (False if sent_raw == "NIE" else None),
        "sent_number": _text(raw["sent_number"]),
        "sent_status": _cap(_text(raw["sent_status"]), 120),
        "status": _derive_status(notify_date, customs, eta),
        "notes": notes,
    }


# pola nadpisywane z Excela na istniejących kontenerach. customs_assigned_at
# celowo wykluczone: to świeży timestamp z każdego build → floodowałby audyt.
SYNCED_FIELDS = (
    "vessel", "eta", "notify_date", "transport_type", "transport_details",
    "supplier_id", "supplier_raw", "forwarder_id", "warehouse_id", "order_numbers",
    "delivery_note",
    "purchase_note", "document_flow", "incoming_delivery_no", "rf_number",
    "customs_status", "customs_agency", "customs_agency_id", "sent_required",
    "sent_number", "sent_status", "status", "notes",
)


def _audit_val(v):
    """Serializacja wartości do AuditLog (enum→value, reszta→str, None→None)."""
    if v is None:
        return None
    return v.value if hasattr(v, "value") else str(v)


def ser(v) -> str | None:
    """Serializacja pola do porównania i baseline: enum->value, date->iso, else str."""
    if v is None:
        return None
    if hasattr(v, "value"):
        return v.value
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    return str(v)


def container_baseline(container) -> dict:
    """Aktualny stan pól SYNCED_FIELDS kontenera po ser() — kandydat na nowy baseline."""
    return {f: ser(getattr(container, f)) for f in SYNCED_FIELDS}


def app_field_time(db: Session, container, field: str) -> datetime.datetime:
    """Czas ostatniej zmiany pola w apce (z AuditLog); fallback = updated_at kontenera."""
    t = db.scalar(select(func.max(AuditLog.created_at)).where(
        AuditLog.entity_type == "containers", AuditLog.entity_id == container.id,
        AuditLog.field == field))
    return t or container.updated_at


# pola, w których edycja w apce ma pierwszeństwo przy konflikcie z Excelem (LWW po
# file_mtime). Pola SYNCED_FIELDS spoza tej listy (status, notes, relacyjne *_id/agency)
# są Excel->apka only (Excel autorytatywny).
WRITABLE_FIELDS = (
    "eta", "notify_date", "vessel", "order_numbers", "delivery_note", "purchase_note",
    "document_flow", "incoming_delivery_no", "rf_number", "sent_required", "sent_number",
    "sent_status",
)


def _reset_plan_if_notify_date_changed(db: Session, container, changed_fields, actor) -> None:
    """Excel nadpisał notify_date -> jeśli plan był uzgodniony/wysłany, reguła zamrożenia
    (patrz app/planning.py) wymaga resetu do PROPOZYCJA; inaczej rekord udawałby dalej
    uzgodniony pod datą, której nikt nie potwierdził."""
    if any(f == "notify_date" for f, _, _ in changed_fields) \
            and container.planning_status != PlanningStatus.PROPOZYCJA:
        reset_plan(db, container, actor, note="sync z Excela: zmiana daty po potwierdzeniu spedycji")


REPEAT_PREFIX = "powtórny numer — poprzednia dostawa: "


def containers_by_number(db: Session, company_id: int) -> tuple[dict, dict]:
    """N-20 (DATA-001): import i sync dopasowują numer TYLKO wśród niezrealizowanych kontenerów
    spółki. Zwraca (aktywne: numer→Container, zrealizowane: numer→notatka „powtórny numer…”
    z datą awizacji ostatniej zrealizowanej dostawy) — numer tylko z archiwum = nowy kontener."""
    active, repeats = {}, {}
    for c in db.scalars(select(Container).where(Container.company_id == company_id)
                        .order_by(Container.id)):
        if c.status == ContainerStatus.ZREALIZOWANY:
            repeats[c.container_no] = REPEAT_PREFIX + (date_pl(c.notify_date) or "brak daty")
        else:
            active[c.container_no] = c
    return active, repeats


def _same_finished_delivery(db: Session, company_id: int, number: str, fields: dict) -> bool:
    """Wiersz to wciąż TA SAMA, już zrealizowana dostawa (zostawiona w Excelu po zamknięciu):
    zrealizowany kontener z tym numerem ma tę samą datę awizacji albo ETA. Wtedy sync pomija
    wiersz — inaczej każdy sync tworzyłby nowy „powtórny numer” (N-20 dotyczy nowej dostawy)."""
    same = [col == fields[col.key] for col in (Container.notify_date, Container.eta)
            if fields[col.key] is not None]
    return bool(same) and db.scalar(select(Container.id).where(
        Container.company_id == company_id, Container.container_no == number,
        Container.status == ContainerStatus.ZREALIZOWANY, or_(*same)).limit(1)) is not None


def with_repeat_note(note: str, notes: str) -> str:
    return "\n".join(x for x in (note, notes) if x)


def _process_row(db: Session, company, raw: dict, existing: dict, actor,
                 file_mtime: datetime.datetime | None = None,
                 repeats: dict | None = None) -> dict | None:
    number = iso6346.normalize(_text(raw["container_no"]))
    ok, _reason = iso6346.validate(number)
    if not ok:
        logger.warning("sync: pominięto niepoprawny numer kontenera %s", number)
        return None
    fields = build_container_fields(db, company, raw)
    container = existing.get(number)
    if container is None:                                   # nowy kontener
        if number in (repeats or {}) and _same_finished_delivery(db, company.id, number, fields):
            return None                                     # zrealizowana dostawa wciąż w arkuszu
        fields["notes"] = with_repeat_note((repeats or {}).get(number, ""), fields["notes"])
        container = Container(company_id=company.id, container_no=number, **fields)
        year = (fields["notify_date"] or today_pl()).year
        container.transport_id = next_transport_id(db, company, year)
        db.add(container); db.flush(); existing[number] = container
        container.sync_baseline = container_baseline(container)   # B = stan początkowy
        record(db, entity_type="containers", entity_id=container.id, field="status",
               old_value=None, new_value=container.status.value, user=actor,
               note="sync z Excela (nowy)")
        return {"container": container, "changes": [("__new__", None, None)]}
    fields["status"] = _synced_status(container.status, fields["status"])
    fields["customs_status"] = _synced_customs(container.customs_status, fields["customs_status"])
    # notatka „powtórny numer…” nie pochodzi z Excela — sync (Excel autorytatywny dla notes) jej nie kasuje
    first = (container.notes or "").split("\n", 1)[0]
    if first.startswith(REPEAT_PREFIX):
        fields["notes"] = with_repeat_note(first, fields["notes"])

    baseline = container.sync_baseline
    # nazwa z pliku bez mapowania = „brak zdania" o dostawcy, dopóki nazwa w pliku się nie
    # zmieni — nie kasuj dostawcy przypisanego w apce (ręcznie / po scaleniu duplikatów)
    if (baseline is not None and fields["supplier_id"] is None and fields["supplier_raw"]
            and baseline.get("supplier_raw", container.supplier_raw) == fields["supplier_raw"]):
        fields["supplier_id"] = container.supplier_id
    # BOOTSTRAP: brak baseline -> Excel wygrywa (jak Faza A), potem B <- stan
    if baseline is None:
        changes = []
        for f in SYNCED_FIELDS:
            if ser(getattr(container, f)) != ser(fields[f]):
                setattr(container, f, fields[f]); changes.append((f, None, ser(fields[f])))
        container.sync_baseline = container_baseline(container)
        if changes and all(f == "status" for f, _, _ in changes):
            return None
        for f, _o, nv in changes:
            record(db, entity_type="containers", entity_id=container.id, field=f,
                   old_value=None, new_value=nv, user=actor, note="sync z Excela")
        _reset_plan_if_notify_date_changed(db, container, changes, actor)
        return {"container": container, "changes": changes} if changes else None

    # THREE-WAY per pole
    new_baseline = dict(baseline)
    excel_changes = []            # pola gdzie Excel wygrał i ustawiamy A<-E (audyt/notify)
    for f in SYNCED_FIELDS:
        e = ser(fields[f]); a = ser(getattr(container, f)); b = baseline.get(f)
        if e == b and a == b:
            continue                                        # nic
        writable = f in WRITABLE_FIELDS
        if e != b and a == b:                               # tylko Excel -> Excel wins
            setattr(container, f, fields[f]); new_baseline[f] = e
            excel_changes.append((f, a, e)); continue
        if a != b and e == b:                               # tylko apka
            # zapisywalne: pending (B stare) -> zapis w Excelu (B3). Niezapisywalne: zostaw
            # wartość z apki i B = E — B<-A sprawiało, że kolejny sync z tym samym Excelem
            # widział „zmianę w Excelu” i cofał apkę (np. odprawę, magazyn, uwagi).
            continue
        if e == a:                                          # oba zgodne
            new_baseline[f] = e; continue
        # konflikt: e!=b, a!=b, e!=a
        if not writable:                                    # niezapisywalne: Excel autorytatywny
            setattr(container, f, fields[f]); new_baseline[f] = e
            excel_changes.append((f, a, e)); continue
        app_wins = file_mtime is not None and app_field_time(db, container, f) > file_mtime
        if app_wins:
            continue                                        # apka -> pending, B stare
        setattr(container, f, fields[f]); new_baseline[f] = e
        excel_changes.append((f, a, e))
    container.sync_baseline = new_baseline
    if not excel_changes:
        return None
    if all(f == "status" for f, _, _ in excel_changes):     # tylko czasowy status -> cicho
        return None
    if any(f == "customs_agency_id" for f, _, _ in excel_changes):
        container.customs_assigned_at = fields["customs_assigned_at"]
    for f, ov, nv in excel_changes:
        record(db, entity_type="containers", entity_id=container.id, field=f,
               old_value=ov, new_value=nv, user=actor, note="sync z Excela")
    _reset_plan_if_notify_date_changed(db, container, excel_changes, actor)
    return {"container": container, "changes": excel_changes}


def reconcile_queue(db: Session, company, parsed: list[dict], actor,
                    file_mtime: datetime.datetime | None = None) -> list[dict]:
    """Uzgadnia snapshot arkusza z DB per numer kontenera three-way na sync_baseline.
    Każdy wiersz w savepoincie — jeden wadliwy nie wywala całego syncu."""
    existing, repeats = containers_by_number(db, company.id)
    results: list[dict] = []
    for raw in parsed:
        try:
            with db.begin_nested():
                row_result = _process_row(db, company, raw, existing, actor, file_mtime, repeats)
        except Exception as exc:  # noqa: BLE001 — wadliwy wiersz nie przerywa syncu
            logger.warning("sync: pominięto %s: %s", _text(raw.get("container_no")), exc)
            continue
        if row_result:
            results.append(row_result)
    return results


def sync_queue_bytes(db: Session, company, content: bytes, actor, *, sheet: str | None = None,
                     date_from: datetime.date | None = None,
                     file_mtime: datetime.datetime | None = None, dry_run: bool = True) -> dict:
    """Wspólny rdzeń syncu kolejki: POST /import/queue-sync i job SharePointa.
    Wiersze z notify_date < date_from pomijane (bez notify_date zawsze przechodzą).
    dry_run liczy zmiany w savepoincie i cofa; inaczej zapis + powiadomienia + commit."""
    from .queue_notify import notify_sync_summary   # leniwie: notifications importuje routery

    parsed = _parse_rows(content, company, sheet)
    skipped_old = 0
    if date_from:
        kept = []
        for row in parsed:
            nd = _date(row["notify_date"])
            if nd and nd < date_from:
                skipped_old += 1
                continue
            kept.append(row)
        parsed = kept
    if dry_run:
        # reconcile mutuje obiekty; savepoint obejmuje wewnętrzne begin_nested reconcile
        sp = db.begin_nested()
        results = reconcile_queue(db, company, parsed, actor, file_mtime=file_mtime)
        changed = [r["container"].container_no for r in results]
        sp.rollback()
        db.rollback()
        return {"dry_run": True, "containers": len(parsed), "changed": len(changed),
                "changed_numbers": changed[:300], "skipped_old": skipped_old}

    results = reconcile_queue(db, company, parsed, actor, file_mtime=file_mtime)
    notified = notify_sync_summary(db, company, results)
    db.commit()
    return {"dry_run": False, "containers": len(parsed), "changed": len(results),
            "notified": notified, "skipped_old": skipped_old}

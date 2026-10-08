"""Import kolejki z Excela (układ arkusza 2026 — kolejka Acme, wspólny dla obu modułów).

Dopasowanie kolumn po nagłówkach (odporne na zmiany kolejności), wiersze-separatory
dat pomijane, tylko NOWE kontenery (numery niezrealizowanych kontenerów są pomijane), wartości
wielokrotne w komórkach zachowywane 1:1 jako tekst.

Router jest cienki: parsowanie i uzgadnianie w app/importers/*, endpointy master data
w routers/imports_master.py (sub-router). Stare nazwy re-eksportowane poniżej.
"""
import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import iso6346
from ..audit import record
from ..config import settings as app_config
from ..database import get_db
from ..deps import Editors as editors
from ..deps import get_company_by_code
from ..importers.excel import (  # noqa: F401 — re-eksport (scripts/import_lfa1, gałęzie)
    _cap,
    _cell_getter,
    _date,
    _load_workbook,
    _map_headers,
    _num,
    _open_first_sheet,
    _text,
)
from ..importers.master_data import (  # noqa: F401 — re-eksport publicznych ścieżek
    CPORT_HEADERS,
    DLT_HEADERS,
    MARM_HEADERS,
    MASTER_TYPES,
    _parse_cport_rows,
    _parse_cport_text,
    _parse_dlt_stock_rows,
    _parse_marm_rows,
    detect_master_type,
)
from ..importers.purchasing import (  # noqa: F401 — re-eksport publicznych ścieżek
    EKKO_DATES,
    EKKO_FLAGS,
    EKKO_HEADERS,
    ETD_HEADERS,
    SAP_HEADERS,
    _link_container_id,
    _order_tokens,
    _parse_ekko_rows,
    _parse_etd_rows,
    _parse_ref_rows,
)
from ..importers.queue import (  # noqa: F401 — re-eksport publicznych ścieżek
    HEADER_MAP,
    SYNCED_FIELDS,
    WRITABLE_FIELDS,
    _audit_val,
    _classify_transport,
    _derive_status,
    _get_or_create,
    _map_warehouse,
    _match_customs_agency,
    _parse_forwarder_name,
    _parse_rows,
    _pick_sheet,
    _process_row,
    _reset_plan_if_notify_date_changed,
    app_field_time,
    build_container_fields,
    container_baseline,
    containers_by_number,
    reconcile_queue,
    ser,
    sync_queue_bytes,
    with_repeat_note,
)
from ..models import Container, OrderItem, PurchaseOrder, User, today_pl
from ..app_settings import get_setting, set_setting
from .containers import next_transport_id
from .forwarding import read_upload_capped
from .imports_master import (  # noqa: F401 — re-eksport endpointów
    import_container_ports,
    import_dlt_stock,
    import_master_data,
    import_material_units,
    import_sap_orders,
    import_suppliers_lfa1,
)
from .imports_master import router as _master_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/containers")
def import_containers(
    file: UploadFile,
    company_code: str = Query(...),
    dry_run: bool = Query(default=True),
    db: Session = Depends(get_db),
    user: User = editors,
):
    company = get_company_by_code(db, user, company_code)

    parsed = _parse_rows(read_upload_capped(file, app_config.max_upload_mb, "Plik importu"),
                         company)
    # „już w systemie" liczone w obrębie tej spółki (separacja spółek) i tylko wśród
    # niezrealizowanych — numer z archiwum = powtórny przyjazd, nowy kontener (N-20)
    existing, repeats = containers_by_number(db, company.id)

    preview, seen = [], set()
    for raw in parsed:
        number = iso6346.normalize(_text(raw["container_no"]))
        ok, reason = iso6346.validate(number)
        if not ok:
            entry_status, note = "invalid", reason
        elif number in existing:
            entry_status, note = "exists", "kontener już w systemie — pomijany"
        elif number in seen:
            entry_status, note = "duplicate", "zduplikowany w pliku — wczytany raz"
        else:
            entry_status, note = "new", repeats.get(number, "")
            seen.add(number)
        warehouse_name, warehouse_extra = _map_warehouse(_text(raw["warehouse"]))
        eta, notify = _date(raw["eta"]), _date(raw["notify_date"])
        transport_type = _classify_transport(_text(raw["transport"]))[0]
        preview.append({
            "container_no": number or _text(raw["container_no"]),
            "status": entry_status, "note": note,
            "supplier": _text(raw["supplier"]), "vessel": _text(raw["vessel"]),
            "eta": eta.isoformat() if eta else "",
            "notify_date": notify.isoformat() if notify else "",
            "warehouse": warehouse_name or _text(raw["warehouse"]),
            "forwarder": _parse_forwarder_name(_text(raw["forwarder"])),
            "transport": transport_type.value if transport_type else "",
            "_warehouse_extra": warehouse_extra,
        })

    counts = {
        "total": len(preview),
        "new": sum(1 for p in preview if p["status"] == "new"),
        "exists": sum(1 for p in preview if p["status"] == "exists"),
        "invalid": sum(1 for p in preview if p["status"] == "invalid"),
        "duplicate": sum(1 for p in preview if p["status"] == "duplicate"),
    }
    if dry_run:
        return {"dry_run": True, "counts": counts,
                # pełna lista błędnych numerów (do poprawy w Excelu) — niecapowana
                "invalid_numbers": [p["container_no"] for p in preview if p["status"] == "invalid"],
                "rows": [{k: v for k, v in p.items() if not k.startswith("_")}
                         for p in preview[:300]]}

    # --- zapis nowych kontenerów ---
    imported = 0
    failed = 0
    parsed_by_no = {}
    for raw in parsed:
        number = iso6346.normalize(_text(raw["container_no"]))
        if number not in parsed_by_no:
            parsed_by_no[number] = raw
    for entry in preview:
        if entry["status"] != "new":
            continue
        raw = parsed_by_no[entry["container_no"]]
        # każdy wiersz w osobnym savepoincie — jeden wadliwy (np. za długa komórka)
        # nie wywala już całego importu; jest pomijany i policzony jako błędny.
        try:
            with db.begin_nested():
                fields = build_container_fields(db, company, raw)
                fields["notes"] = with_repeat_note(entry["note"], fields["notes"])
                container = Container(company_id=company.id,
                                      container_no=entry["container_no"], **fields)
                year = (fields["notify_date"] or today_pl()).year
                container.transport_id = next_transport_id(db, company, year)
                db.add(container)
                db.flush()
                record(db, entity_type="containers", entity_id=container.id, field="status",
                       old_value=None, new_value=container.status.value, user=user,
                       note=f"import z Excela ({file.filename})")
            imported += 1
        except Exception as exc:  # noqa: BLE001 — pojedynczy wiersz nie może przerwać importu
            failed += 1
            logger.warning("Import: pominięto kontener %s: %s", entry["container_no"], exc)
    try:
        db.commit()
    except IntegrityError:
        # równoległy import zajął ten sam numer transportu — czytelne 409 do ponowienia
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Konflikt numeracji transportu przy imporcie — spróbuj ponownie.") from None
    return {"dry_run": False, "counts": counts, "imported": imported, "failed": failed}


# --- import zamówień zakupowych (arkusz ETD, wczesny etap przed kontenerem) ---

@router.post("/purchase-orders")
def import_purchase_orders(
    file: UploadFile,
    company_code: str = Query(...),
    dry_run: bool = Query(default=True),
    db: Session = Depends(get_db),
    user: User = editors,
):
    """Import zamówień zakupowych z arkusza ETD. Upsert po (spółka, order_no) —
    ponowny import aktualizuje istniejące. Auto-link do kontenera po order_no."""
    company = get_company_by_code(db, user, company_code)
    parsed = _parse_etd_rows(
        read_upload_capped(file, app_config.max_upload_mb, "Plik ETD"))

    existing = {p.order_no: p for p in db.scalars(
        select(PurchaseOrder).where(PurchaseOrder.company_id == company.id))}
    containers = [(cid, no) for cid, no in db.execute(select(
        Container.id, Container.order_numbers).where(Container.company_id == company.id))]

    seen: set[str] = set()
    new_n = updated_n = linked_n = dup_n = 0
    for raw in parsed:
        no = raw["order_no"]
        if no in seen:
            dup_n += 1
            continue
        seen.add(no)
        container_id = _link_container_id(no, containers)
        if container_id:
            linked_n += 1
        if no in existing:
            updated_n += 1
        else:
            new_n += 1

    counts = {"total": len(parsed), "new": new_n, "updated": updated_n,
              "linked": linked_n, "duplicate": dup_n}
    if dry_run:
        return {"dry_run": True, "counts": counts, "rows": parsed[:300]}

    seen.clear()
    for raw in parsed:
        no = raw["order_no"]
        if no in seen:
            continue
        seen.add(no)
        container_id = _link_container_id(no, containers)
        po = existing.get(no)
        if po is None:
            po = PurchaseOrder(company_id=company.id, order_no=no)
            db.add(po)
            existing[no] = po
        for key, value in raw.items():
            if key != "order_no":
                setattr(po, key, value)
        po.container_id = container_id
    record(db, entity_type="purchase_orders", entity_id=company.id, field="import",
           old_value=None, new_value=f"{new_n} nowych / {updated_n} zaktualizowanych",
           user=user, note=f"import ETD ({file.filename})")
    db.commit()
    return {"dry_run": False, "counts": counts}


# --- import pozycji zamówień (REF) z eksportu SAP (parser: importers/purchasing.py) ---

@router.post("/order-items")
def import_order_items(
    file: UploadFile,
    company_code: str = Query(...),
    dry_run: bool = Query(default=True),
    db: Session = Depends(get_db),
    user: User = editors,
):
    """Import zawartości kontenerów (pozycje REF) z eksportu SAP.

    Pozycje przypisywane po numerze zamówienia; ponowny import zamówienia
    nadpisuje jego pozycje (zawsze aktualny stan z SAP). Wiersz bez numeru pozycji albo
    z nieliczbową ilością trafia do raportu błędów, a jego zamówienie zostaje nietknięte —
    częściowe nadpisanie skasowałoby pozycję, do której może być przypięte przyjęcie.
    """
    company = get_company_by_code(db, user, company_code)
    parsed, errors, duplicates = _parse_ref_rows(
        read_upload_capped(file, app_config.max_upload_mb, "Plik importu"))
    skipped = {e["order_number"] for e in errors}
    parsed = [p for p in parsed if p["order_number"] not in skipped]

    orders = sorted({p["order_number"] for p in parsed})
    tokens: set[str] = set()   # całe numery z kontenerów — nie podciąg („4500024” ≠ „4500624622”)
    for (text_,) in db.execute(
            select(Container.order_numbers).where(Container.company_id == company.id)):
        tokens |= _order_tokens(text_ or "")
    counts = {"rows": len(parsed), "orders": len(orders),
              "orders_linked": sum(1 for o in orders if _order_tokens(o) & tokens),
              "invalid": len(errors), "orders_skipped": len(skipped), "duplicate": duplicates}
    if dry_run:
        return {"dry_run": True, "counts": counts, "orders": orders[:100],
                "rows": parsed[:200], "errors": errors[:200]}

    for order_number in orders:  # nadpisanie pozycji importowanych zamówień
        db.query(OrderItem).filter(OrderItem.company_id == company.id,
                                   OrderItem.order_number == order_number).delete()
    for entry in parsed:
        db.add(OrderItem(company_id=company.id, **entry))
    record(db, entity_type="order_items", entity_id=company.id, field="import",
           old_value=None, new_value=f"{len(parsed)} pozycji / {len(orders)} zamówień",
           user=user, note=f"import REF z SAP ({file.filename})")
    db.commit()
    return {"dry_run": False, "counts": counts, "imported": len(parsed),
            "errors": errors[:200]}


@router.get("/queue-sync-date-from")
def queue_sync_date_from(
    company_code: str = Query(...),
    db: Session = Depends(get_db),
    user: User = editors,
):
    """Ostatnio użyta data „importuj od" dla spółki — do prefillu pola w modalu."""
    company = get_company_by_code(db, user, company_code)  # izolacja per-firma jak w queue_sync
    value = get_setting(db, f"queue_sync_date_from:{company.code}")
    return {"date_from": value or None}


@router.post("/sharepoint-sync")
def sharepoint_sync_now(db: Session = Depends(get_db), user: User = editors):
    """Ręczna synchronizacja kolejki z arkusza SharePoint (okres dwutorowej pracy Excel ↔ aplikacja)."""
    from .. import sharepoint
    if not sharepoint.is_configured():
        raise HTTPException(status.HTTP_409_CONFLICT, "SharePoint nie jest skonfigurowany.")
    result = sharepoint.sharepoint_queue_sync(db)   # „ok” / „unchanged” / „error” (szczegóły w panelu integracji)
    record(db, entity_type="sharepoint_sync", entity_id=0, field="import", old_value=None,
           new_value=result, user=user, note="ręczna synchronizacja kolejki z SharePoint")
    db.commit()
    if result == "error":
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Synchronizacja nieudana — szczegóły w panelu integracji.")
    return {"status": result}


@router.post("/queue-sync")
def queue_sync(
    file: UploadFile,
    company_code: str = Query(...),
    file_mtime: str | None = Query(default=None),
    sheet: str | None = Query(default=None),
    dry_run: bool = Query(default=True),
    date_from: datetime.date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = editors,
):
    """Ręczny upload arkusza kolejki (dawniej n8n z SharePointa) → uzgodnienie
    three-way: aktualizuje istniejące kontenery i dodaje nowe. Konflikt Excel vs
    apka rozstrzygany po czasie (LWW, `file_mtime`); per zmieniony kontener audyt +
    powiadomienie. dry_run=true (domyślnie) liczy zmiany bez zapisu.
    `date_from` filtruje wiersze po dacie rozładunku (notify_date) — arkusz
    SharePointa stale rośnie i user chce importować tylko świeższy fragment.
    Wiersze bez notify_date zawsze przechodzą (nowe kontenery nie mogą zniknąć)."""
    company = get_company_by_code(db, user, company_code)
    content = read_upload_capped(file, app_config.max_upload_mb, "Plik kolejki")
    mtime = None
    if file_mtime:
        try:
            mtime = datetime.datetime.fromisoformat(file_mtime)
            if mtime.tzinfo is not None:
                mtime = mtime.astimezone(datetime.UTC).replace(tzinfo=None)
        except ValueError:
            mtime = None
    if date_from and not dry_run:
        set_setting(db, f"queue_sync_date_from:{company.code}", date_from.isoformat())
    return sync_queue_bytes(db, company, content, user, sheet=sheet, date_from=date_from,
                            file_mtime=mtime, dry_run=dry_run)


# endpointy master data (EKKO/MARM/DLT/porty/LFA1/auto-rozpoznanie) żyją w sub-routerze —
# podpinamy go tutaj, żeby main.py nadal rejestrował jeden router importów
router.include_router(_master_router)

"""Wywołania palet do DLT: analiza per produkt (stan MAG/DLT vs zapotrzebowanie)
oraz CRUD wywołań z eksportem xlsx mailem."""
import io
import math
import threading

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .. import powerbi
from ..audit import record as audit_record
from ..audit import record_changes, record_created
from ..config import settings
from ..database import get_db
from ..deps import (
    AdminOnly as admin_only,
)
from ..deps import (
    Editors as editors,
)
from ..deps import (
    GlobalDataEditors as global_editors,
)
from ..deps import (
    StaffReaders as staff,
)
from ..deps import WarehouseOrEditors as warehouse_or_editors
from ..deps import (
    get_scoped,
    resolve_company_id,
    scope_company,
)
from ..exports import XLSX_MIME
from ..models import (
    MaterialStockTarget,
    PalletCall,
    PalletCallLine,
    PalletCallStatus,
    PalletCallTruck,
    User,
    Warehouse,
    utcnow,
)
from ..notifications import send_html_email
from ..pallets_analysis import PALLET_CAP
from ..pallets_cache import get_analysis
from ..pallets_cache import invalidate as invalidate_analysis
from ..pallets_export import build_xlsx, xlsx_filename
from ..powerbi import PowerBINotConfigured
from ..schemas import (
    AnalysisPage,
    PalletCallCreate,
    PalletCallOut,
    PalletCallUpdate,
    StockTargetIn,
    StockTargetOut,
    StockTargetsPage,
)

TRUCK_CAPACITY = 33          # miejsc paletowych na naczepie
MAX_TRUCKS = 4

router = APIRouter(prefix="/api/pallet-calls", tags=["wywolania-dlt"])


def _next_number(db: Session, company_id: int) -> str:
    year = utcnow().year
    count = db.scalar(select(func.count(PalletCall.id)).where(
        PalletCall.company_id == company_id,
        PalletCall.number.like(f"PC-{year}-%"))) or 0
    return f"PC-{year}-{count + 1:04d}"


def _get_scoped_call(db: Session, call_id: int, user: User) -> PalletCall:
    return get_scoped(db, PalletCall, call_id, user, options=(
        selectinload(PalletCall.lines).selectinload(PalletCallLine.truck),
        selectinload(PalletCall.trucks)))


@router.get("/powerbi/status")
def powerbi_status(user: User = staff, db: Session = Depends(get_db)):
    """Status integracji Power BI dla gatingu UI."""
    return {
        "provider": settings.powerbi_provider,
        "configured": powerbi.is_configured(),
        "delegated": powerbi.has_delegated_session(db),
        # sesja delegowana potrzebna tylko gdy brak wklejonego tokenu i service principal
        "needs_connect": (settings.powerbi_provider == "real"
                          and not settings.powerbi_access_token
                          and not settings.powerbi_client_secret
                          and not powerbi.has_delegated_session(db)),
    }


@router.post("/powerbi/connect")
def powerbi_connect(user: User = admin_only, db: Session = Depends(get_db)):
    """Rozpoczyna device-code; zwraca kod dla użytkownika. Dokończenie w tle."""
    if settings.powerbi_provider != "real":
        raise HTTPException(400, "POWERBI_PROVIDER musi być 'real'")
    app, cache, flow = powerbi.begin_device_flow()
    if "user_code" not in flow:
        raise HTTPException(502, f"Nie udało się rozpocząć logowania: {flow}")
    # kto podpina konto Power BI (token trafia do cache MSAL) — bez samego kodu/tokenu w audycie
    audit_record(db, entity_type="powerbi", entity_id=0, field="device_flow_started",
                 old_value=None, new_value="start logowania", user=user)
    db.commit()
    threading.Thread(target=powerbi.complete_device_flow, args=(app, cache, flow),
                     daemon=True).start()
    return {"message": flow.get("message"), "user_code": flow.get("user_code"),
            "verification_uri": flow.get("verification_uri")}


@router.get("/analysis", response_model=AnalysisPage)
def analysis(user: User = staff, db: Session = Depends(get_db),
             q: str = "", urgent_only: bool = False, missing_paz: bool = False,
             below_target: bool = False, refresh: bool = False,
             limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0)):
    try:
        items, disc, fetched_at, features = get_analysis(db, force=refresh)
    except PowerBINotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    if q:
        ql = q.lower()
        items = [i for i in items if ql in str(i.get("produkt", "")).lower()]
    if urgent_only:
        items = [i for i in items if i.get("pilne")]
    if missing_paz:
        items = [i for i in items if i.get("sugestia_pal") is None]
    if below_target:
        items = [i for i in items
                 if i.get("dni_zapasu") is not None and i.get("cel_dni") is not None
                 and i["dni_zapasu"] < i["cel_dni"]]
    total = len(items)
    return {"items": items[offset:offset + limit], "total": total,
            "fetched_at": fetched_at, "discrepancies": disc, "features": features}


@router.get("/hu-inventory")
def hu_inventory(user: User = staff, db: Session = Depends(get_db)):
    """#65 Inwentaryzacja HU: rozjazdy HU wg PBI (stan DLT) vs HU wywołane.

    Zwraca wiersze per HU z flagami in_dlt/called; degradacja gdy PBI bez kolumny HU
    (features.hu = False) — front pokazuje komunikat zamiast tabeli."""
    try:
        items, _, fetched_at, features = get_analysis(db)
    except PowerBINotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    if not features.get("hu"):
        return {"available": False, "rows": [], "fetched_at": fetched_at}

    # HU w DLT wg PBI: produkt -> {hu: ilosc}
    dlt: dict[str, dict[str, float]] = {}
    for item in items:
        for h in item.get("hu", []):
            dlt.setdefault(item["produkt"], {})[str(h["hu"])] = h.get("ilosc", 0)

    # HU wywołane (linie wywołań w obiegu: sent/confirmed/delivered): hu -> wywołanie
    stmt = (select(PalletCallLine, PalletCall)
            .join(PalletCall, PalletCall.id == PalletCallLine.pallet_call_id)
            .where(PalletCallLine.hu_numbers != "",
                   PalletCall.status.in_((PalletCallStatus.sent,
                                          PalletCallStatus.confirmed,
                                          PalletCallStatus.delivered))))
    stmt = scope_company(stmt, PalletCall.company_id, user)
    called: dict[tuple[str, str], dict] = {}   # (produkt, hu) -> info wywołania
    for line, call in db.execute(stmt):
        for hu in (h.strip() for h in line.hu_numbers.split(",") if h.strip()):
            called[(line.produkt, hu)] = {"call_number": call.number,
                                          "call_status": call.status.value}

    rows = []
    for produkt, hus in dlt.items():
        for hu, qty in hus.items():
            info = called.pop((produkt, hu), None)
            rows.append({
                "produkt": produkt, "hu": hu, "ilosc": qty,
                "in_dlt": True, "called": info is not None,
                "call_number": info["call_number"] if info else "",
                "call_status": info["call_status"] if info else "",
                # wywołane, a wciąż widoczne w DLT = potencjalny rozjazd
                "mismatch": info is not None and info["call_status"] == "delivered",
            })
    for (produkt, hu), info in called.items():
        rows.append({
            "produkt": produkt, "hu": hu, "ilosc": None,
            "in_dlt": False, "called": True,
            "call_number": info["call_number"], "call_status": info["call_status"],
            # wywołane wg statusu w drodze, ale zniknęło z DLT przed dostawą = rozjazd
            "mismatch": info["call_status"] != "delivered",
        })
    rows.sort(key=lambda r: (r["produkt"], r["hu"]))
    return {"available": True, "fetched_at": fetched_at, "rows": rows,
            "mismatches": sum(1 for r in rows if r["mismatch"])}


@router.post("", response_model=PalletCallOut, status_code=201)
def create(body: PalletCallCreate, user: User = editors, db: Session = Depends(get_db)):
    if not body.lines:
        raise HTTPException(422, "Wywołanie musi mieć co najmniej jedną pozycję")
    company_id = resolve_company_id(db, user, body.company_id)
    if not body.allow_over_dlt:
        _guard_dlt_stock(db, body.lines)
    _guard_trucks(body.lines)
    call = PalletCall(company_id=company_id, number=_next_number(db, company_id),
                      status=PalletCallStatus.draft, needed_by=body.needed_by,
                      notes=body.notes, created_by=user.id)
    _apply_lines(call, body.lines)
    db.add(call)
    try:
        db.flush()   # unikalny (company_id, number) — równoległy create → 409, nie 500
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Konflikt numeracji wywołania — spróbuj ponownie.") from None
    audit_record(db, entity_type="pallet_call", entity_id=call.id, field="status",
                 old_value=None, new_value="draft", user=user,
                 note=f"utworzono ({len(call.lines)} poz.)")
    db.commit()
    db.refresh(call)
    return call


def _places(ln) -> int:
    """Miejsca paletowe zajmowane przez pozycję: pełne palety (ceil ułamka)."""
    return math.ceil(float(ln.pallets)) if ln.pallets else math.ceil(float(ln.ilosc_pal))


def _guard_trucks(lines) -> None:
    """Guardy pojemności: ≤33 miejsc na auto, ≤132 (4×33) na całe wywołanie."""
    total = sum(_places(ln) for ln in lines)
    if total > PALLET_CAP:
        raise HTTPException(422,
            f"Wywołanie przekracza {PALLET_CAP} miejsc paletowych ({total}). "
            f"Maksymalnie {MAX_TRUCKS} auta × {TRUCK_CAPACITY} miejsc.")
    per_truck: dict[int, int] = {}
    for ln in lines:
        if ln.truck_no is not None:
            per_truck[ln.truck_no] = per_truck.get(ln.truck_no, 0) + _places(ln)
    over = [n for n, s in per_truck.items() if s > TRUCK_CAPACITY]
    if over:
        raise HTTPException(422,
            f"Auto {', '.join(map(str, sorted(over)))} przekracza "
            f"{TRUCK_CAPACITY} miejsc paletowych.")


def _apply_lines(call: PalletCall, lines) -> None:
    """Buduje pozycje + auta (PalletCallTruck) z przydziałów truck_no na liniach."""
    call.lines = []
    call.trucks = []
    trucks: dict[int, PalletCallTruck] = {}
    for ln in lines:
        data = ln.model_dump(exclude={"truck_no"})
        line = PalletCallLine(**data)
        if ln.truck_no is not None:
            truck = trucks.get(ln.truck_no)
            if truck is None:
                truck = PalletCallTruck(ordinal=ln.truck_no, capacity=TRUCK_CAPACITY)
                trucks[ln.truck_no] = truck
                call.trucks.append(truck)
            line.truck = truck
        call.lines.append(line)


def _guard_dlt_stock(db: Session, lines) -> None:
    """Odrzuca wywołanie, gdy ilość palet przekracza stan w DLT (chyba że allow_over_dlt)."""
    try:
        items, _, _, _ = get_analysis(db)
    except PowerBINotConfigured:
        return                                # brak danych = nie blokujemy
    dlt = {i["produkt"]: i.get("stan_dlt_pal") for i in items}
    over = [ln.produkt for ln in lines
            if dlt.get(ln.produkt) is not None and ln.ilosc_pal > dlt[ln.produkt]]
    if over:
        raise HTTPException(422,
            f"Ilość przekracza stan w DLT dla: {', '.join(over)}. "
            f"Ustaw allow_over_dlt=true, aby wymusić.")


@router.get("", response_model=list[PalletCallOut])
def list_calls(user: User = staff, db: Session = Depends(get_db)):
    stmt = (select(PalletCall).options(selectinload(PalletCall.lines))
            .order_by(PalletCall.id.desc()))
    stmt = scope_company(stmt, PalletCall.company_id, user)
    return list(db.scalars(stmt))


@router.get("/{call_id}", response_model=PalletCallOut)
def get_one(call_id: int, user: User = staff, db: Session = Depends(get_db)):
    return _get_scoped_call(db, call_id, user)


@router.patch("/{call_id}", response_model=PalletCallOut)
def update(call_id: int, body: PalletCallUpdate, user: User = editors,
           db: Session = Depends(get_db)):
    call = _get_scoped_call(db, call_id, user)
    if call.status != PalletCallStatus.draft:
        raise HTTPException(409, "Edycja możliwa tylko dla szkicu")
    changes = {k: v for k, v in (("needed_by", body.needed_by), ("notes", body.notes))
               if v is not None}
    record_changes(db, call, changes, user)
    if body.lines is not None:
        _guard_trucks(body.lines)
        before = len(call.lines)
        _apply_lines(call, body.lines)
        audit_record(db, entity_type=call.__tablename__, entity_id=call.id, field="lines",
                     old_value=f"{before} poz.", new_value=f"{len(body.lines)} poz.", user=user)
    db.commit()
    db.refresh(call)
    return call


def _dlt_recipients(db: Session) -> list[str]:
    """Adresy DLT: e-mail magazynu DLT ze słownika -> env DLT_CALL_EMAILS -> DLT_EMAIL."""
    whs = db.scalars(select(Warehouse).where(Warehouse.is_active.is_(True))).all()
    emails = [w.email for w in whs if w.email and "dlt" in w.name.lower()]
    if emails:
        return emails
    if settings.dlt_call_emails_list:
        return settings.dlt_call_emails_list
    return [settings.dlt_email] if settings.dlt_email else []


@router.post("/{call_id}/send", response_model=PalletCallOut)
def send(call_id: int, user: User = editors, db: Session = Depends(get_db)):
    call = _get_scoped_call(db, call_id, user)
    recipients = _dlt_recipients(db)
    if not recipients:
        raise HTTPException(400,
            "Brak adresu DLT (e-mail magazynu DLT, DLT_CALL_EMAILS lub DLT_EMAIL)")
    if user.email:                          # kopia do wywołującego
        recipients = recipients + [user.email]
    xlsx = build_xlsx(call)
    trucks_info = f", {len(call.trucks)} aut" if call.trucks else ""
    html = (f"<p>Wywołanie palet <b>{call.number}</b> — {len(call.lines)} "
            f"pozycji{trucks_info}.</p>")
    from .dlt import create_dlt_link
    raw_token = create_dlt_link(db, call)
    base = (settings.public_base_url or "").rstrip("/")
    dlt_url = f"{base}/dlt/{raw_token}"
    html += (f'<p>Potwierdzenie przygotowania i wysyłki: '
             f'<a href="{dlt_url}">{dlt_url}</a></p>')
    send_html_email(recipients, f"Wywołanie palet {call.number}", html,
                    attachments=[(xlsx_filename(call), xlsx, XLSX_MIME)])
    _set_status(db, call, PalletCallStatus.sent, user)
    call.sent_at = utcnow()
    db.commit()
    db.refresh(call)
    return call


@router.get("/{call_id}/xlsx")
def download_xlsx(call_id: int, user: User = staff, db: Session = Depends(get_db)):
    call = _get_scoped_call(db, call_id, user)
    data = build_xlsx(call)
    return StreamingResponse(
        io.BytesIO(data), media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{xlsx_filename(call)}"'})


def _set_status(db: Session, call: PalletCall, new: PalletCallStatus, user: User) -> None:
    old = call.status.value
    call.status = new
    audit_record(db, entity_type="pallet_call", entity_id=call.id, field="status",
                 old_value=old, new_value=new.value, user=user)


@router.post("/{call_id}/confirm", response_model=PalletCallOut)
def confirm(call_id: int, user: User = editors, db: Session = Depends(get_db)):
    call = _get_scoped_call(db, call_id, user)
    _set_status(db, call, PalletCallStatus.confirmed, user)
    db.commit()
    db.refresh(call)
    return call


@router.post("/{call_id}/prepared", response_model=PalletCallOut)
def prepared(call_id: int, user: User = warehouse_or_editors, db: Session = Depends(get_db)):
    """Magazyn DLT (konto z rolą warehouse) potwierdza przygotowanie — zamiast linku z maila
    (decyzja 2026-10-07: nic bez logowania). Ta sama reguła i powiadomienia co strona DLT."""
    from .dlt import mark_prepared
    call = _get_scoped_call(db, call_id, user)
    mark_prepared(db, call, user, "w aplikacji")
    db.refresh(call)
    return call


@router.post("/{call_id}/shipped", response_model=PalletCallOut)
def shipped(call_id: int, user: User = warehouse_or_editors, db: Session = Depends(get_db)):
    from .dlt import mark_shipped
    call = _get_scoped_call(db, call_id, user)
    mark_shipped(db, call, user, "w aplikacji")
    db.refresh(call)
    return call


@router.post("/{call_id}/deliver", response_model=PalletCallOut)
def deliver(call_id: int, user: User = editors, db: Session = Depends(get_db)):
    """Palety przywiezione — przestają być odejmowane z sugestii (wychodzą z 'w drodze')."""
    call = _get_scoped_call(db, call_id, user)
    _set_status(db, call, PalletCallStatus.delivered, user)
    db.commit()
    db.refresh(call)
    return call


@router.post("/{call_id}/cancel", response_model=PalletCallOut)
def cancel(call_id: int, user: User = editors, db: Session = Depends(get_db)):
    call = _get_scoped_call(db, call_id, user)
    _set_status(db, call, PalletCallStatus.cancelled, user)
    db.commit()
    db.refresh(call)
    return call


# --- Cele pokrycia zapasu (dni) per materiał — nadpisania globalnego celu ---
targets_router = APIRouter(prefix="/api/stock-targets", tags=["wywolania-dlt"])


@targets_router.get("", response_model=StockTargetsPage)
def list_targets(user: User = staff, db: Session = Depends(get_db)):
    items = db.scalars(select(MaterialStockTarget)
                       .order_by(MaterialStockTarget.material_no)).all()
    return {"global_days": settings.pallet_target_days, "items": items}


@targets_router.post("", response_model=StockTargetOut)
def upsert_target(body: StockTargetIn, user: User = global_editors,
                  db: Session = Depends(get_db)):
    material_no = body.material_no.strip()
    row = db.scalar(select(MaterialStockTarget)
                    .where(MaterialStockTarget.material_no == material_no))
    if row is None:
        row = MaterialStockTarget(material_no=material_no, days=body.days)
        db.add(row)
        record_created(db, row, user, label=f"{material_no}: {body.days} dni")
    else:
        record_changes(db, row, {"days": body.days}, user, note=material_no)
        row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    invalidate_analysis(db)     # cel wpływa na podpowiedzi — przelicz przy odczycie
    return row


@targets_router.delete("/{target_id}", status_code=204)
def delete_target(target_id: int, user: User = global_editors,
                  db: Session = Depends(get_db)):
    row = db.get(MaterialStockTarget, target_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono celu")
    audit_record(db, entity_type=row.__tablename__, entity_id=row.id, field="delete",
                 old_value=f"{row.material_no}: {row.days} dni", new_value=None, user=user)
    db.delete(row)
    db.commit()
    invalidate_analysis(db)

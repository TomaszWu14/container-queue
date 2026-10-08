"""W5 — dokumenty i OCR: propozycje podpięcia (31), braki przed ETA (32),
porównania dokument↔system (33/34), masowe ZIP-y (35), szablony wysyłki (36)."""
import datetime
import io
import logging
import pathlib
import secrets
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import audit
from ..config import settings
from ..database import get_db
from ..date_pl import date_pl
from ..deps import Editors as logistics_or_admin
from ..deps import NonWarehouseViewers as non_warehouse
from ..deps import PurchasingReaders as purchasing_readers
from ..deps import Viewer as viewer
from ..deps import (
    forwarder_may_see,
    forwarder_may_see_sql,
    get_company_by_code,
    get_scoped,
    require_roles,
    scope_company,
    scope_containers,
)
from ..mail_html import esc
from ..models import (
    INVOICE_LIKE_KINDS,
    Attachment,
    AttachmentSuggestion,
    Container,
    CustomsStatus,
    DocumentStatus,
    DocumentType,
    FreightInvoice,
    InvoiceBatch,
    InvoiceDocKind,
    InvoiceJob,
    Role,
    SuggestionStatus,
    User,
    pl_midnight_utc,
    today_pl,
    utcnow,
)
from ..print_button import PRINT_SCRIPT
from ..schemas import (
    AttachmentSuggestionOut,
    SuggestionAcceptIn,
)
from .containers import get_container_checked, hidden_fields
from .customs import missing_document_types_batch
from .doc_templates import (  # noqa: F401 — re-eksport (customs.py, testy)
    DEFAULT_DOCS_BODY,
    DEFAULT_DOCS_SUBJECT,
    _Keep,
    render_docs_message,
    template_for,
)
from .doc_templates import router as doc_templates_router
from ..document_gate import digest, duplicate_reason
from .forwarding import commit_with_file, safe_filename, uploads_dir

router = APIRouter(prefix="/api", tags=["dokumenty (W5)"])
logger = logging.getLogger(__name__)

# role z dostępem do faktur (jak PurchasingReaders / router invoices) — tylko one widzą
# w wyszukiwarce faktury CIPL (InvoiceJob, treść = ceny) i faktury transportowe
_INVOICE_ROLES = (Role.admin, Role.logistics, Role.purchasing)


@router.get("/documents/search")
def search_documents(q: str = Query(default="", max_length=120),
                     supplier_id: int | None = Query(default=None),
                     document_type_id: int | None = Query(default=None),
                     limit: int = Query(default=100, le=500),
                     db: Session = Depends(get_db), user: User = viewer) -> list[dict]:
    """#41 — archiwum dokumentów z wyszukiwaniem pełnotekstowym po WSZYSTKICH źródłach
    w zasięgu spółki użytkownika: załączniki kontenerów, dokumenty faktur (InvoiceJob,
    z text_excerpt), faktury transportowe. ILIKE po polach tekstowych; scope_containers
    pilnuje izolacji (dokumenty spoza spółki nie wyciekają)."""
    term = q.strip()
    like = f"%{term}%"
    out: list[dict] = []

    # dostawca maskowany tak jak w to_out (magazyn/agencja celna nie widzą danych handlowych)
    hide_supplier = "supplier_id" in hidden_fields(user)
    can_see_invoices = user.role in _INVOICE_ROLES

    def supplier_of(cont: Container) -> str | None:
        return cont.supplier.name if cont.supplier and not hide_supplier else None

    # (a) załączniki per kontener — scope przez Container
    aq = (select(Attachment, Container).join(Container, Attachment.container_id == Container.id)
          .outerjoin(DocumentType, Attachment.document_type_id == DocumentType.id))
    aq = scope_containers(aq, user).where(forwarder_may_see_sql(user))   # spedytor/magazyn: przed limitem
    if supplier_id is not None and not hide_supplier:   # filtr po ukrytym = wyrocznia
        aq = aq.where(Container.supplier_id == supplier_id)
    if document_type_id is not None:
        aq = aq.where(Attachment.document_type_id == document_type_id)
    if term:
        aq = aq.where(Attachment.filename.ilike(like) | DocumentType.name.ilike(like))
    for att, cont in db.execute(aq.limit(limit)).all():
        out.append({
            "source": "attachment", "id": att.id, "title": att.filename,
            "container_id": cont.id, "container_no": cont.container_no,
            "supplier_name": supplier_of(cont),
            "document_type": att.document_type.name if att.document_type else None,
            "created_at": att.created_at.isoformat() if att.created_at else None,
            "download_url": f"/api/attachments/{att.id}/download",
        })

    # (b) dokumenty faktur (InvoiceJob) — jedyne z treścią (text_excerpt) do full-text;
    # tylko role z dostępem do faktur, inaczej ILIKE po text_excerpt byłby wyrocznią cen
    if document_type_id is None and can_see_invoices:
        jq = (select(InvoiceJob, Container)
              .join(InvoiceBatch, InvoiceJob.batch_id == InvoiceBatch.id)
              .join(Container, InvoiceBatch.container_id == Container.id))
        jq = scope_containers(jq, user)
        if supplier_id is not None:
            jq = jq.where(InvoiceBatch.supplier_id == supplier_id)
        if term:
            jq = jq.where(InvoiceJob.filename.ilike(like) | InvoiceJob.invoice_number.ilike(like)
                          | InvoiceJob.container_no.ilike(like) | InvoiceJob.text_excerpt.ilike(like))
        for job, cont in db.execute(jq.limit(limit)).all():
            out.append({
                "source": "invoice", "id": job.id,
                "title": job.filename or job.invoice_number or f"faktura #{job.id}",
                "container_id": cont.id, "container_no": cont.container_no,
                "supplier_name": supplier_of(cont),
                "document_type": job.doc_kind.value if job.doc_kind else None,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "download_url": None,
            })

    # (c) faktury transportowe — własne company_id (bez powiązania per-kontener);
    # tylko role z dostępem do faktur (jak PurchasingReaders) — pozostałym sekcję
    # pomijamy, zamiast blokować całe wyszukiwanie (np. spedytor bez spółki)
    if (document_type_id is None and supplier_id is None
            and can_see_invoices):
        fq = scope_company(select(FreightInvoice), FreightInvoice.company_id, user)
        if term:
            fq = fq.where(FreightInvoice.filename.ilike(like) | FreightInvoice.invoice_number.ilike(like)
                          | FreightInvoice.bl_number.ilike(like) | FreightInvoice.note.ilike(like))
        for inv in db.scalars(fq.limit(limit)).all():
            out.append({
                "source": "freight", "id": inv.id,
                "title": inv.filename or inv.invoice_number or inv.bl_number or f"BL #{inv.id}",
                "container_id": None, "container_no": None,
                "supplier_name": inv.forwarder.name if inv.forwarder else None,
                "document_type": "freight_invoice",
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
                "download_url": (f"/api/freight-invoices/{inv.id}/download"
                                 if inv.stored_name else None),
            })

    out.sort(key=lambda r: r["created_at"] or "", reverse=True)
    return out[:limit]


cmr_users = Depends(require_roles(Role.admin, Role.logistics, Role.forwarder, Role.warehouse))


@router.get("/containers/{container_id}/cmr", response_class=HTMLResponse)
def container_cmr(container_id: int, db: Session = Depends(get_db), user: User = cmr_users):
    """#19 — drukowalny list przewozowy (CMR) wypełniony danymi kontenera. HTML z print-CSS
    (bez zależności PDF — użytkownik drukuje/zapisuje do PDF z przeglądarki). Zakres get_scoped."""
    c = get_scoped(db, Container, container_id, user)
    hidden = hidden_fields(user)   # magazyn: bez dostawcy i uwag zakupowych (jak to_out)

    def e(v) -> str:
        return esc(v, empty="—")

    delivery = c.warehouse.name if c.warehouse else None
    date = c.eta or c.notify_date
    rows = [
        ("1. Nadawca / Sender", e(c.supplier.name
                                  if c.supplier and "supplier_name" not in hidden else None)),
        ("2. Odbiorca / Consignee", e(c.company.name if c.company else None)),
        ("3. Miejsce przeznaczenia / Place of delivery", e(delivery)),
        ("5. Przewoźnik / Carrier", e(c.forwarder.name if c.forwarder else None)),
        ("6. Nr kontenera / Container no", e(c.container_no)),
        ("11. Liczba palet / Packages", e(getattr(c, "pallet_count", None) or None)),
        ("Data / Date", e(date_pl(date) or None)),
        ("Uwagi / Remarks", e("" if "purchase_note" in hidden else c.purchase_note)),
    ]
    body = "".join(f"<tr><th>{label}</th><td>{value}</td></tr>" for label, value in rows)
    doc = f"""<!doctype html><html lang="pl"><head><meta charset="utf-8">
<title>CMR {e(c.container_no)}</title><style>
body{{font-family:Arial,sans-serif;margin:24px;color:#111}}
h1{{font-size:18px;margin:0 0 4px}} .sub{{color:#555;font-size:12px;margin-bottom:16px}}
table{{border-collapse:collapse;width:100%;max-width:720px}}
th,td{{border:1px solid #333;padding:8px 10px;font-size:13px;text-align:left;vertical-align:top}}
th{{width:42%;background:#f3f4f6;font-weight:600}}
@media print{{.noprint{{display:none}}}}
</style></head><body>
<h1>Międzynarodowy list przewozowy — CMR</h1>
<div class="sub">Kontener {e(c.container_no)} · wygenerowano z systemu</div>
<table><tbody>{body}</tbody></table>
<button class="noprint" style="margin-top:16px" data-print>Drukuj / Zapisz PDF</button>
{PRINT_SCRIPT}
</body></html>"""
    return HTMLResponse(content=doc)


# --- 31: propozycje podpięcia dokumentów z OCR ------------------------------

def _suggestion_out(s: AttachmentSuggestion, container_no: str | None = None) \
        -> AttachmentSuggestionOut:
    out = AttachmentSuggestionOut.model_validate(s)
    out.status = s.status.value
    if s.job:
        out.filename = s.job.filename
        out.invoice_number = s.job.invoice_number
        out.page_from, out.page_to = s.job.page_from, s.job.page_to
    out.container_no = container_no
    return out


@router.get("/containers/{container_id}/attachment-suggestions",
            response_model=list[AttachmentSuggestionOut])
def list_suggestions(container_id: int, db: Session = Depends(get_db), user: User = purchasing_readers):
    container = get_container_checked(db, container_id, user)
    rows = db.scalars(select(AttachmentSuggestion)
                      .options(selectinload(AttachmentSuggestion.job))
                      .where(AttachmentSuggestion.container_id == container_id)
                      .order_by(AttachmentSuggestion.created_at.desc())).all()
    return [_suggestion_out(s, container.container_no) for s in rows]


def _get_suggestion(db: Session, suggestion_id: int, user: User) -> AttachmentSuggestion:
    # izolacja: AttachmentSuggestion ma container_id → ogólna gałąź w deps
    suggestion = get_scoped(db, AttachmentSuggestion, suggestion_id, user,
                            options=(selectinload(AttachmentSuggestion.job),))
    if suggestion.status != SuggestionStatus.proposed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Propozycja została już rozstrzygnięta.")
    return suggestion


@router.post("/attachment-suggestions/{suggestion_id}/accept",
             response_model=AttachmentSuggestionOut)
def accept_suggestion(suggestion_id: int, body: SuggestionAcceptIn | None = None,
                      db: Session = Depends(get_db), user: User = purchasing_readers):
    """Akceptacja: kopiuje plik części PDF (wycinek stron ze splittera) jako zwykły
    Attachment kontenera + audyt. Typ dokumentu: z body albo bez typu."""
    suggestion = _get_suggestion(db, suggestion_id, user)
    job = suggestion.job
    if not job:
        raise HTTPException(status.HTTP_410_GONE, "Dokument źródłowy został usunięty.")
    source = uploads_dir() / job.stored_name
    if not source.is_file():
        raise HTTPException(status.HTTP_410_GONE, "Plik dokumentu został usunięty z dysku.")
    document_type_id = body.document_type_id if body else None
    if document_type_id is not None:
        document_type = db.get(DocumentType, document_type_id)
        if not document_type or not document_type.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                "Nie znaleziono aktywnego typu dokumentu.")
    content = source.read_bytes()
    # §4 pkt 12: ten sam dokument już leży w kontenerze docelowym — bez kopii
    duplicate = duplicate_reason(db, suggestion.container_id, content, uploads_dir())
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ten dokument {duplicate}.")
    base = pathlib.Path(job.filename).stem[:120]
    filename = f"{base}_str{job.page_from}-{job.page_to}.pdf" \
        if job.page_to > job.page_from else f"{base}.pdf"
    stored = f"{suggestion.container_id}_{secrets.token_hex(8)}_{filename}"
    attachment = Attachment(container_id=suggestion.container_id, filename=filename,
                            stored_name=stored, content_type="application/pdf",
                            size=len(content), sha256=digest(content), uploaded_by_id=user.id,
                            document_type_id=document_type_id)
    db.add(attachment)
    db.flush()
    suggestion.status = SuggestionStatus.accepted
    suggestion.attachment_id = attachment.id
    suggestion.document_type_id = document_type_id
    suggestion.decided_by_id, suggestion.decided_at = user.id, utcnow()
    audit.record(db, entity_type="containers", entity_id=suggestion.container_id,
                 field="attachment_suggestion", old_value="proposed", new_value="accepted",
                 user=user, note=f"podpięto {filename} (z OCR, dokument {job.id})")
    commit_with_file(db, uploads_dir() / stored, content)   # §4 pkt 32: bez sieroty przy błędzie commitu
    container = db.get(Container, suggestion.container_id)
    return _suggestion_out(suggestion, container.container_no if container else None)


@router.post("/attachment-suggestions/{suggestion_id}/reject",
             response_model=AttachmentSuggestionOut)
def reject_suggestion(suggestion_id: int, db: Session = Depends(get_db), user: User = purchasing_readers):
    suggestion = _get_suggestion(db, suggestion_id, user)
    suggestion.status = SuggestionStatus.rejected
    suggestion.decided_by_id, suggestion.decided_at = user.id, utcnow()
    audit.record(db, entity_type="containers", entity_id=suggestion.container_id,
                 field="attachment_suggestion", old_value="proposed", new_value="rejected",
                 user=user, note=f"odrzucono propozycję (dokument {suggestion.job_id})")
    db.commit()
    return _suggestion_out(suggestion)


# --- 32: braki dokumentów przed ETA (sekcja pulpitu) ------------------------

@router.get("/customs/docs-gaps")
def docs_gaps(db: Session = Depends(get_db), user: User = logistics_or_admin):
    # dokumenty odprawowe: bez spedytora (decyzja 2026-09-28 cofa #662)
    """Kontenery w obiegu celnym z ETA ≤ dziś+DOCS_ETA_DAYS i brakami wymaganych
    typów dokumentów — ta sama reguła co alert check_docs_alerts."""
    today = today_pl()
    horizon = today + datetime.timedelta(days=settings.docs_eta_days)
    query = scope_containers(select(Container).where(
        Container.eta.is_not(None), Container.eta <= horizon,
        Container.document_status != DocumentStatus.WYSLANE,
        (Container.customs_agency_id.is_not(None))
        | (Container.customs_status != CustomsStatus.BRAK)), user)
    out = []
    containers = db.scalars(query.order_by(Container.eta)).all()
    gaps = missing_document_types_batch(db, containers)
    for container in containers:
        missing = gaps[container.id]
        if missing:
            out.append({"id": container.id, "container_no": container.container_no,
                        "eta": container.eta.isoformat() if container.eta else None,
                        "missing": missing})
    return out


# --- 33/34: porównania dokument ↔ system ------------------------------------

@router.get("/invoice-jobs/{job_id}/packing-compare")
def packing_compare(job_id: int, db: Session = Depends(get_db), user: User = purchasing_readers):
    """#33: packing lista (OCR) vs pozycje zamówień kontenera. Sam raport —
    nic nie nadpisuje danych."""
    from ..invoices.compare import packing_list_report
    job = get_scoped(db, InvoiceJob, job_id, user)
    if job.doc_kind != InvoiceDocKind.packing_list:
        raise HTTPException(status.HTTP_409_CONFLICT, "To nie jest packing lista.")
    container = db.get(Container, job.batch.container_id)
    try:
        return packing_list_report(db, job, container, uploads_dir())
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_410_GONE,
                            "Plik packing listy został usunięty z dysku.") from exc


@router.get("/invoice-jobs/{job_id}/order-compare")
def order_compare(job_id: int, db: Session = Depends(get_db), user: User = purchasing_readers):
    """#34: kwoty i ilości faktury vs zamówienie (EKKO + pozycje). Sam raport."""
    from ..invoices.compare import invoice_vs_order
    job = get_scoped(db, InvoiceJob, job_id, user)
    if job.doc_kind not in INVOICE_LIKE_KINDS:
        raise HTTPException(status.HTTP_409_CONFLICT, "To nie jest faktura.")
    container = db.get(Container, job.batch.container_id)
    return invoice_vs_order(db, job, container, settings.invoice_tolerance_pct)


# --- 35: masowe pobieranie ZIP ------------------------------------------------

def _zip_attachments(attachments: list[Attachment]) -> bytes:
    """ZIP w pamięci (zipfile stdlib). Załączniki są ograniczone max_upload_mb,
    a liczba plików limitem archive_zip_max_files — bufor nie rośnie bez końca."""
    uploads = uploads_dir()
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for attachment in attachments:
            path = uploads / attachment.stored_name
            if not path.is_file():
                continue
            # arcname bez ścieżki (zip-slip: „../”, „..\”, „/”) — nazwa od klienta
            name = safe_filename(attachment.filename or attachment.stored_name)
            if name in used:   # duplikaty nazw: dopisz id, zamiast nadpisać wpis w ZIP
                name = f"{attachment.id}_{name}"
            used.add(name)
            archive.write(path, arcname=name)
    return buf.getvalue()


def _zip_response(content: bytes, filename: str) -> Response:
    return Response(content, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/containers/{container_id}/attachments/zip")
def container_attachments_zip(container_id: int, db: Session = Depends(get_db),
                              user: User = non_warehouse):
    """„Pobierz wszystkie (ZIP)” — załączniki kontenera jednym plikiem."""
    container = get_container_checked(db, container_id, user)
    attachments = db.scalars(select(Attachment)
                             .options(selectinload(Attachment.document_type))
                             .where(Attachment.container_id == container_id)
                             .order_by(Attachment.created_at)).all()
    attachments = [a for a in attachments if forwarder_may_see(a, user)]   # spedytor: CMR i własne
    if not attachments:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brak załączników.")
    content = _zip_attachments(attachments)
    logger.info("ZIP kontenera %s: %s plików, %s B (user %s)",
                container.container_no, len(attachments), len(content), user.login)
    return _zip_response(content, f"dokumenty_{container.container_no}.zip")


@router.get("/archive/attachments-zip")
def monthly_attachments_zip(company_code: str, month: str,
                            db: Session = Depends(get_db),
                            user: User = logistics_or_admin):
    """Archiwum kolejki: ZIP dokumentów miesiąca per spółka (YYYY-MM).
    Limit ARCHIVE_ZIP_MAX_FILES chroni serwer; pobranie idzie do audytu."""
    try:
        first = datetime.date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Miesiąc w formacie YYYY-MM.") from exc
    company = get_company_by_code(db, user, company_code)
    next_month = (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    attachments = db.scalars(
        scope_containers(
            select(Attachment).join(Container, Attachment.container_id == Container.id), user)
        .where(Container.company_id == company.id,
               Attachment.created_at >= pl_midnight_utc(first),
               Attachment.created_at < pl_midnight_utc(next_month))
        .order_by(Attachment.created_at)
        .limit(settings.archive_zip_max_files + 1)).all()
    if not attachments:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brak dokumentów w tym miesiącu.")
    if len(attachments) > settings.archive_zip_max_files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Za dużo plików (> {settings.archive_zip_max_files}) — "
                            "zawęź zakres (pobierz per kontener).")
    content = _zip_attachments(attachments)
    audit.record(db, entity_type="companies", entity_id=company.id, field="attachments_zip",
                 old_value=None, new_value=month, user=user,
                 note=f"{len(attachments)} plików, {len(content)} B")
    db.commit()
    return _zip_response(content, f"dokumenty_{company.code}_{month}.zip")


# --- 36: szablony wysyłki dokumentów do agencji — doc_templates.py ---
router.include_router(doc_templates_router)

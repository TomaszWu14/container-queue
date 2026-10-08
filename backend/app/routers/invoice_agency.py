"""Faktury do agencji celnej jako szkic maila (.eml) — Outlook otwiera go do edycji,
użytkownik sam klika „Wyślij” ze swojego konta. Serwer niczego nie wysyła (decyzja
2026-09-24: bez uprawnień do skrzynek i bez Microsoft Graph).

Podgląd (2026-10-06, „nie widzę, co wyszło i czy jest OK”): te same części maila co .eml —
odbiorcy, temat, treść, załączniki z rozmiarami i ostrzeżenia — zanim powstanie szkic."""
import io
import mimetypes
import re

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import agency_templates, audit
from ..attachment_links import in_container
from ..audit import record_changes
from ..avizo_workflow import split_addresses
from ..database import get_db
from ..eml import build_eml
from ..invoices import sad_export, symbols
from ..mail_html import esc
from ..invoices.splitter import is_bill_of_lading
from ..models import (INVOICE_LIKE_KINDS, Attachment, DocumentStatus, DocumentType, InvoiceBatch,
                      InvoiceDocKind, InvoiceJobStatus, InvoiceMatchStatus, User)
from .customs import docs_senders
from .forwarding import safe_filename, uploads_dir
from .invoices import _get_batch

router = APIRouter(prefix="/api", tags=["faktury"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail)


def _symbols(db: Session, batch: InvoiceBatch, invoices, user: User) -> bytes:
    """Kartoteka symboli wg wzoru z Master data (co to za towary — obok Excela pozycji)."""
    container = batch.container
    agency = container.customs_agency_rel
    supplier = batch.supplier or container.supplier
    buf = io.BytesIO()
    symbols.build_workbook(db, invoices, container.company_id, supplier.country if supplier else "",
                           ((agency.export_params if agency else None) or {}).get(
                               "IDZestawu", symbols.DEFAULT_ID_ZESTAWU),
                           user.login, template=agency_templates.load(db, "winsad_symbole")).save(buf)
    return buf.getvalue()


def _warnings(db: Session, batch: InvoiceBatch, invoices, symbols_xlsx: bytes) -> list[str]:
    """Co agencja dostanie inaczej, niż użytkownik zakłada — pokazywane przed wysyłką."""
    out = []
    pending = [j for j in batch.jobs if j.doc_kind in INVOICE_LIKE_KINDS
               and j.status not in (InvoiceJobStatus.confirmed, InvoiceJobStatus.ignored)]
    if pending:
        out.append(f"{len(pending)} faktur(y) niezatwierdzone — nie trafią do maila: "
                   + ", ".join(j.invoice_number or j.filename for j in pending[:5]))
    unmatched = sorted({i.raw_ref or i.descr[:30] for j in invoices for i in j.items
                        if not i.skipped and i.match_status != InvoiceMatchStatus.matched})
    if unmatched:
        out.append(f"{len(unmatched)} pozycji bez dopasowania do master daty — brak w kartotece "
                   f"symboli, w Excelu bez nazwy PL / CN: {', '.join(unmatched[:8])}")
    import openpyxl
    rows = list(openpyxl.load_workbook(io.BytesIO(symbols_xlsx), read_only=True).active
                .iter_rows(values_only=True))
    if len(rows) <= 1:
        out.append("Kartoteka symboli jest pusta — żadna pozycja nie ma dopasowanego REF.")
    required = [c["name"] for c in agency_templates.load(db, "winsad_symbole")["columns"] if c["required"]]
    head = list(rows[0]) if rows else []
    for name in required:
        if name in head:
            empty = sum(1 for r in rows[1:] if r[head.index(name)] in (None, ""))
            if empty:
                out.append(f"Kartoteka symboli: wymagana kolumna „{name}” pusta w {empty} wierszach.")
    return out


def _sadue(db: Session, batch: InvoiceBatch) -> tuple[bytes | None, list[str]]:
    """XML SADUE do maila: blokada XML nie blokuje maila — idzie bez XML, powód w ostrzeżeniach."""
    try:
        return sad_export.build(db, batch)
    except sad_export.SadExportError as exc:
        return None, [f"Bez XML do WinSAD: {exc}"]


def _mail(db: Session, batch: InvoiceBatch, user: User) -> dict:
    """Wszystkie części szkicu maila (wspólne dla podglądu i .eml); 409 = nie da się złożyć."""
    container = batch.container
    agency = container.customs_agency_rel
    if agency is None:
        raise _conflict("Kontener nie ma przypisanej agencji celnej.")
    to = split_addresses(agency.email)
    if not to:
        raise _conflict(f"Agencja {agency.name} nie ma adresu e-mail.")
    if batch.attachment is None or not batch.ready:   # = excel_current z _batches_out
        # blokada zamiast cichej regeneracji: eksport ma własne reguły (wszystkie zatwierdzone
        # albo świadomy eksport częściowy) i role — decyzję zostawiamy przyciskowi eksportu
        raise _conflict("Excel paczki jest nieaktualny lub niewygenerowany — "
                        "wygeneruj Excel ponownie i dopiero wtedy przygotuj maila.")
    lowered = {a.lower() for a in to}
    cc: list[str] = []
    for address in split_addresses(container.company.avizo_cc if container.company else ""):
        if address.lower() not in lowered:
            lowered.add(address.lower())
            cc.append(address)

    uploads = uploads_dir()
    # czytelna nazwa dla agencji: Faktury_<kontener>_<data wygenerowania Excela>.xlsx
    generated = batch.attachment.created_at.date().isoformat() if batch.attachment.created_at else ""
    excel_name = f"Faktury_{container.container_no}_{generated}.xlsx".replace("_.xlsx", ".xlsx")
    invoices = [job for job in batch.jobs
                if job.doc_kind in INVOICE_LIKE_KINDS and job.status == InvoiceJobStatus.confirmed]
    files: list[tuple[str, str, str, str, int | None]] = [(excel_name, batch.attachment.stored_name,
              batch.attachment.content_type or "application/octet-stream", "excel", None)]
    files += [(job.filename, job.stored_name, "application/pdf", "invoice", job.id) for job in invoices]
    # audyt 2026-10-06 #12: komplet do odprawy — packing listy i B/L z zestawu (wcześniej tylko
    # faktury → użytkownik wgrywał PL/B/L drugi raz do „Pliki”, stąd duble)
    files += [(job.filename, job.stored_name, "application/pdf", "packing_list", job.id)
              for job in batch.jobs if job.doc_kind == InvoiceDocKind.packing_list
              and job.status == InvoiceJobStatus.packing_list]
    bls = [job for job in batch.jobs
           if job.doc_kind == InvoiceDocKind.other and is_bill_of_lading(job.text_excerpt)]
    files += [(job.filename, job.stored_name, "application/pdf", "bl", job.id) for job in bls]
    # dokumenty kontenera spoza paczki (kafelki): CI/PL wgrane jako pliki też idą do odprawy;
    # B/L tylko gdy nie ma go w zestawie i tylko najnowszy — po podmianie stary zostawał w mailu
    # (§4 pkt 23). Typ MIME z rozszerzenia, nie od przeglądarki wgrywającego (pkt 39).
    kind_of = {"CI": "invoice", "PL": "packing_list", "BL": "bl"}
    tiles = db.execute(select(Attachment, DocumentType.tile_code).join(DocumentType).where(
        in_container(container.id), DocumentType.tile_code.in_(kind_of))
        .order_by(Attachment.created_at)).all()
    loose = [(a, code) for a, code in tiles if code != "BL"]
    if not bls:
        loose += [(a, code) for a, code in tiles if code == "BL"][-1:]
    files += [(a.filename, a.stored_name, mimetypes.guess_type(a.filename)[0] or "application/octet-stream",
               kind_of.get(code or "", "bl"), -a.id) for a, code in loose]
    attachments = []   # (nazwa, bajty, typ MIME, rodzaj, id dokumentu do podglądu)
    for filename, stored_name, content_type, kind, ref in files:
        path = uploads / stored_name
        if not stored_name or not path.is_file():
            raise _conflict(f"Brak pliku: {filename}.")
        attachments.append((safe_filename(filename, "plik"), path.read_bytes(), content_type, kind, ref))
    symbols_xlsx = _symbols(db, batch, invoices, user)
    attachments.insert(1, (safe_filename(f"kartoteka_symboli_{container.container_no}.xlsx", "kartoteka.xlsx"),
                           symbols_xlsx, XLSX, "symbols", None))
    sadue, sadue_warnings = _sadue(db, batch)
    if sadue is not None:
        attachments.insert(2, (safe_filename(f"SAD_{container.container_no}.xml", "SAD.xml"), sadue,
                               "application/xml", "sadue", None))

    company = container.company.name if container.company else ""
    # audyt 2026-10-06 #16: Excel z części faktur (eksport częściowy) nie może wyglądać jak komplet
    expected = [j for j in batch.jobs
                if j.doc_kind in INVOICE_LIKE_KINDS and j.status != InvoiceJobStatus.ignored]
    partial = len(invoices) < len(expected)
    subject = f"Faktury — {container.container_no} — {company}"         + (f" (częściowe {len(invoices)}/{len(expected)})" if partial else "")
    names = [a[0] for a in attachments]
    kinds = {a[3] for a in attachments}
    lines = [f"Nr kontenera: {container.container_no}",
             f"Liczba faktur: {len(invoices)}" + (f" z {len(expected)} — pozostałe dośle(my) osobno"
                                                  if partial else "")]
    extra = [label for kind, label in (("packing_list", "packing listy"), ("bl", "konosament (B/L)"))
             if kind in kinds]
    intro = ("w załączeniu dokumenty do odprawy: zestawienie faktur w Excelu, "
             "kartoteka symboli, oryginały faktur (PDF)"
             + (f" oraz {' i '.join(extra)}" if extra else "") + ".")
    text = f"Dzień dobry,\n\n{intro}\n\n" + "\n".join(lines) \
        + "\n\nZałączniki:\n" + "\n".join(f"- {n}" for n in names) + "\n"
    html = (f"<p>Dzień dobry,</p><p>{esc(intro)}</p><p>"
            + "<br>".join(esc(line) for line in lines) + "</p><p>Załączniki:</p><ul>"
            + "".join(f"<li>{esc(n)}</li>" for n in names) + "</ul>")
    return {"agency": agency, "to": to, "cc": cc, "subject": subject, "text": text, "html": html,
            "attachments": attachments, "warnings": _warnings(db, batch, invoices, symbols_xlsx) + sadue_warnings}


@router.get("/invoice-batches/{batch_id}/agency-mail/preview")
def agency_mail_preview(batch_id: int, db: Session = Depends(get_db), user: User = docs_senders) -> dict:
    """Podgląd szkicu: dokładnie to, co trafi do .eml, plus ostrzeżenia — bez wpisu w audycie."""
    mail = _mail(db, _get_batch(db, batch_id, user), user)
    return {"to": mail["to"], "cc": mail["cc"], "subject": mail["subject"], "body": mail["text"],
            "agency": mail["agency"].name, "warnings": mail["warnings"],
            # ref > 0 = dokument z paczki (PDF części), ref < 0 = załącznik kontenera (−id)
            "attachments": [{"name": name, "size": len(data), "kind": kind,
                             "job_id": ref if ref and ref > 0 else None,
                             "attachment_id": -ref if ref and ref < 0 else None}
                            for name, data, _, kind, ref in mail["attachments"]]}


@router.get("/invoice-batches/{batch_id}/symbols.xlsx")
def agency_symbols_xlsx(batch_id: int, db: Session = Depends(get_db), user: User = docs_senders):
    """Kartoteka symboli do obejrzenia przed wysyłką (ta sama co w mailu)."""
    batch = _get_batch(db, batch_id, user)
    invoices = [job for job in batch.jobs
                if job.doc_kind in INVOICE_LIKE_KINDS and job.status == InvoiceJobStatus.confirmed]
    name = re.sub(r"[^A-Za-z0-9_-]", "_", batch.container.container_no or "")
    return Response(_symbols(db, batch, invoices, user), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="kartoteka_symboli_{name}.xlsx"'})


@router.get("/invoice-batches/{batch_id}/sadue.xml")
def agency_sadue_xml(batch_id: int, db: Session = Depends(get_db), user: User = docs_senders):
    """XML SADUE (WinSAD) z zatwierdzonych faktur — ten sam co w mailu; 409 = co poprawić."""
    batch = _get_batch(db, batch_id, user)
    try:
        content, warnings = sad_export.build(db, batch)
    except sad_export.SadExportError as exc:
        raise _conflict(str(exc)) from exc
    audit.record(db, entity_type="containers", entity_id=batch.container_id, field="sadue_xml",
                 old_value=None, new_value=f"paczka {batch.id}", user=user,
                 note="pobrano XML SADUE z faktur" + (f" ({'; '.join(warnings)})" if warnings else ""))
    db.commit()
    name = re.sub(r"[^A-Za-z0-9_-]", "_", batch.container.container_no or "")
    return Response(content, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="SAD_{name}.xml"'})


@router.get("/invoice-batches/{batch_id}/agency-mail.eml")
def agency_mail_eml(batch_id: int, db: Session = Depends(get_db), user: User = docs_senders):
    batch = _get_batch(db, batch_id, user)
    container = batch.container
    mail = _mail(db, batch, user)
    attachments = [(name, data, ctype) for name, data, ctype, _, _ in mail["attachments"]]
    content = build_eml(mail["to"], mail["cc"], mail["subject"], mail["html"], mail["text"], attachments)

    # §4 pkt 24: ślad, KTÓRE dokumenty poszły (id — nazwy bywają takie same po podmianie)
    sent = ", ".join(f"{name} [{'dok' if ref > 0 else 'plik'} {abs(ref)}]" if ref else name
                     for name, _, _, _, ref in mail["attachments"])
    audit.record(db, entity_type="containers", entity_id=container.id, field="invoice_agency_mail",
                 old_value=None, new_value=mail["agency"].name, user=user,
                 note=f"przygotowano szkic maila do agencji (Do: {', '.join(mail['to'])}; "
                      f"DW: {', '.join(mail['cc']) or '—'}; pliki: {sent})")
    if container.document_status != DocumentStatus.WYSLANE:   # jak send-docs: obieg → WYSŁANE
        record_changes(db, container, {"document_status": DocumentStatus.WYSLANE}, user,
                       note="szkic maila do agencji z dokumentami")
    db.commit()
    # nagłówek HTTP: tylko bezpieczne znaki (cudzysłów/CRLF w numerze nie rozbiją nagłówka)
    filename = f"faktury_{re.sub(r'[^A-Za-z0-9_-]', '_', container.container_no or '')}.eml"
    return Response(content, media_type="message/rfc822",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})

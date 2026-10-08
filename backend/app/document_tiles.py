"""Kafelki dokumentów dostawy (spec 2026-10-01-kafelki-dokumentow): PI · CI ⇄ PL · BL ·
SAD-DRAFT → SAD-PZ → SAD-PW — stan zebrany z trzech źródeł bez wgrywania czegokolwiek drugi raz:
paczki faktur (InvoiceJob.doc_kind), załączniki z typem o kodzie kafelka, drafty SAD agencji.

Stan kafelka: none (brak) / present (jest) / ok (sprawdzony) / warn (niepewny, czeka) /
bad (sprzeczny, do poprawy). „Wymagany” zależy od etapu kontenera i statusu odprawy."""
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .audit import record
from .invoices.conformity import CONFLICT, OK, UNCERTAIN, job_conformity
from .invoices.splitter import is_bill_of_lading
from .models import (Attachment, AttachmentLink, Container, ContainerStatus, CustomsStatus, DocumentType,
                     InvoiceBatch, InvoiceDocKind, InvoiceJob, InvoiceJobStatus, Role, SadDraft,
                     SupplierDocProfile, User, customs_rank)

TILES = ("PI", "CI", "PL", "BL", "SAD_DRAFT", "SAD_PZ", "SAD_PW")
_KIND_TILE = {InvoiceDocKind.proforma: "PI", InvoiceDocKind.invoice: "CI",
              InvoiceDocKind.packing_list: "PL"}
_RANK = {"none": 0, "present": 1, "ok": 2, "warn": 3, "bad": 4}   # najgorszy wygrywa (poza none)

_STAGE = list(ContainerStatus)


def _from_stage(c: Container, status: ContainerStatus) -> bool:
    return _STAGE.index(ContainerStatus(c.status)) >= _STAGE.index(status)


def _customs_at_least(c: Container, status: CustomsStatus) -> bool:
    # REWIZJA = odprawa w toku po zgłoszeniu (customs_rank) — draft był, PZ/PW jeszcze nie
    return customs_rank(CustomsStatus(c.customs_status)) >= customs_rank(status)


# od kiedy brak kafelka jest „brakiem” (wcześniej — tylko szary); domyślnie wymagane wszystkie
_REQUIRED_FROM = {
    "PI": lambda c: _from_stage(c, ContainerStatus.W_PRODUKCJI),
    "CI": lambda c: _from_stage(c, ContainerStatus.W_TRANSPORCIE),
    "PL": lambda c: _from_stage(c, ContainerStatus.W_TRANSPORCIE),
    "BL": lambda c: _from_stage(c, ContainerStatus.W_TRANSPORCIE),
    "SAD_DRAFT": lambda c: _customs_at_least(c, CustomsStatus.DRAFT_WYSLANY),
    "SAD_PZ": lambda c: _customs_at_least(c, CustomsStatus.ODPRAWIONY),
    "SAD_PW": lambda c: _customs_at_least(c, CustomsStatus.ZWOLNIONY),
}


def required(c: Container, chosen=None) -> set[str]:
    """Kafelki wymagane na tym etapie; `chosen` = zestaw dostawcy (None = wszystkie, jak dotąd)."""
    return {code for code, reached in _REQUIRED_FROM.items()
            if (chosen is None or code in chosen) and reached(c)}


def supplier_required_docs(db: Session, supplier_ids) -> dict[int, list[str]]:
    """Zestawy wymaganych kafelków ustawione w profilu dostawcy (decyzja 16) — tylko nadpisane."""
    ids = {i for i in supplier_ids if i}
    rows = db.execute(select(SupplierDocProfile.supplier_id, SupplierDocProfile.required_docs)
                      .where(SupplierDocProfile.supplier_id.in_(ids))).all() if ids else []
    return {sid: docs for sid, docs in rows if docs is not None}


def required_codes(db: Session, c: Container) -> set[str]:
    """Jedno źródło „wymaganych”: zestaw dostawcy, a bez niego domyślne reguły etapu.
    Czytają je kafelki (pojedyncze i kolejka) i ostrzeżenie przy zmianie statusu."""
    return required(c, supplier_required_docs(db, [c.supplier_id]).get(c.supplier_id or 0))


def _job_state(db: Session, job: InvoiceJob, company_id: int) -> str:
    result = job_conformity(db, job, company_id)
    if result["status"] == CONFLICT:
        return "bad"
    if job.doc_kind == InvoiceDocKind.packing_list:
        return "ok" if result["status"] == OK else "present"
    confirmed = job.status == InvoiceJobStatus.confirmed
    if confirmed and (result["status"] == OK or (result["status"] == UNCERTAIN and result["ack"])):
        return "ok"
    return "warn"   # niezatwierdzona albo niepewna bez potwierdzenia


_DRAFT_STATE = {"accepted": "ok", "rejected": "bad", "pending": "warn"}


def container_tiles(db: Session, c: Container, visible=lambda a: True) -> dict:
    return tiles_bulk(db, [c], visible)[c.id]


def tiles_bulk(db: Session, containers: list[Container], visible=lambda a: True) -> dict[int, dict]:
    """Kafelki wielu kontenerów (kolejka): paczki, drafty i załączniki trzema zapytaniami na całą
    listę zamiast per kontener. Bramka zgodności (`job_conformity`) nadal liczona per dokument."""
    ids = [c.id for c in containers]
    batches = db.scalars(select(InvoiceBatch).options(selectinload(InvoiceBatch.jobs))
                         .where(InvoiceBatch.container_id.in_(ids))).all() if ids else []
    batch_container = {b.id: b.container_id for b in batches}
    drafts = db.scalars(select(SadDraft).options(selectinload(SadDraft.attachment))
                        .where(SadDraft.batch_id.in_(batch_container))
                        .order_by(SadDraft.created_at)).all() if batches else []
    # pliki własne i wspólne (AttachmentLink, decyzja 24) — jedno zapytanie o powiązania
    links: dict[int, set[int]] = {}
    for att_id, cid in (db.execute(select(AttachmentLink.attachment_id, AttachmentLink.container_id)
                                   .where(AttachmentLink.container_id.in_(ids))).all() if ids else []):
        links.setdefault(att_id, set()).add(cid)
    attachments = db.scalars(select(Attachment).options(selectinload(Attachment.document_type))
                             .join(DocumentType, Attachment.document_type_id == DocumentType.id)
                             .where(Attachment.container_id.in_(ids) | Attachment.id.in_(links),
                                    DocumentType.tile_code.is_not(None))
                             .order_by(Attachment.created_at)).all() if ids else []
    chosen = supplier_required_docs(db, [c.supplier_id for c in containers])
    return {c.id: _tiles(db, c, required(c, chosen.get(c.supplier_id or 0)), [b for b in batches if b.container_id == c.id],
                         [d for d in drafts if batch_container[d.batch_id] == c.id],
                         [a for a in attachments
                          if a.container_id == c.id or c.id in links.get(a.id, ())], visible)
            for c in containers}


def _tiles(db: Session, c: Container, need: set[str], batches, drafts, attachments, visible) -> dict:
    files: dict[str, list[dict]] = {code: [] for code in TILES}
    state: dict[str, str] = {code: "none" for code in TILES}

    def add(code: str, file: dict, st: str) -> None:
        files[code].append(file)
        if _RANK[st] > _RANK[state[code]]:
            state[code] = st

    for batch in batches:
        for job in batch.jobs:
            if job.doc_kind == InvoiceDocKind.other and is_bill_of_lading(job.text_excerpt):
                add("BL", {"source": "invoice", "id": job.id, "name": job.filename,
                           "filename": job.filename, "created_at": job.created_at,
                           "url": f"/api/invoice-jobs/{job.id}/pdf"}, "present")
                continue
            code = _KIND_TILE.get(job.doc_kind)
            if code is None or job.status in (InvoiceJobStatus.ignored, InvoiceJobStatus.uploaded):
                continue
            st = "warn" if job.status == InvoiceJobStatus.error else _job_state(db, job, c.company_id)
            add(code, {"source": "invoice", "id": job.id, "name": job.invoice_number or job.filename,
                       "filename": job.filename, "created_at": job.created_at,
                       "url": f"/api/invoice-jobs/{job.id}/pdf"}, st)

    draft_attachments = {d.attachment_id for d in drafts}
    for d in drafts:
        # stan = najnowsza wersja (starsze odrzucone nie barwią kafelka na czerwono)
        st = _DRAFT_STATE.get(d.decision, "warn") if d is drafts[-1] else "present"
        add("SAD_DRAFT", {"source": "sad_draft", "id": d.id, "name": f"v{d.version}",
                          "filename": d.attachment.filename if d.attachment else "",
                          "created_at": d.created_at, "url": f"/api/attachments/{d.attachment_id}/download"}, st)

    for a in attachments:
        code = a.document_type.tile_code if a.document_type else None   # join gwarantuje typ
        if code not in files or a.id in draft_attachments or not visible(a):
            continue
        add(code, {"source": "attachment", "id": a.id, "name": a.filename, "filename": a.filename,
                   "created_at": a.created_at, "url": f"/api/attachments/{a.id}/download"}, "present")

    tiles = [{"code": code, "state": state[code], "required": code in need,
              "files": sorted(files[code], key=lambda f: f["created_at"], reverse=True)}
             for code in TILES]
    missing = [t["code"] for t in tiles if t["required"] and t["state"] == "none"]
    loaded = sum(1 for t in tiles if t["state"] != "none")
    return {"tiles": tiles, "loaded": loaded, "total": len(TILES), "missing": missing}


# role bez wglądu w część obiegu (spedytor: zero dokumentów celnych i handlowych, magazyn: bez
# faktur i SAD) — kafelki puste (routers/document_tiles), ostrzeżenie bez tych kodów
FORWARDER_HIDDEN_TILES = ("SAD_", "PI", "CI", "PL")
WAREHOUSE_HIDDEN_TILES = ("SAD_", "PI", "CI")
_HIDDEN = {Role.forwarder: FORWARDER_HIDDEN_TILES, Role.warehouse: WAREHOUSE_HIDDEN_TILES}
# decyzja 9: zmiana statusu przy brakach nie jest blokowana — ostrzeżenie + wpis w historii
WARN_CUSTOMS = (CustomsStatus.ODPRAWIONY, CustomsStatus.ZWOLNIONY)
WARN_STATUS = (ContainerStatus.DOSTARCZONY,)


def missing_docs_warning(db: Session, c: Container, user: User, label: str) -> str | None:
    """Braki wymaganych kafelków po zmianie statusu na `label` → wpis audytu
    `docs_missing_on_status` i tekst ostrzeżenia (bez kodów, których rola nie widzi)."""
    missing = container_tiles(db, c)["missing"]
    if not missing:
        return None
    note = f"Braki: {', '.join(missing)}"
    record(db, entity_type="containers", entity_id=c.id, field="docs_missing_on_status",
           old_value=None, new_value=", ".join(missing), user=user, note=f"{note} (status {label})")
    shown = [m for m in missing if not m.startswith(_HIDDEN.get(user.role, ()))]
    return f"Status {label} zapisany mimo braków. Braki: {', '.join(shown)}" if shown else None


# automat (spec, PR 5): wgrany SAD po odprawie / zwolnienie przesuwa status odprawy — tylko do przodu
_SAD_STATUS = {"SAD_PZ": CustomsStatus.ODPRAWIONY, "SAD_PW": CustomsStatus.ZWOLNIONY}


def sad_customs_target(c: Container, document_type: DocumentType | None) -> CustomsStatus | None:
    """Status odprawy po wgraniu SAD-PZ (ODPRAWIONY) / SAD-PW (ZWOLNIONY) albo None, gdy
    kontener jest już dalej (np. ROZLICZONY) albo dokument nie jest SAD-em z kafelka."""
    target = _SAD_STATUS.get(document_type.tile_code or "") if document_type else None
    if target is None or customs_rank(target) <= customs_rank(CustomsStatus(c.customs_status)):
        return None
    return target

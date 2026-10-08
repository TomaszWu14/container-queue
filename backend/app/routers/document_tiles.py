"""Kafelki dokumentów dostawy (spec 2026-10-01-kafelki-dokumentow) + podgląd PDF dokumentu
z paczki faktur (klik w kafelek CI / PI / PL)."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import PurchasingReaders as purchasing_readers
from ..deps import Viewer as viewer
from ..deps import forwarder_may_see, get_scoped, scope_containers
from ..document_tiles import (FORWARDER_HIDDEN_TILES, WAREHOUSE_HIDDEN_TILES, container_tiles,
                              tiles_bulk)
from ..models import Container, IntakeBatch, IntakeItem, InvoiceJob, Role, User
from .containers import get_container_checked
from .forwarding_files import uploads_dir

router = APIRouter(prefix="/api", tags=["dokumenty"])

# role z dostępem do modułu faktur — pozostali widzą stan kafelka CI/PI/PL, ale bez linku do pliku
_INVOICE_READERS = (Role.admin, Role.logistics, Role.purchasing)


@router.get("/containers/{container_id}/document-tiles")
def document_tiles(container_id: int, db: Session = Depends(get_db), user: User = viewer) -> dict:
    container = get_container_checked(db, container_id, user)
    return _for_role(container_tiles(db, container, visible=lambda a: forwarder_may_see(a, user)), user)


def _for_role(result: dict, user: User) -> dict:
    if user.role == Role.forwarder:
        _blank_forwarder_tiles(result)
    elif user.role == Role.warehouse:
        # spec 2026-10-06 decyzja 25 / §4 pkt 4: magazyn tylko PL, CMR, BL, awizo — bez faktur,
        # proform i obiegu SAD (wcześniej widział numery faktur i stan draftów agencji)
        _blank_forwarder_tiles(result, WAREHOUSE_HIDDEN_TILES)
    if user.role not in _INVOICE_READERS:
        for tile in result["tiles"]:
            for file in tile["files"]:
                if file["source"] == "invoice":
                    file["url"] = None
    return result


BULK_MAX = 500
_MINI = ("PI", "CI", "PL", "BL")
_SAD_ORDER = ("SAD_PW", "SAD_PZ", "SAD_DRAFT")   # najdalszy etap obiegu SAD wygrywa


@router.get("/document-tiles")
def document_tiles_bulk(ids: str, db: Session = Depends(get_db), user: User = viewer) -> dict:
    """Mini-kafelki kolejki (spec 2026-10-06 decyzja 28): PI·CI·PL·BL·SAD + braki + liczba części
    czekających w poczekalni — jedno żądanie na listę (do BULK_MAX id). Id spoza zakresu
    użytkownika są pomijane bez błędu; widoczność per rola jak w kafelkach pojedynczego kontenera."""
    id_list = list(dict.fromkeys(int(p) for p in ids.split(",") if p.strip().isdigit()))[:BULK_MAX]
    if not id_list:
        return {}
    containers = list(db.scalars(scope_containers(select(Container).where(Container.id.in_(id_list)), user)))
    bulk = tiles_bulk(db, containers, visible=lambda a: forwarder_may_see(a, user))
    pending = _intake_pending(db, [c.id for c in containers], user)
    return {c.id: _mini(_for_role(bulk[c.id], user), pending.get(c.id, 0)) for c in containers}


def _mini(result: dict, intake_pending: int) -> dict:
    state = {t["code"]: t["state"] for t in result["tiles"]}
    sad = next((state[c] for c in _SAD_ORDER if state[c] != "none"), "none")
    missing = [c for c in _MINI if c in result["missing"]]
    if any(c.startswith("SAD_") for c in result["missing"]):
        missing.append("SAD")
    return {"codes": {**{c: state[c] for c in _MINI}, "SAD": sad}, "missing": missing,
            "intake_pending": intake_pending}


def _intake_pending(db: Session, ids: list[int], user: User) -> dict[int, int]:
    """Części w otwartych wgraniach poczekalni — magazyn nie ma poczekalni (NonWarehouseViewers),
    spedytor liczy tylko własne wgrania (may_see_intake)."""
    if not ids or user.role == Role.warehouse:
        return {}
    query = (select(IntakeBatch.container_id, func.count(IntakeItem.id))
             .join(IntakeItem, IntakeItem.batch_id == IntakeBatch.id)
             .where(IntakeBatch.container_id.in_(ids), IntakeBatch.status == "pending")
             .group_by(IntakeBatch.container_id))
    if user.role == Role.forwarder:
        query = query.where(IntakeBatch.created_by_id == user.id)
    return {cid: n for cid, n in db.execute(query).all() if cid is not None}


def _blank_forwarder_tiles(result: dict, hidden: tuple[str, ...] = FORWARDER_HIDDEN_TILES) -> None:
    """Spedytor nie widzi obiegu odprawy (decyzja 2026-09-28) ani dokumentów handlowych:
    kafelki SAD i PI/CI/PL zawsze puste — stan/„wymagany”/pliki zdradzałyby status odprawy,
    drafty agencji, numery faktur. Kafelki zostają (UI rysuje stały zestaw), tylko bez treści."""
    for tile in result["tiles"]:
        if tile["code"].startswith(hidden):
            tile.update(state="none", required=False, files=[])
        # B/L wycięty z paczki faktur: nazwa pliku zestawu zdradza numer faktury
        tile["files"] = [f for f in tile["files"] if f["source"] != "invoice"]
    result["missing"] = [c for c in result["missing"] if not c.startswith(hidden)]
    result["loaded"] = sum(1 for t in result["tiles"] if t["state"] != "none")


@router.get("/invoice-jobs/{job_id}/pdf")
def invoice_job_pdf(job_id: int, db: Session = Depends(get_db), user: User = purchasing_readers):
    """Część PDF dokumentu z paczki faktur (po cięciu pypdf) — podgląd w przeglądarce."""
    job = get_scoped(db, InvoiceJob, job_id, user)
    path = uploads_dir() / job.stored_name
    if not job.stored_name or not path.is_file():
        raise HTTPException(status.HTTP_410_GONE, "Plik został usunięty z dysku.")
    return FileResponse(path, filename=job.filename, media_type="application/pdf",
                        content_disposition_type="inline")

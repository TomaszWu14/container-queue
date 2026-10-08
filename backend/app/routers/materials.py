"""Master data materiałów (REF → nazwa PL, CN, SENT, jm) — słownik globalny dla grupy
z nadpisaniami per spółka. Zasila dopasowanie pozycji faktur (app/invoices/matching).

Zapis = tylko admin (jak inne słowniki). Odczyt dla ról pracujących z fakturami
(admin, logistyka, zakupy) — spółka zakupowa widzi wartości globalne + własne nadpisania,
nie cudzych spółek.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..database import get_db
from ..deps import AdminOnly as admins
from ..deps import PurchasingReaders as readers
from ..deps import visible_overrides
from ..invoices import master_import, ml
from ..invoices.uom import normalize_ref
from ..models import Company, Material, MaterialOverride, User, utcnow
from ..schemas import (
    MaterialImportOut,
    MaterialIn,
    MaterialOut,
    MaterialOverrideIn,
    MaterialOverrideOut,
    MlStatsOut,
)
from .forwarding import read_upload_capped

router = APIRouter(prefix="/api/materials", tags=["materiały"])
logger = logging.getLogger(__name__)



def _out(material: Material, user: User) -> MaterialOut:
    out = MaterialOut.model_validate(material)
    # izolacja per spółka centralnie w deps.py (jak scope_containers) — nie tu
    out.overrides = [MaterialOverrideOut.model_validate(o) for o in visible_overrides(material, user)]
    return out


@router.get("", response_model=list[MaterialOut])
def list_materials(q: str = Query(default="", max_length=120),
                   limit: int = Query(default=200, ge=1, le=1000),
                   include_inactive: bool = False,
                   db: Session = Depends(get_db), user: User = readers):
    query = select(Material).order_by(Material.ref_code).limit(limit)
    if not include_inactive:
        query = query.where(Material.is_active)
    if q.strip():
        like = f"%{q.strip()}%"
        conditions = [Material.ref_code.ilike(like), Material.name_pl.ilike(like)]
        norm = normalize_ref(q)
        if norm:   # „-” czy „/” normalizuje się do pustego → LIKE '%%' dopasowałby wszystko
            conditions.append(Material.ref_norm.like(f"%{norm}%"))
        query = query.where(or_(*conditions))
    return [_out(m, user) for m in db.scalars(query).all()]


@router.get("/count")
def count_materials(db: Session = Depends(get_db), user: User = readers):
    """Aktywne materiały — tyle, ile widzi lista i dopasowanie faktur."""
    return {"count": db.scalar(select(func.count()).select_from(Material)
                               .where(Material.is_active)) or 0}


@router.get("/ml/stats", response_model=MlStatsOut)
def ml_stats(user: User = readers):
    return MlStatsOut(**ml.stats())


@router.post("/ml/train", response_model=MlStatsOut)
def ml_train(db: Session = Depends(get_db), user: User = admins):
    """Trening modeli ML z bazy (materiały, zatwierdzone pozycje, teksty dokumentów).
    Pipeline dotrenowuje po każdym zatwierdzeniu; ręcznie — np. po imporcie master daty."""
    stats = ml.train(db)
    audit.record(db, entity_type="materials", entity_id=0, field="ml_train", old_value=None,
                 new_value=f"{stats['ref_materials']} materiałów / {stats['ref_examples']} przykładów",
                 user=user)
    db.commit()
    return MlStatsOut(**stats)


@router.post("/import", response_model=MaterialImportOut)
def import_materials(file: UploadFile, dry_run: bool = Query(default=True),
                           db: Session = Depends(get_db), user: User = admins):
    """Import xlsx (szablon master daty: nagłówek 1- lub 2-wierszowy z bannerem poziomów).
    Upsert po ref_code; dry_run pokazuje liczniki bez zapisu."""
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Wymagany plik .xlsx.")
    content = read_upload_capped(file, settings.max_upload_mb, "Plik master daty")
    # parsowanie 25 MB xlsx + upsert tysięcy wierszy + trening TF-IDF to CPU — poza event loopem
    counts = _import_and_train(db, content, dry_run, user, file.filename)
    return MaterialImportOut(dry_run=dry_run, counts=counts)


def _import_and_train(db: Session, content: bytes, dry_run: bool, user: User,
                      filename: str | None) -> dict:
    try:
        rows = master_import.load_xlsx_rows(content)
    except Exception as exc:  # noqa: BLE001 — uszkodzony xlsx to błąd użytkownika, nie 500
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie udało się odczytać arkusza.") from exc
    records = master_import.parse_workbook_rows(rows)
    if not records:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie znaleziono kolumny REF (ref_code) ani wierszy z materiałami.")
    counts = master_import.import_records(db, records, dry_run=dry_run)
    if dry_run:
        db.rollback()
        return counts
    audit.record(db, entity_type="materials", entity_id=0, field="import", old_value=None,
                 new_value=f"{counts['new']} nowych / {counts['updated']} zaktualizowanych",
                 user=user, note=f"import master daty ({filename})")
    db.commit()
    ml.schedule_training()   # nowe materiały = nowy indeks podobieństwa
    return counts


def _get(db: Session, material_id: int) -> Material:
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono materiału.")
    return material


@router.patch("/{material_id}", response_model=MaterialOut)
def update_material(material_id: int, body: MaterialIn,
                    db: Session = Depends(get_db), user: User = admins):
    material = _get(db, material_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Brak pól do zmiany.")
    audit.record_changes(db, material, changes, user)
    material.updated_at = utcnow()
    db.commit()
    return _out(material, user)


@router.put("/{material_id}/override", response_model=MaterialOut)
def set_override(material_id: int, body: MaterialOverrideIn,
                 db: Session = Depends(get_db), user: User = admins):
    """Nadpisanie pól dla spółki; komplet pustych pól = usunięcie nadpisania."""
    material = _get(db, material_id)
    if not db.get(Company, body.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spółki.")
    override = next((o for o in material.overrides if o.company_id == body.company_id), None)
    values = body.model_dump(exclude={"company_id"})
    empty = not any(v for v in values.values() if v is not None and v != "") and body.sent is None
    if empty:
        if override is not None:
            db.delete(override)
    else:
        if override is None:
            override = MaterialOverride(material_id=material.id, company_id=body.company_id)
            db.add(override)
        for key, value in values.items():
            setattr(override, key, value)
    audit.record(db, entity_type="materials", entity_id=material.id, field="override",
                 old_value=None, new_value=f"spółka {body.company_id}: "
                 + ("usunięto" if empty else str({k: v for k, v in values.items() if v not in ("", None)})),
                 user=user)
    db.commit()
    db.refresh(material)
    return _out(material, user)

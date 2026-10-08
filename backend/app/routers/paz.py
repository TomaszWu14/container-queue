"""Słownik PAZ (sztuk na paletę per produkt): CRUD + import xlsx/csv."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select

from ..audit import record, record_changes
from ..config import settings
from ..database import get_db
from ..deps import GlobalDataEditors as global_editors
from ..deps import StaffReaders as staff
from ..models import ProductPaz, User, utcnow
from ..schemas import PazIn, PazOut
from ..tabular import XLSX_EXT, normalize_header, read_rows, to_float
from .forwarding_files import read_upload_capped

router = APIRouter(prefix="/api/paz", tags=["wywolania-dlt"])


@router.get("", response_model=list[PazOut])
def list_paz(user: User = staff, db=Depends(get_db)):
    return list(db.scalars(select(ProductPaz).order_by(ProductPaz.produkt)))


def _upsert(db, produkt: str, sztuk: float, user: User, note: str = "") -> ProductPaz:
    row = db.scalar(select(ProductPaz).where(ProductPaz.produkt == produkt))
    if row is None:
        row = ProductPaz(produkt=produkt, sztuk_na_palete=sztuk)
        db.add(row)
        db.flush()
        record(db, entity_type=ProductPaz.__tablename__, entity_id=row.id, field="created",
               old_value=None, new_value=f"{produkt}: {float(sztuk)}", user=user, note=note)
    else:
        record_changes(db, row, {"sztuk_na_palete": sztuk}, user, note=note or produkt)
        row.updated_at = utcnow()
    return row


@router.post("", response_model=PazOut, status_code=201)
def upsert_paz(body: PazIn, user: User = global_editors, db=Depends(get_db)):
    row = _upsert(db, body.produkt, body.sztuk_na_palete, user)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{paz_id}", status_code=204)
def delete_paz(paz_id: int, user: User = global_editors, db=Depends(get_db)):
    row = db.get(ProductPaz, paz_id)
    if row is None:
        raise HTTPException(404, "Nie znaleziono")
    record(db, entity_type=ProductPaz.__tablename__, entity_id=row.id, field="delete",
           old_value=f"{row.produkt}: {row.sztuk_na_palete}", new_value=None, user=user)
    db.delete(row)
    db.commit()


@router.post("/import")
def import_paz(file: UploadFile, user: User = global_editors, db=Depends(get_db)):
    """Import z csv/xlsx — kolumny 'produkt' i 'sztuk_na_palete' (po nagłówku)."""
    name = file.filename or ""
    if not name.lower().endswith((".csv", *XLSX_EXT)):
        raise HTTPException(400, "Obsługiwane formaty: .csv, .xlsx")
    table = read_rows(read_upload_capped(file, settings.max_upload_mb, "Plik PAZ"), name)
    header = [normalize_header(h) for h in (table[0] if table else [])]
    try:
        pi, si = header.index("produkt"), header.index("sztuk_na_palete")
    except ValueError:
        raise HTTPException(400, "Brak kolumn 'produkt'/'sztuk_na_palete'") from None
    rows = [(r[pi] if pi < len(r) else None, r[si] if si < len(r) else None) for r in table[1:]]
    count = 0
    skipped: list[dict] = []
    for i, (produkt, sztuk) in enumerate(rows, start=2):  # +1 nagłówek, +1 licząc od 1
        if not produkt or sztuk in (None, ""):
            skipped.append({"row": i, "produkt": str(produkt or ""), "reason": "brak danych"})
            continue
        val = to_float(sztuk)
        if val is None:
            skipped.append({"row": i, "produkt": str(produkt), "reason": f"nieliczbowa wartość: {sztuk}"})
            continue
        if val <= 0:
            skipped.append({"row": i, "produkt": str(produkt), "reason": "wartość ≤ 0"})
            continue
        _upsert(db, str(produkt).strip(), val, user, note=f"import {name}")
        count += 1
    db.commit()
    return {"imported": count, "skipped": skipped}

"""Słownik mapowań indeksów dostawcy: kod artykułu dostawcy → nasz ref_code.

Ma pierwszeństwo przy dopasowaniu pozycji faktury (invoices/matching.resolve_supplier_ref),
zanim zadziałają reguły REF i ML. Zarządza admin/logistyk/zakupy w granicach swoich spółek;
zakres firmowy egzekwują deps (get_company_by_code / get_scoped / scope_company).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record, record_changes
from ..database import get_db
from ..deps import PurchasingReaders as manage
from ..deps import StaffReaders as staff
from ..deps import get_company_by_code, get_scoped, scope_company
from ..models import SupplierMaterialMap, User, utcnow
from ..schemas import SupplierMaterialMapIn, SupplierMaterialMapOut

router = APIRouter(prefix="/api/supplier-material-maps", tags=["zakupy"])



@router.get("", response_model=list[SupplierMaterialMapOut])
def list_maps(company_code: str | None = Query(default=None),
              supplier_id: int | None = Query(default=None),
              q: str | None = Query(default=None, max_length=120),
              db: Session = Depends(get_db), user: User = staff):
    """Mapowania w zasięgu użytkownika; opcjonalny filtr spółki/dostawcy/frazy (kod lub ref)."""
    query = select(SupplierMaterialMap)
    if company_code is not None:
        company = get_company_by_code(db, user, company_code)
        query = query.where(SupplierMaterialMap.company_id == company.id)
    else:
        query = scope_company(query, SupplierMaterialMap.company_id, user)
    if supplier_id is not None:
        query = query.where(SupplierMaterialMap.supplier_id == supplier_id)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(SupplierMaterialMap.supplier_code.ilike(pattern)
                            | SupplierMaterialMap.ref_code.ilike(pattern))
    rows = db.scalars(query).all()
    rows.sort(key=lambda m: (m.supplier_id, m.supplier_code))
    return rows


@router.post("", response_model=SupplierMaterialMapOut, status_code=status.HTTP_201_CREATED)
def create_map(body: SupplierMaterialMapIn, db: Session = Depends(get_db), user: User = manage):
    """Nowe mapowanie; ten sam (spółka, dostawca, kod) = aktualizacja ref_code (upsert)."""
    if not body.company_code or not body.supplier_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Wymagane: company_code i supplier_id.")
    company = get_company_by_code(db, user, body.company_code)
    code, ref = body.supplier_code.strip(), body.ref_code.strip()
    if not code or not ref:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Kod dostawcy i ref_code są wymagane.")
    row = db.scalar(select(SupplierMaterialMap).where(
        SupplierMaterialMap.company_id == company.id,
        SupplierMaterialMap.supplier_id == body.supplier_id,
        SupplierMaterialMap.supplier_code == code))
    if row:
        record_changes(db, row, {"ref_code": ref, "note": body.note or ""}, user, note=code)
        row.updated_at = utcnow()
    else:
        row = SupplierMaterialMap(company_id=company.id, supplier_id=body.supplier_id,
                                  supplier_code=code, ref_code=ref, note=body.note or "")
        db.add(row)
        db.flush()
        record(db, entity_type=SupplierMaterialMap.__tablename__, entity_id=row.id,
               field="created", old_value=None, new_value=f"{code} → {ref}", user=user,
               note=f"dostawca {body.supplier_id}")
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{map_id}", response_model=SupplierMaterialMapOut)
def update_map(map_id: int, body: SupplierMaterialMapIn,
               db: Session = Depends(get_db), user: User = manage):
    """Zmiana ref_code / kodu / notatki (w granicach spółki wpisu)."""
    row = get_scoped(db, SupplierMaterialMap, map_id, user)
    changes = {"note": body.note or ""}
    if body.ref_code.strip():
        changes["ref_code"] = body.ref_code.strip()
    if body.supplier_code.strip():
        changes["supplier_code"] = body.supplier_code.strip()
    record_changes(db, row, changes, user, note=row.supplier_code)
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{map_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_map(map_id: int, db: Session = Depends(get_db), user: User = manage):
    """Usunięcie mapowania (w granicach spółki wpisu)."""
    row = get_scoped(db, SupplierMaterialMap, map_id, user)
    record(db, entity_type=SupplierMaterialMap.__tablename__, entity_id=row.id, field="delete",
           old_value=f"{row.supplier_code} → {row.ref_code}", new_value=None, user=user,
           note=f"dostawca {row.supplier_id}")
    db.delete(row)
    db.commit()

"""Profil dokumentów dostawcy (CI + packing list) — odczyt i zapis (etap 1 spec
2026-09-24-profil-dostawcy). Scoping dostawcy jak słownik (get_scoped);
edycja admin (jak słownik dostawców), odczyt admin/logistyka/zakupy."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..audit import record
from ..database import get_db
from ..deps import AdminOnly as admins
from ..deps import PurchasingReaders as readers
from ..deps import get_scoped
from ..models import Supplier, SupplierDocProfile, User
from ..schemas.supplier_profiles import RequiredDocsIn, SupplierDocProfileIn, SupplierDocProfileOut

router = APIRouter(prefix="/api", tags=["profil dostawcy"])


@router.get("/suppliers/{supplier_id}/doc-profile", response_model=SupplierDocProfileOut)
def get_profile(supplier_id: int, db: Session = Depends(get_db), user: User = readers):
    supplier = get_scoped(db, Supplier, supplier_id, user)
    if supplier.doc_profile:
        return supplier.doc_profile
    return SupplierDocProfileOut(supplier_id=supplier.id)


@router.put("/suppliers/{supplier_id}/doc-profile", response_model=SupplierDocProfileOut)
def put_profile(supplier_id: int, body: SupplierDocProfileIn, db: Session = Depends(get_db),
                user: User = admins):
    supplier = get_scoped(db, Supplier, supplier_id, user)
    profile = supplier.doc_profile or SupplierDocProfile(supplier_id=supplier.id)
    old_status = profile.status if profile.id else None
    for field, value in body.model_dump().items():
        setattr(profile, field, value)
    db.add(profile)
    record(db, entity_type="suppliers", entity_id=supplier.id, field="doc_profile",
           old_value=old_status, new_value=profile.status, user=user)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/suppliers/{supplier_id}/required-docs", response_model=SupplierDocProfileOut)
def put_required_docs(supplier_id: int, body: RequiredDocsIn, db: Session = Depends(get_db),
                      user: User = admins):
    """Wymagane dokumenty dostawcy (spec 2026-10-06 decyzja 16) — czytają je kafelki i ostrzeżenie
    przy zmianie statusu (document_tiles.required_codes). `codes: null` = domyślny zestaw."""
    supplier = get_scoped(db, Supplier, supplier_id, user)
    profile = supplier.doc_profile or SupplierDocProfile(supplier_id=supplier.id)
    old = profile.required_docs
    profile.required_docs = body.codes
    db.add(profile)
    record(db, entity_type="suppliers", entity_id=supplier.id, field="required_docs",
           old_value=", ".join(old) if old is not None else None,
           new_value=", ".join(body.codes) if body.codes is not None else None, user=user)
    db.commit()
    db.refresh(profile)
    return profile

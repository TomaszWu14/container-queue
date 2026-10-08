"""Kreator profilu dostawcy (etap 4): próbki PDF (upload/usunięcie — lista jest w
GET /doc-profile), podgląd tabeli z próbki i test profilu na próbkach bez zapisu faktur.
Edycja: admin (jak słownik dostawców); odczyt: admin/logistyka/zakupy. Scoping spółki: get_scoped."""
import pathlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from .. import supplier_profile_lab as lab
from ..audit import record
from ..config import settings
from ..database import get_db
from ..deps import AdminOnly as admins
from ..deps import PurchasingReaders as readers
from ..deps import get_scoped
from ..models import Supplier, SupplierDocProfile, SupplierDocSample, User
from ..models.enums import utcnow
from ..schemas.supplier_profiles import SampleOut, SupplierDocProfileIn
from .forwarding_files import commit_with_file, read_upload_capped, safe_filename, uploads_dir

router = APIRouter(prefix="/api/suppliers/{supplier_id}/doc-profile", tags=["profil dostawcy"])

MAX_SAMPLES = 10


def _sample(db: Session, supplier: Supplier, sample_id: int) -> SupplierDocSample:
    sample = db.get(SupplierDocSample, sample_id)
    if not sample or not supplier.doc_profile or sample.profile_id != supplier.doc_profile.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono próbki.")
    return sample


def _path(sample: SupplierDocSample) -> str:
    return str(uploads_dir() / sample.stored_path)


def _verdict(result: dict | None) -> str | None:
    """Wynik testu w audycie jako werdykt (pełny wynik zostaje w last_test próbki)."""
    return None if result is None else ("ok" if result.get("ok") else "błąd")


@router.post("/samples", response_model=SampleOut, status_code=201)
def upload_sample(supplier_id: int, file: UploadFile, db: Session = Depends(get_db),
                  user: User = admins):
    supplier = get_scoped(db, Supplier, supplier_id, user)
    if pathlib.Path(file.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Próbka musi być plikiem PDF.")
    profile = supplier.doc_profile or SupplierDocProfile(supplier_id=supplier.id)
    if len(profile.samples) >= MAX_SAMPLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Profil ma już {MAX_SAMPLES} próbek — usuń którąś.")
    content = read_upload_capped(file, settings.max_upload_mb, "Próbka")
    safe = safe_filename(file.filename, "probka.pdf")
    stored = f"profile{supplier.id}_{secrets.token_hex(8)}_{safe}"
    sample = SupplierDocSample(filename=safe, stored_path=stored)
    profile.samples.append(sample)
    db.add(profile)
    db.flush()
    record(db, entity_type=SupplierDocSample.__tablename__, entity_id=sample.id, field="created",
           old_value=None, new_value=safe, user=user, note=f"dostawca {supplier.name}")
    commit_with_file(db, uploads_dir() / stored, content)
    db.refresh(sample)
    return sample


@router.delete("/samples/{sample_id}", status_code=204)
def delete_sample(supplier_id: int, sample_id: int, db: Session = Depends(get_db),
                  user: User = admins):
    supplier = get_scoped(db, Supplier, supplier_id, user)
    sample = _sample(db, supplier, sample_id)
    path = uploads_dir() / sample.stored_path
    record(db, entity_type=SupplierDocSample.__tablename__, entity_id=sample.id, field="delete",
           old_value=sample.filename, new_value=None, user=user, note=f"dostawca {supplier.name}")
    db.delete(sample)
    db.commit()
    path.unlink(missing_ok=True)


@router.get("/samples/{sample_id}/preview")
def preview_sample(supplier_id: int, sample_id: int, kind: str = Query("ci", pattern="^(ci|pl)$"),
                   db: Session = Depends(get_db), user: User = readers):
    """Tabela z próbki (CI albo PL) do mapowania kolumn + podział stron."""
    supplier = get_scoped(db, Supplier, supplier_id, user)
    sample = _sample(db, supplier, sample_id)
    profile = supplier.doc_profile
    try:
        pages = lab.extractor.read_pages(_path(sample))
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie udało się odczytać PDF próbki.") from None
    parts = lab.split_pages(pages, profile.split_marker)
    role_map = profile.ci_map if kind == "ci" else profile.pl_map
    return {**lab.preview(pages, parts[kind], role_map),
            "pages": {k: [i + 1 for i in v] for k, v in parts.items()}}


@router.post("/test")
def test_profile(supplier_id: int, body: SupplierDocProfileIn, db: Session = Depends(get_db),
                 user: User = admins):
    """Test NIEZAPISANEGO stanu kreatora na wszystkich próbkach; wynik zapisany w próbkach
    (last_test) — faktury/partie nie powstają."""
    supplier = get_scoped(db, Supplier, supplier_id, user)
    samples = supplier.doc_profile.samples if supplier.doc_profile else []
    if not samples:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Najpierw wgraj próbkę PDF.")
    now = utcnow()
    results = []
    for sample in samples:
        before = sample.last_test
        sample.last_test = lab.run_test(db, supplier, body, _path(sample))
        sample.last_test_at = now
        record(db, entity_type=SupplierDocSample.__tablename__, entity_id=sample.id,
               field="last_test", old_value=_verdict(before), new_value=_verdict(sample.last_test),
               user=user, note=f"test profilu: {sample.filename}")
        results.append({"sample_id": sample.id, "filename": sample.filename, **sample.last_test})
    db.commit()
    return {"ok": all(r["ok"] for r in results), "results": results}

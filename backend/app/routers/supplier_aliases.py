"""Mapowanie nazw dostawców z pliku kolejki (Container.supplier_raw) na słownik przez aliasy.
Alias należy do spółki pliku kolejki (nazwa → dostawca w tej spółce). Import kolejki nie
tworzy dostawców — nazwy bez dopasowania trafiają na listę „Do zmapowania".

Tu też ekran „Do rozstrzygnięcia" kartoteki (spec 2026-09-25 §3): podgląd i scalenie dubli
kodu SAP oraz kasowanie kopii bez powiązań."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..deps import AdminOnly as admins
from ..deps import Editors as editors
from ..deps import (
    apply_company_code_filter,
    check_company_access,
    get_scoped,
    is_material_company,
    scope_containers,
    supplier_clause_for_company,
)
from ..models import Company, Container, Supplier, SupplierAlias, User, normalize_alias
from ..supplier_consolidation import apply_groups, delete_orphans, orphans_preview, proposal

router = APIRouter(prefix="/api/suppliers", tags=["słowniki"])


@router.get("/resolve")
def resolve_list(db: Session = Depends(get_db), user: User = admins):
    """„Do rozstrzygnięcia" (dry-run): grupy tego samego kodu SAP + kartoteka bez kodu SAP."""
    return proposal(db)


@router.post("/resolve/apply")
def resolve_apply(db: Session = Depends(get_db), user: User = admins):
    """Scala wszystkie grupy tego samego kodu SAP w jednej transakcji (audyt per scalenie).
    Pojedyncze decyzje: POST /{id}/merge, PATCH /{id} (nieaktywny), DELETE /{id}."""
    result = apply_groups(db, user)
    db.commit()
    return result


@router.get("/resolve/orphans")
def resolve_orphans(db: Session = Depends(get_db), user: User = admins):
    """Podgląd kopii bez żadnych powiązań (decyzja usera #2, 2026-09-25) — nic nie zmienia."""
    return orphans_preview(db)


@router.post("/resolve/orphans/delete")
def resolve_orphans_delete(db: Session = Depends(get_db), user: User = admins):
    """Kasuje wszystkie kopie bez powiązań w jednej transakcji (audyt zbiorczy)."""
    deleted = delete_orphans(db, user)
    db.commit()
    return {"deleted": deleted}


class AliasIn(BaseModel):
    alias: str = Field(min_length=1, max_length=160)
    # spółka pliku kolejki; domyślnie spółka nadawcy klienta (dostawca z kartoteki jej nie ma)
    company_id: int | None = None


def _alias_out(a: SupplierAlias) -> dict:
    return {"id": a.id, "alias": a.alias, "supplier_id": a.supplier_id}


@router.get("/unmapped")
def unmapped(company_code: str | None = None, db: Session = Depends(get_db),
             user: User = editors):
    """Nazwy z pliku bez dostawcy w słowniku (w zakresie usera), najczęstsze najpierw.
    `catalog` = spółka pracuje na materiałach Acme (mapujemy na kartotekę)."""
    n = func.count(Container.id)
    q = (select(Container.company_id, Container.supplier_raw, n)
         .where(Container.supplier_id.is_(None), Container.supplier_raw != "")
         .group_by(Container.company_id, Container.supplier_raw)
         .order_by(n.desc(), Container.supplier_raw))
    q = apply_company_code_filter(scope_containers(q, user), db, Container.company_id,
                                  company_code, None)
    catalog = {c.id: is_material_company(c) for c in db.scalars(select(Company))}
    return [{"name": name, "company_id": cid, "containers": cnt, "catalog": catalog.get(cid, False)}
            for cid, name, cnt in db.execute(q)]


@router.get("/{supplier_id}/aliases")
def list_aliases(supplier_id: int, db: Session = Depends(get_db), user: User = editors):
    get_scoped(db, Supplier, supplier_id, user)
    return [_alias_out(a) for a in db.scalars(select(SupplierAlias).where(
        SupplierAlias.supplier_id == supplier_id).order_by(SupplierAlias.alias))]


@router.post("/{supplier_id}/aliases", status_code=201)
def create_alias(supplier_id: int, body: AliasIn, db: Session = Depends(get_db),
                 user: User = editors):
    """Alias nazwy → dostawca w spółce pliku + przypięcie kontenerów tej spółki z tą nazwą
    bez dostawcy. Dostawca musi być do użycia w tej spółce (deps.supplier_clause_for_company)."""
    supplier = get_scoped(db, Supplier, supplier_id, user)
    company_id = body.company_id if body.company_id is not None else supplier.client_company_id
    if company_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Wskaż spółkę pliku kolejki (company_id).")
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spółki.")
    check_company_access(user, company.id)
    if db.scalar(select(Supplier.id).where(
            Supplier.id == supplier.id, supplier_clause_for_company(company))) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono dostawcy.")
    norm = normalize_alias(body.alias)
    if not norm:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pusta nazwa aliasu.")
    alias = db.scalar(select(SupplierAlias).where(
        SupplierAlias.company_id == company.id, SupplierAlias.alias_norm == norm))
    if alias and alias.supplier_id != supplier.id:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Ta nazwa jest już przypisana do innego dostawcy (id={alias.supplier_id}).")
    if not alias:
        alias = SupplierAlias(company_id=company.id, supplier_id=supplier.id,
                              alias=body.alias.strip(), alias_norm=norm)
        db.add(alias)
    # ponytail: normalizacja w Pythonie po kontenerach bez dostawcy (zwykle setki), kolumna
    # supplier_raw_norm z indeksem gdyby urosło
    rows = db.execute(select(Container.id, Container.supplier_raw).where(
        Container.company_id == company.id, Container.supplier_id.is_(None),
        Container.supplier_raw != "")).all()
    ids = [cid for cid, raw in rows if normalize_alias(raw) == norm]
    if ids:
        db.execute(update(Container).where(Container.id.in_(ids)).values(supplier_id=supplier.id))
    for cid in ids:
        audit.record(db, entity_type="containers", entity_id=cid, field="supplier_id",
                     old_value=None, new_value=str(supplier.id), user=user,
                     note=f"mapowanie nazwy z pliku: {alias.alias}")
    db.commit()
    return {"alias": _alias_out(alias), "assigned": len(ids)}


@router.delete("/aliases/{alias_id}", status_code=204)
def delete_alias(alias_id: int, db: Session = Depends(get_db), user: User = editors):
    """Usuwa alias (przyszłe importy tej nazwy wrócą na listę); kontenery już przypięte zostają."""
    alias = get_scoped(db, SupplierAlias, alias_id, user)
    audit.record(db, entity_type="supplier_aliases", entity_id=alias.id, field="delete",
                 old_value=alias.alias, new_value=None, user=user, note="usunięto alias dostawcy")
    db.delete(alias)
    db.commit()

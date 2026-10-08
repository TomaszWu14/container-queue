"""Scalanie dubli dostawców po przejściu na globalną kartotekę (spec 2026-09-25 §3, PR1).

Import LFA1 szedł dotąd do KAŻDEJ spółki, więc ten sam dostawca SAP istnieje w kartotece
kilka razy (dawne kopie Acme i Iberia). `proposal` = dry-run: grupy tego samego kodu
SAP („pewne") + aktywni w kartotece bez kodu SAP („do rozstrzygnięcia", z podpowiedzią po
nazwie). `apply_groups` scala grupy tą samą funkcją co ręczne „Scal z…" (merge_into), więc
przepina wszystkie FK. Wołają: ekran Master data → Dostawcy i scripts/consolidate_suppliers.py.

`orphans_preview`/`delete_orphans` (decyzje usera #2 i #8, ten sam dokument): masowe kasowanie
kopii nadawców spółek-klientów BEZ żadnych powiązań (tysiące kopii LFA1 w Borealis/Cobalt) — te same sprawdzenia
co pojedyncze DELETE dostawcy (dictionaries_merge.SUPPLIERS.refs), plus profil dokumentów
(„owned", nie w refs, ale realny rekord skonfigurowany ręcznie — nie kopia z importu).
"""
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import audit
from .models import (
    Company,
    Container,
    InvoiceBatch,
    Order,
    Supplier,
    SupplierDocProfile,
    User,
    normalize_alias,
)
from .routers.dictionaries_merge import SUPPLIERS, merge_into


def _usage(db: Session) -> dict[int, int]:
    """Kontenery + zamówienia + paczki faktur per dostawca (3 zapytania, nie N)."""
    out: dict[int, int] = defaultdict(int)
    for model in (Container, Order, InvoiceBatch):
        for supplier_id, count in db.execute(
                select(model.supplier_id, func.count()).where(model.supplier_id.is_not(None))
                .group_by(model.supplier_id)):
            out[supplier_id] += count
    return out


def _brief(s: Supplier, usage: dict[int, int]) -> dict:
    return {"id": s.id, "name": s.name, "sap_code": s.sap_code, "country": s.country,
            "is_active": s.is_active, "usage": usage.get(s.id, 0)}


def proposal(db: Session) -> dict:
    """Dry-run: nic nie zmienia."""
    usage = _usage(db)
    with_profile = set(db.scalars(select(SupplierDocProfile.supplier_id)))
    catalog = db.scalars(select(Supplier).where(Supplier.client_company_id.is_(None))
                         .order_by(Supplier.id)).all()
    by_code: dict[str, list[Supplier]] = defaultdict(list)
    for supplier in catalog:
        if supplier.sap_code:
            by_code[supplier.sap_code].append(supplier)

    def rank(s: Supplier) -> tuple:
        # zostaje: z profilem dokumentów > aktywny > najczęściej używany > najstarszy
        return (s.id in with_profile, s.is_active, usage.get(s.id, 0), -s.id)

    groups, leaders = [], {}
    for code, members in sorted(by_code.items()):
        target = max(members, key=rank)
        leaders[code] = target
        if len(members) > 1:
            # ≥2 profile dokumentów: scalenie skasowałoby profil duplikatu — tylko ręcznie
            # (decyzja usera #9); „Scal wszystkie" takie grupy pomija
            conflict = sum(s.id in with_profile for s in members) >= 2
            groups.append({"sap_code": code, "target": _brief(target, usage),
                           "sources": [_brief(s, usage) for s in members if s.id != target.id],
                           "profile_conflict": conflict})
    # podpowiedź po nazwie tylko jednoznaczna (ta sama nazwa pod dwoma kodami = „dubel w SAP")
    names = Counter(normalize_alias(t.name) for t in leaders.values())
    by_name = {normalize_alias(t.name): t for t in leaders.values()
               if names[normalize_alias(t.name)] == 1}
    unresolved = []
    for supplier in catalog:
        if supplier.sap_code or not supplier.is_active:
            continue
        hint = by_name.get(normalize_alias(supplier.name))
        unresolved.append({**_brief(supplier, usage),
                           "suggestion": _brief(hint, usage) if hint else None})
    return {"merge_groups": groups, "unresolved": unresolved}


def apply_groups(db: Session, user: User | None) -> dict:
    """Scala wszystkie grupy tego samego kodu SAP poza konfliktem profili (decyzja #9). Bez
    commit — transakcję domyka wołający (jedna transakcja: błąd w środku = nic nie zapisane)."""
    groups = [g for g in proposal(db)["merge_groups"] if not g["profile_conflict"]]
    merged = 0
    for group in groups:
        target = db.get(Supplier, group["target"]["id"])
        for source in group["sources"]:
            merge_into(db, SUPPLIERS, db.get(Supplier, source["id"]), target, user)
            merged += 1
    return {"groups": len(groups), "merged": merged}


def _referenced_supplier_ids(db: Session) -> set[int]:
    """Dostawcy z jakimkolwiek powiązaniem — te same pola co pojedyncze DELETE dostawcy
    (dictionaries_merge.SUPPLIERS.refs), plus profil dokumentów (owned, nie w refs)."""
    ids: set[int] = set()
    for model, column in SUPPLIERS.refs:
        col = getattr(model, column)
        ids |= set(db.scalars(select(col).distinct().where(col.is_not(None))))
    ids |= set(db.scalars(select(SupplierDocProfile.supplier_id).distinct()))
    return ids


def _orphans(db: Session) -> list[tuple[Supplier, str]]:
    """Kopie nadawców spółek-klientów bez żadnych powiązań (decyzja usera #8: kartoteka Acme
    — z kodem SAP i bez — nigdy masowo), z kodem spółki."""
    referenced = _referenced_supplier_ids(db)
    return [tuple(row) for row in db.execute(
        select(Supplier, Company.code)
        .join(Company, Company.id == Supplier.client_company_id)
        .where(Supplier.client_company_id.is_not(None), Supplier.id.not_in(referenced))
        .order_by(Supplier.id)).all()]


def orphans_preview(db: Session) -> dict:
    """Podgląd kopii bez żadnych powiązań, bez zmian w bazie."""
    rows = _orphans(db)
    by_company: dict[str, int] = defaultdict(int)
    for _, code in rows:
        by_company[code] += 1
    sample = [{"id": s.id, "name": s.name, "company_code": code} for s, code in rows[:50]]
    return {"count": len(rows), "by_company": dict(by_company), "sample": sample}


def delete_orphans(db: Session, user: User | None) -> int:
    """Usuwa wszystkie kopie bez powiązań w jednej transakcji (audyt zbiorczy). Bez commit —
    transakcję domyka wołający."""
    rows = _orphans(db)
    if not rows:
        return 0
    listing = "; ".join(f"{s.id} {s.name!r} SAP={s.sap_code or '-'} {code}" for s, code in rows)
    audit.record(db, entity_type="suppliers", entity_id=0, field="__orphans_deleted__",
                old_value=None, new_value=str(len(rows)), user=user,
                note=f"usunięto kopie bez powiązań: {listing}")
    for supplier, _ in rows:
        db.delete(supplier)
    return len(rows)

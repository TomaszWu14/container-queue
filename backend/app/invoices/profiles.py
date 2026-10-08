"""Profil dokumentów dostawcy w ekstrakcji (etap 2 spec 2026-09-24-profil-dostawcy):
które mapy kolumn CI/PL, jaki znacznik stron PL, czy kolumna REF to kod dostawcy, oraz
rozpoznanie dostawcy po słowach kluczowych. Przeniesione z repo compare
(supplier_profiles.detect_supplier / apply_column_mapping) na SQLAlchemy.

Kolejność map CI: aktywny profil → stare `Supplier.column_map` → auto-detekcja nagłówków.
Profil `draft` nie działa automatycznie (spec: „Błędy”)."""
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import supplier_clause_for_company
from ..models import Company, Supplier, SupplierDocProfile
from .extractor import COLUMN_ROLES, ROLE_ALIASES, parse_column_map


@dataclass
class DocProfile:
    ci_map: dict = field(default_factory=dict)
    pl_map: dict = field(default_factory=dict)
    ref_kind: str = "ours"           # ours | supplier (kod → SupplierMaterialMap)
    split_marker: str = ""
    source: str = "auto"             # active | column_map | auto — skąd mapa CI


def normalize_role_map(raw: dict | None) -> dict[str, list[str]]:
    """{rola: [aliasy]} z nazwami ról ekstraktora; nieznane role (i „skip”) pomijane."""
    out: dict[str, list[str]] = {}
    for role, aliases in (raw or {}).items():
        role = str(role).strip().lower()
        role = ROLE_ALIASES.get(role, role)
        if role not in COLUMN_ROLES:
            continue
        names = [aliases] if isinstance(aliases, str) else (aliases or [])
        clean = [a.strip() for a in names if isinstance(a, str) and a.strip()]
        if clean:
            out.setdefault(role, []).extend(clean)
    return out


def resolve(supplier: Supplier | None) -> DocProfile:
    legacy = parse_column_map(supplier.column_map) if supplier else {}
    profile = supplier.doc_profile if supplier else None
    if profile is not None and profile.status == "active":
        ci = normalize_role_map(profile.ci_map)
        return DocProfile(ci_map=ci or legacy, pl_map=normalize_role_map(profile.pl_map),
                          ref_kind=profile.ref_kind or "ours",
                          split_marker=(profile.split_marker or "").strip(),
                          source="active" if ci else ("column_map" if legacy else "auto"))
    return DocProfile(ci_map=legacy, source="column_map" if legacy else "auto")


def keyword_hits(text: str, keywords: list) -> int:
    """Ile słów kluczowych występuje w tekście jako całe słowo/fraza (bez rozróżniania
    wielkości liter). Granice przez lookaround, nie \\b — „ACME CO.” kończy się kropką."""
    low = (text or "").lower()
    return sum(1 for kw in keywords or [] if isinstance(kw, str) and kw.strip()
               and re.search(rf"(?<!\w){re.escape(kw.strip().lower())}(?!\w)", low))


def detect_supplier(db: Session, text: str, company_id: int | None) -> Supplier | None:
    """Dostawca do użycia w spółce z AKTYWNYM profilem o największej liczbie trafień słów
    kluczowych. Brak trafień albo remis na szczycie → None (operator wybiera ręcznie)."""
    if not (text or "").strip() or company_id is None:
        return None
    company = db.get(Company, company_id)
    if company is None:
        return None
    rows = db.execute(select(SupplierDocProfile.keywords, Supplier)
                      .join(Supplier, Supplier.id == SupplierDocProfile.supplier_id)
                      .where(SupplierDocProfile.status == "active", Supplier.is_active,
                             supplier_clause_for_company(company))).all()
    scored = sorted(((keyword_hits(text, kws), sup) for kws, sup in rows),
                    key=lambda pair: pair[0], reverse=True)
    if not scored or scored[0][0] == 0:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]

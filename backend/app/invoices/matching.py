"""Dopasowanie pozycji faktury do master daty materiałów (`Material` + nadpisania per
spółka) i ustalenie statusu: matched / ambiguous / unmatched. Deterministyczne, bez LLM.

Dopasowanie po REF z obsługą aliasów sufiksu (X → X1): dokładne trafienie, potem
kandydaci „prefiks + same cyfry”; jeden kandydat = matched, kilku = ambiguous (operator
rozstrzyga), zero = unmatched (puste pola, nie blokuje).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (InvoiceItem, InvoiceJob, InvoiceMatchStatus, Material,
                      SupplierMaterialMap, UomConversion)
from . import ml, uom
from .uom import normalize_ref

ENRICH_FIELDS = ("name_pl", "tariff_cn", "customs_code", "base_uom", "sent")


def effective(material: Material, company_id: int | None) -> dict:
    """Pola materiału z nadpisaniem spółki (puste pole / NULL = wartość globalna)."""
    view = {"ref_code": material.ref_code, "name_pl": material.name_pl,
            "tariff_cn": material.tariff_cn, "customs_code": material.customs_code,
            "base_uom": material.base_uom, "sent": bool(material.sent)}
    if company_id is None:
        return view
    for override in material.overrides:
        if override.company_id != company_id:
            continue
        for key in ("name_pl", "tariff_cn", "customs_code", "base_uom"):
            if getattr(override, key):
                view[key] = getattr(override, key)
        if override.sent is not None:
            view["sent"] = override.sent
    return view


def get_material(db: Session, ref) -> Material | None:
    ref = str(ref or "").strip()
    if not ref:
        return None
    material = db.scalar(select(Material).where(Material.ref_code == ref,
                                                Material.is_active))
    if material:
        return material
    norm = normalize_ref(ref)
    if not norm:
        return None
    return db.scalar(select(Material).where(Material.ref_norm == norm, Material.is_active)
                     .order_by(Material.id).limit(1))


def resolve_supplier_ref(db: Session, company_id: int | None, supplier_id: int | None,
                         raw_ref) -> str | None:
    """Nasz ref_code ze słownika mapowań indeksów dostawcy (kod artykułu → ref_code).
    Najwyższy priorytet: operator ustalił to na stałe. None = brak wpisu. `company_id=None`
    (test próbki profilu dostawcy z kartoteki — bez kontenera) = mapa dowolnej spółki."""
    code = str(raw_ref or "").strip()
    if not code or not supplier_id:
        return None
    query = select(SupplierMaterialMap.ref_code).where(
        SupplierMaterialMap.supplier_id == supplier_id,
        SupplierMaterialMap.supplier_code == code)
    if company_id is not None:
        query = query.where(SupplierMaterialMap.company_id == company_id)
    return db.scalar(query.order_by(SupplierMaterialMap.id).limit(1))


def find_candidates(db: Session, raw_ref) -> list[Material]:
    """Materiały, których ref_norm = norm + same cyfry: 'X' → {X, X1, X10}, ale NIE 'XYLO'."""
    norm = normalize_ref(raw_ref)
    if not norm:
        return []
    rows = db.scalars(select(Material).where(Material.ref_norm.like(norm + "%"),
                                             Material.is_active)
                      .order_by(Material.ref_code)).all()
    return [m for m in rows if (m.ref_norm[len(norm):] == "" or m.ref_norm[len(norm):].isdigit())]


def load_conversions(db: Session) -> list[dict]:
    out = []
    for rule in db.scalars(select(UomConversion)).all():
        try:
            factor = float(rule.factor)
        except (TypeError, ValueError):
            continue
        out.append({"ref_norm": rule.ref_norm, "unit_from": uom.canonical_unit(rule.unit_from),
                    "unit_to": uom.canonical_unit(rule.unit_to), "factor": factor})
    return out


def _enrich(item: InvoiceItem, view: dict, conversions: list[dict]) -> None:
    item.master_ref = view["ref_code"]
    item.name_pl = view["name_pl"]
    item.tariff_cn = view["tariff_cn"] or view["customs_code"]
    item.sent = bool(view["sent"])
    factor = uom.get_factor(item.uom_src, view["base_uom"], view["ref_code"], conversions)
    item.uom_factor = "" if factor is None else format(factor, "g")


def _blank(item: InvoiceItem, match_status: InvoiceMatchStatus) -> None:
    item.match_source = ""
    item.master_ref = ""
    item.name_pl = ""
    item.tariff_cn = ""
    item.sent = False
    item.uom_factor = ""
    item.match_status = match_status


def reset_match(item: InvoiceItem, master_ref: str) -> None:
    """Operator zmienił REF master ręcznie: stare wzbogacenie (nazwa/CN/SENT z poprzedniego
    dopasowania) nie może zostać. Pusty REF = „nie ma w master” (nie blokuje); niepusty czeka
    na resolve_chosen_refs — do tego czasu jest niejednoznaczny (blokuje zatwierdzenie)."""
    _blank(item, InvoiceMatchStatus.unmatched if not master_ref else InvoiceMatchStatus.ambiguous)
    item.master_ref = master_ref


def _fill_weight(item: InvoiceItem, weight_map: dict | None, filled_refs: set) -> None:
    """Wagi/kartony z packing listy po znormalizowanym REF (dokładnie albo alias cyfrowy).

    Mapa PL trzyma SUMĘ per REF, więc tylko PIERWSZA linia danego REF może z niej brać —
    faktura wielo-LOT (kilka linii, ten sam REF) skopiowałaby sumę do każdej linii."""
    if not weight_map:
        item.weight_source = "brak"
        return
    ref = normalize_ref(item.raw_ref)
    if ref and ref in filled_refs:
        item.weight_source = item.weight_source or "brak"
        return
    entry = weight_map.get(ref)
    if entry is None and ref:
        cands = [k for k in weight_map
                 if k.startswith(ref) and (k[len(ref):] == "" or k[len(ref):].isdigit())]
        if len(cands) == 1:
            entry = weight_map[cands[0]]
    # waga z tabeli faktury (jeśli była) wygrywa; PL uzupełnia TYLKO puste
    if entry and not item.weight_net and not item.weight_gross:
        item.weight_net = entry.get("weight_net", "") or item.weight_net
        item.weight_gross = entry.get("weight_gross", "") or item.weight_gross
        item.weight_source = "pl"
    else:
        item.weight_source = item.weight_source or "brak"
    if entry and not item.cartons:
        item.cartons = entry.get("cartons", "") or ""
    if ref:
        filled_refs.add(ref)


def _text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


def build_items(db: Session, raw_items: list[dict], company_id: int | None,
                weight_map: dict | None = None, supplier_id: int | None = None,
                ref_kind: str = "ours") -> list[InvoiceItem]:
    """Surowe pozycje z ekstraktora → obiekty InvoiceItem wzbogacone master datą
    (reguły, a gdy te zawiodą — sugestia ML z historii zatwierdzeń / podobieństwa).
    `ref_kind="supplier"` (profil dostawcy): REF z faktury to kod dostawcy — dopasowanie
    tylko przez SupplierMaterialMap, bez reguł REF (zbieżny kod ≠ nasz materiał)."""
    conversions = load_conversions(db)
    filled_refs: set = set()
    out = []
    for line_no, raw in enumerate(raw_items, start=1):
        item = InvoiceItem(
            line_no=line_no,
            raw_ref=_text(raw.get("ref"), 100),
            descr=_text(raw.get("desc"), 500),
            qty=_text(raw.get("qty"), 40),
            uom_src=_text(raw.get("unit"), 20),
            net_amount=_text(raw.get("net"), 40),
            amount=_text(raw.get("amount") or raw.get("net"), 40),
            weight_net=_text(raw.get("weight_net"), 40),
            weight_gross=_text(raw.get("weight_gross"), 40),
            cartons=_text(raw.get("cartons"), 40),
        )
        match(db, item, company_id, conversions, supplier_id, ref_kind)
        if item.match_status != InvoiceMatchStatus.matched:
            suggest(db, item, company_id, supplier_id, conversions, ref_kind)
        _fill_weight(item, weight_map, filled_refs)
        out.append(item)
    return out


def suggest(db: Session, item: InvoiceItem, company_id: int | None, supplier_id: int | None,
            conversions: list[dict] | None = None, ref_kind: str = "ours") -> None:
    """Sugestia ML dla pozycji bez dopasowania regułowego. Pewna (≥ próg) i istniejąca
    w master → pozycja dopasowana z match_source='ml'; słabsza → tylko podpowiedź."""
    suggestions = ml.suggest_ref(item.raw_ref, item.descr, supplier_id)
    if not suggestions:
        return
    best = suggestions[0]
    item.ml_suggestion = best.master_ref
    item.ml_confidence = best.score
    if best.score < settings.ml_auto_apply_threshold:
        return
    # X vs X1 (ambiguous) rozstrzyga operator albo JEGO wcześniejsza decyzja (historia);
    # samo podobieństwo n-gramów nie odróżni wariantów sufiksu — zostaje podpowiedzią
    if item.match_status == InvoiceMatchStatus.ambiguous and best.source != "history":
        return
    # kod dostawcy: podobieństwo do naszych REF nic nie znaczy — auto tylko z historii
    if ref_kind == "supplier" and best.source != "history":
        return
    material = get_material(db, best.master_ref)
    if material is None:
        return
    conversions = load_conversions(db) if conversions is None else conversions
    _enrich(item, effective(material, company_id), conversions)
    item.match_status = InvoiceMatchStatus.matched
    item.match_source = "ml"


def match(db: Session, item: InvoiceItem, company_id: int | None,
          conversions: list[dict] | None = None, supplier_id: int | None = None,
          ref_kind: str = "ours") -> None:
    conversions = load_conversions(db) if conversions is None else conversions
    # słownik indeksów dostawcy ma pierwszeństwo przed regułami REF
    mapped = resolve_supplier_ref(db, company_id, supplier_id, item.raw_ref)
    if mapped:
        material = get_material(db, mapped)
        if material:
            _enrich(item, effective(material, company_id), conversions)
            item.match_status = InvoiceMatchStatus.matched
            item.match_source = "supplier_map"
            return
    if ref_kind == "supplier":   # brak mapowania kodu = „do przypisania” (jak dziś)
        _blank(item, InvoiceMatchStatus.unmatched)
        return
    material = get_material(db, item.raw_ref) if item.raw_ref else None
    if material:
        _enrich(item, effective(material, company_id), conversions)
        item.match_status = InvoiceMatchStatus.matched
        item.match_source = "rules"
        return
    cands = find_candidates(db, item.raw_ref) if item.raw_ref else []
    if len(cands) == 1:
        _enrich(item, effective(cands[0], company_id), conversions)
        item.match_status = InvoiceMatchStatus.matched
        item.match_source = "rules"
    elif len(cands) > 1:
        _blank(item, InvoiceMatchStatus.ambiguous)
    else:
        _blank(item, InvoiceMatchStatus.unmatched)


def resolve_chosen_refs(db: Session, job: InvoiceJob, company_id: int | None) -> None:
    """Po zapisie weryfikacji: pozycje z ręcznie wpisanym master_ref dostają dane z master
    i status matched, jeśli taki REF istnieje. Nie istnieje → zostaje jak było
    (ambiguous nadal blokuje zatwierdzenie)."""
    conversions = load_conversions(db)
    for item in job.items:
        if item.match_status == InvoiceMatchStatus.matched:
            continue
        ref = (item.master_ref or "").strip()
        if not ref:
            continue
        material = get_material(db, ref)
        if not material:
            continue
        _enrich(item, effective(material, company_id), conversions)
        item.match_status = InvoiceMatchStatus.matched
        item.match_source = "user"

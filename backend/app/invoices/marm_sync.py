"""MARM (jednostki z SAP) → kartoteka materiałów faktur (`Material` + `UomConversion`).

Dopasowanie faktur szuka tylko w `Material`; sam eksport MARM zna numer materiału, jednostki,
przeliczniki i EAN — zakładamy więc brakujące materiały (bez nazwy PL / CN: te daje import
master daty) i uzupełniamy puste pola istniejących. Nazw, CN ani SENT nie ruszamy."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Material, UomConversion
from . import uom
from .uom import normalize_ref

_NOT_BASE = {"JU"}   # „JU” w eksporcie ACME ma 1/1, ale nie jest jednostką magazynową


def base_unit(units: list[dict]) -> dict | None:
    """Jednostka podstawowa: przelicznik 1/1 (MARM nie ma MARA-MEINS), SZT przed innymi."""
    ones = [u for u in units if u["numerator"] == u["denominator"] and u["unit"] not in _NOT_BASE]
    return next((u for u in ones if u["unit"] == "SZT"), ones[0] if ones else None)


def sync(db: Session, rows: list[dict], dry_run: bool) -> dict:
    by_material: dict[str, list[dict]] = {}
    for row in rows:
        by_material.setdefault(row["material_no"], []).append(row)
    existing = {m.ref_code: m for m in db.scalars(select(Material))}
    rules = {(r.ref_norm, r.unit_from, r.unit_to): r for r in db.scalars(select(UomConversion))}
    counts = {"materials_new": sum(1 for no in by_material if no not in existing), "conversions": 0}
    for material_no, units in by_material.items():
        base = base_unit(units)
        norm = normalize_ref(material_no)
        conversions = [] if base is None else [
            (uom.canonical_unit(u["unit"]), uom.canonical_unit(base["unit"]),
             u["numerator"] / u["denominator"])
            for u in units if u is not base and u["unit"] not in _NOT_BASE
            and uom.canonical_unit(u["unit"]) != uom.canonical_unit(base["unit"])]
        counts["conversions"] += len(conversions)
        if dry_run:
            continue
        material = existing.get(material_no)
        if material is None:
            material = Material(ref_code=material_no, ref_norm=norm)
            db.add(material)
            existing[material_no] = material
        material.ref_norm = material.ref_norm or norm
        if base is not None:
            material.base_uom = material.base_uom or base["unit"]
            material.ean = material.ean or (base.get("ean") or "")[:14]
        for unit_from, unit_to, factor in conversions:
            rule = rules.get((norm, unit_from, unit_to))
            if rule is None:
                rule = UomConversion(ref_norm=norm, unit_from=unit_from, unit_to=unit_to, factor=factor)
                db.add(rule)
                rules[(norm, unit_from, unit_to)] = rule
            else:
                rule.factor = factor
    return counts

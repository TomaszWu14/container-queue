"""Kontrole dokumentu wg profilu dostawcy (etap 3 spec 2026-09-24-profil-dostawcy):
jednostki (ilość w jednostce podstawowej i uzupełniającej, cena za jednostkę podstawową),
waga netto per REF, suma pozycji ↔ suma faktury, ilość CI ↔ PL i CI ↔ zamówienie SAP.

Liczone przy odczycie z bieżących pozycji (edycja w weryfikacji od razu zmienia wynik);
z ekstrakcji bierzemy tylko to, czego pozycje nie niosą: `InvoiceJob.check_data`
(suma z faktury, ilości z PL). Tolerancja jak `apply_supplier_rules` w compare:
|a − b| / |b| ≤ tol %."""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InvoiceJob, Material, OrderItem, SapOrder
from . import uom
from .matching import load_conversions
from .orders_link import invoice_orders, supplier_check
from .numbers import normalize_number
from .uom import normalize_ref

DEFAULT_TOL_AMOUNT, DEFAULT_TOL_QTY = 0.5, 0.0


def diff_pct(value: Decimal, reference: Decimal) -> Decimal | None:
    if reference == 0:
        return None if value == 0 else Decimal("100")
    return (value - reference) / abs(reference) * 100


def within(value: Decimal, reference: Decimal, tol_pct: float) -> bool:
    d = diff_pct(value, reference)
    return d is None or abs(d) <= Decimal(str(tol_pct))


def _num(value) -> Decimal | None:
    return normalize_number(value) if value not in (None, "") else None


def _cmp(value: Decimal | None, reference: Decimal | None, tol: float) -> dict | None:
    """{value, reference, diff_pct, ok} albo None, gdy po którejś stronie brak danych."""
    if value is None or reference is None:
        return None
    d = diff_pct(value, reference)
    return {"value": _s(value), "reference": _s(reference),
            "diff_pct": None if d is None else round(float(d), 2), "ok": within(value, reference, tol)}


def _s(value: Decimal | None) -> str:
    return "" if value is None else format(value.normalize(), "f")


def _tolerances(job: InvoiceJob) -> tuple[float, float, dict]:
    supplier = job.batch.supplier if job.batch else None
    profile = supplier.doc_profile if supplier else None
    info = {"supplier": supplier.name if supplier else "",
            "status": profile.status if profile else "none"}
    if profile is None:
        return DEFAULT_TOL_AMOUNT, DEFAULT_TOL_QTY, info
    return profile.tol_amount_pct, profile.tol_qty_pct, info


def order_qty(db: Session, container_id: int | None, company_id: int | None,
              extra: tuple[str, ...] = ()) -> dict[str, list]:
    """REF → [(ilość, jednostka)] z pozycji zamówień SAP podpiętych do kontenera
    i wymienionych na fakturze (`extra` — numer z nagłówka, zanim ktoś podepnie kontener)."""
    numbers = set(extra) | set(db.scalars(
        select(SapOrder.order_number).where(SapOrder.container_id == container_id)))
    query = select(OrderItem).where(OrderItem.order_number.in_(numbers))
    if company_id is not None:
        query = query.where(OrderItem.company_id == company_id)
    out: dict[str, list] = {}
    for row in db.scalars(query):
        qty = _num(row.quantity)
        if row.material and qty is not None:
            out.setdefault(row.material.strip(), []).append((qty, row.unit))
    return out


def _to_base(qty: Decimal, unit: str, base_uom: str, ref: str, conversions) -> Decimal | None:
    if not (unit or "").strip():
        return qty            # brak jednostki = ilość w jednostce podstawowej
    factor = uom.get_factor(unit, base_uom, ref, conversions)
    return None if factor is None else qty * Decimal(str(factor))


def _group_items(items, materials: dict, conversions) -> dict[str, dict]:
    """Pozycje faktury → grupy per REF (master albo surowy): sumy ilości (także w jednostce
    podstawowej), kwot i wag oraz flagi braków przelicznika/wagi."""
    groups: dict[str, dict] = {}
    for item in items:
        key = item.master_ref or item.raw_ref
        g = groups.setdefault(key, {"ref": key, "matched": bool(item.master_ref), "qty": Decimal(0),
                                    "qty_base": Decimal(0), "amount": Decimal(0),
                                    "weight_net": Decimal(0), "raw_refs": set(),
                                    "no_factor": False, "no_weight": False, "item": item})
        qty = _num(item.qty) or Decimal(0)
        g["qty"] += qty
        g["amount"] += _num(item.amount) or Decimal(0)
        g["raw_refs"].add(normalize_ref(item.raw_ref))
        material = materials.get(item.master_ref)
        base = _to_base(qty, item.uom_src, material.base_uom if material else "", key, conversions)
        if base is None:
            g["no_factor"] = True
        else:
            g["qty_base"] += base
        weight = _num(item.weight_net)
        if weight is None:
            g["no_weight"] = True
        else:
            g["weight_net"] += weight
    return groups


def _group_row(key: str, g: dict, material, pl_qty: dict, order: list, conversions,
               tol_qty) -> dict:
    """Wiersz kontroli jednej grupy: ilość w jednostce podstawowej i dodatkowej, cena
    jednostkowa, porównania CI↔PL i CI↔zamówienie, brakujące dane."""
    base_uom = material.base_uom if material else ""
    qty_base = None if g["no_factor"] else g["qty_base"]
    factor = material.suppl_factor if material else None
    pl = [pl_qty[r] for r in g["raw_refs"] if pl_qty.get(r) is not None]
    order_base = [_to_base(q, u, base_uom, key, conversions) for q, u in order]
    missing = [name for name, flag in (
        ("cn", not g["item"].tariff_cn), ("name_pl", not g["item"].name_pl),
        ("weight", g["no_weight"]), ("unit", g["no_factor"])) if flag]
    return {
        "ref": key, "matched": g["matched"], "qty": _s(g["qty"]),
        "qty_base": _s(qty_base), "base_uom": base_uom,
        "qty_suppl": _s(qty_base * Decimal(str(factor))) if qty_base is not None and factor else "",
        "suppl_unit": material.suppl_unit if material else "",
        "price_base": _s((g["amount"] / qty_base).quantize(Decimal("0.0001")))
        if qty_base else "",
        "weight_net": "" if g["no_weight"] else _s(g["weight_net"]),
        "ci_pl": _cmp(g["qty"], sum(pl, Decimal(0)) if pl else None, tol_qty),
        "ci_order": _cmp(qty_base, sum(order_base, Decimal(0))
                         if order_base and None not in order_base else None, tol_qty),
        "missing": missing,
    }


def job_checks(db: Session, job: InvoiceJob, company_id: int | None) -> dict:
    """Kontrole dokumentu: suma faktury, CI↔PL i CI↔zamówienie per REF (CODE-004: reguły
    w _group_items/_group_row zamiast jednej funkcji)."""
    tol_amount, tol_qty, profile = _tolerances(job)
    data = job.check_data or {}
    items = [i for i in job.items if not i.skipped]
    conversions = load_conversions(db)
    refs = {i.master_ref for i in items if i.master_ref}
    materials = {m.ref_code: m for m in db.scalars(
        select(Material).where(Material.ref_code.in_(refs)))} if refs else {}
    mentioned = invoice_orders(db, job, company_id)
    orders = order_qty(db, job.batch.container_id if job.batch else None, company_id,
                       tuple(o.order_number for o in mentioned))
    supplier = supplier_check(db, job, mentioned)
    pl_qty = {k: _num(v) for k, v in (data.get("pl_qty") or {}).items()}
    rows = [_group_row(key, g, materials.get(key), pl_qty, orders.get(key, []), conversions,
                       tol_qty)
            for key, g in _group_items(items, materials, conversions).items()]
    charges = data.get("charges") or []
    # koszty dodatkowe z faktury (bez indeksu) wchodzą do sumy — faktura je sumuje
    total_items = sum((_num(i.amount) or Decimal(0) for i in items), Decimal(0))         + sum((_num(c.get("amount")) or Decimal(0) for c in charges), Decimal(0))
    amount = _cmp(total_items, _num(data.get("doc_total")), tol_amount)
    ok = all(c["ok"] for c in [amount, *(r[k] for r in rows for k in ("ci_pl", "ci_order"))] if c)         and (supplier is None or supplier["ok"] is not False)
    return {"profile": profile, "tol_amount_pct": tol_amount, "tol_qty_pct": tol_qty,
            "amount": amount, "charges": charges, "supplier": supplier, "refs": rows, "ok": ok}

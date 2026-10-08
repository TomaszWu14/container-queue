"""Packing lista → mapa REF → {weight_net, weight_gross, cartons} (sumy per REF)."""
from decimal import Decimal

from .extractor import parse_pdf
from .numbers import normalize_number
from .uom import normalize_ref


def _add(acc: dict, key: str, fieldname: str, raw) -> None:
    # wagi to wartości dziesiętne („1,500” kg = 1.5, jak w kolumnach wag faktury);
    # liczba kartonów — całkowita („1,000” = tysiąc)
    decimal_field = fieldname != "cartons"
    value = normalize_number(raw, prefer_decimal=decimal_field) if raw not in (None, "") else None
    if value is None:
        return
    prev = acc[key].get(fieldname)
    base = Decimal(prev) if prev not in (None, "") else Decimal("0")
    acc[key][fieldname] = str(base + value)


def weight_map_from_items(items: list[dict]) -> dict:
    out: dict = {}
    for item in items:
        ref = normalize_ref(item.get("ref"))
        if not ref:
            continue
        wn, wg, ct = item.get("weight_net"), item.get("weight_gross"), item.get("cartons")
        if wn in (None, "") and wg in (None, "") and ct in (None, ""):
            continue
        out.setdefault(ref, {})
        _add(out, ref, "weight_net", wn)
        _add(out, ref, "weight_gross", wg)
        _add(out, ref, "cartons", ct)
    return {k: v for k, v in out.items() if v}


def qty_map_from_items(items: list[dict]) -> dict:
    """REF (znormalizowany) → suma ilości z packing listy, jako tekst (kontrola CI↔PL)."""
    out: dict = {}
    for item in items:
        ref, qty = normalize_ref(item.get("ref")), normalize_number(item.get("qty"))
        if ref and qty is not None:
            out[ref] = out.get(ref, Decimal("0")) + qty
    return {k: str(v) for k, v in out.items()}


def extract_weight_map(path: str) -> dict:
    return weight_map_from_items(parse_pdf(path).items)

"""Porównanie draftu SAD z paczką faktur (spec 2026-09-29-agencja-draft-sad §2, PR 2). Czysta
funkcja na słownikach z `sad_parse` i `sad_ours` — bez bazy, testowana na danych syntetycznych.

Grupy CN (agencja łączy pozycje po kodzie towaru). Tolerancje z profilu dostawcy: wartości
`tol_amount_pct`, masa i j. uzupełniające `tol_qty_pct`; masa netto dodatkowo ±1 kg
(zgłoszenie podaje kg zaokrąglone). `ok is None` = nie da się sprawdzić automatycznie
(pole nieodczytane albo brak naszych danych) → „sprawdź ręcznie”, nigdy „zgodne”."""
import re
from decimal import Decimal

from .checks import _cmp, _num, _s

MASS_ABS_KG = Decimal("1")
_FIELDS = ("value", "net_mass", "suppl_qty")
_EMPTY = {"ours": None, "sad": None, "diff_pct": None, "ok": None}


def _norm_no(number: str | None) -> str:
    return re.sub(r"\s", "", number or "").upper()


def _mentions(text: str, number: str) -> bool:
    """Numer faktury w tekście draftu jako osobny token; separatory w środku dowolne
    („T-1” = „T 1” = „T/1”), ale „T1” wewnątrz „DRAFT 15a” się nie liczy."""
    chars = [c for c in number.upper() if c.isalnum()]
    body = r"[\s\-/._]*".join(re.escape(c) for c in chars)
    return bool(chars) and re.search(r"(?<![0-9A-Z])" + body + r"(?![0-9A-Z])", text) is not None


def _field(sad: str | None, ours: str | None, tol: float, mass: bool = False) -> dict:
    s, o = _num(sad), _num(ours)
    cmp = _cmp(s, o, tol)
    ok = None if cmp is None else cmp["ok"]
    if ok is False and mass and s is not None and o is not None:
        ok = abs(s - o) <= MASS_ABS_KG
    return {"ours": ours, "sad": sad, "diff_pct": None if cmp is None else cmp["diff_pct"], "ok": ok}


def _sad_groups(items: list[dict]) -> dict[str, dict]:
    """Pozycje draftu zsumowane po CN (ta sama grupa może mieć kilka pozycji SAD)."""
    sums: dict[str, dict] = {}
    for item in items:
        if not item.get("cn"):
            continue                       # CN nieodczytany — pozycja jest w `unread`
        group = sums.setdefault(item["cn"], {"items": [], "missing": set(),
                                             **{f: Decimal(0) for f in _FIELDS}})
        group["items"].append(item["no"])
        for f in _FIELDS:
            value = _num(item.get(f))
            if value is None:
                group["missing"].add(f)
            else:
                group[f] += value
    return {cn: {"items": g["items"], **{f: None if f in g["missing"] else _s(g[f]) for f in _FIELDS}}
            for cn, g in sums.items()}


def _group(cn: str, ours: dict | None, sad: dict | None, tol_amount: float, tol_qty: float) -> dict:
    row: dict = {"cn": cn, "refs": ours["refs"] if ours else [],
                 "sad_items": sad["items"] if sad else [],
                 "suppl_unit": ours["suppl_unit"] if ours else "", "suppl_qty": None}
    if ours is None or sad is None:
        key, side = ("ours", ours) if sad is None else ("sad", sad)
        if side is None:          # `compare` idzie po sumie CN obu stron — któraś zawsze jest
            raise ValueError(f"CN {cn}: brak obu stron porównania")
        row.update(status="missing_in_sad" if sad is None else "extra_in_sad",
                   value={**_EMPTY, key: side["value"]}, net_mass={**_EMPTY, key: side["net_mass"]})
        return row
    row.update(value=_field(sad["value"], ours["value"], tol_amount),
               net_mass=_field(sad["net_mass"], ours["net_mass"], tol_qty, mass=True))
    if ours["suppl_unit"]:
        row["suppl_qty"] = _field(sad["suppl_qty"], ours["suppl_qty"], tol_qty)
    checked = [f for f in (row["value"], row["net_mass"], row["suppl_qty"]) if f is not None]
    row["status"] = ("diff" if any(f["ok"] is False for f in checked)
                     else "manual" if any(f["ok"] is None for f in checked) else "ok")
    return row


def _header(ours: dict, parsed: dict) -> list[dict]:
    text = (parsed.get("text") or "").upper()
    missing = [n for n in ours["invoices"] if not _mentions(text, n)]
    currency = parsed.get("currency")
    total = _field(parsed.get("total"), ours["total"], ours["tol_amount_pct"])
    dispatch = parsed.get("country_dispatch")
    container = parsed.get("container")
    return [
        {"field": "invoices", "ours": ", ".join(ours["invoices"]), "sad": None, "diff_pct": None,
         "ok": (not missing) if text and ours["invoices"] else None, "detail": ", ".join(missing)},
        {"field": "currency", "ours": ours["currency"], "sad": currency, "diff_pct": None,
         "ok": ours["currency"] == currency if ours["currency"] and currency else None, "detail": ""},
        {"field": "total", "ours": ours["total"], "sad": total["sad"], "diff_pct": total["diff_pct"],
         "ok": total["ok"], "detail": ours["charges"] if _num(ours["charges"]) else ""},
        {"field": "country", "ours": ours["country"], "sad": dispatch, "diff_pct": None,
         "ok": ours["country"] == dispatch if ours["country"] and dispatch else None,
         "detail": parsed.get("country_origin") or ""},
        {"field": "container", "ours": ours["container"], "sad": container, "diff_pct": None,
         "ok": _norm_no(ours["container"]) == _norm_no(container)
         if ours["container"] and container else None, "detail": ""},
    ]


def compare(ours: dict, parsed: dict) -> dict:
    sad = _sad_groups(parsed.get("items") or [])
    groups = [_group(cn, ours["groups"].get(cn), sad.get(cn), ours["tol_amount_pct"],
                     ours["tol_qty_pct"]) for cn in sorted(set(ours["groups"]) | set(sad))]
    header = _header(ours, parsed)
    diff = (sum(g["status"] in ("diff", "missing_in_sad", "extra_in_sad") for g in groups)
            + sum(h["ok"] is False for h in header))
    manual = sum(g["status"] == "manual" for g in groups) + sum(h["ok"] is None for h in header)
    return {"header": header, "groups": groups, "no_cn": ours["no_cn"],
            "unread": parsed.get("unread") or [], "error": parsed.get("error"),
            "tolerances": {"amount_pct": ours["tol_amount_pct"], "qty_pct": ours["tol_qty_pct"],
                           "mass_abs_kg": float(MASS_ABS_KG)},
            "summary": {"groups": len(groups), "ok": sum(g["status"] == "ok" for g in groups),
                        "diff": diff, "manual": manual,
                        "all_ok": diff == 0 and manual == 0 and not ours["no_cn"]
                        and not parsed.get("error")}}

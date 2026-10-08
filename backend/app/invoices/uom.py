"""Jednostki miary i przeliczniki między poziomami opakowań (karton ↔ sztuki).

Reguły są danymi (`UomConversion`): 1 `unit_from` = `factor` × `unit_to`;
`ref_norm='*'` = reguła globalna. Moduł nie dotyka bazy — dostaje listę reguł.
"""
import re

_UNIT_ALIASES = {
    "PCS": "PCS", "PC": "PCS", "PIECE": "PCS", "PIECES": "PCS",
    "SZT": "PCS", "SZTUKA": "PCS", "SZTUKI": "PCS", "SZTUK": "PCS",
    "EA": "PCS", "EACH": "PCS", "EACHES": "PCS", "UNIT": "PCS", "UNITS": "PCS",
    "CTN": "CTN", "CARTON": "CTN", "CARTONS": "CTN", "KARTON": "CTN",
    "KARTONY": "CTN", "KAR": "CTN", "BOX": "CTN", "BOXES": "CTN",
    "OP": "OP", "OPAKOWANIE": "OP", "OPAKOWANIA": "OP", "PACK": "OP",
    "PACKS": "OP", "PKG": "OP",
    "OPZ": "OPZ",
    "PAL": "PAL", "PALLET": "PAL", "PALLETS": "PAL", "PALETA": "PAL", "PALETY": "PAL",
    "PAZ": "PAZ", "PPA": "PPA",
    "SET": "SET", "SETS": "SET", "KPL": "SET", "ZESTAW": "SET", "ZESTAWY": "SET",
}


def canonical_unit(value) -> str:
    """Kanoniczna jednostka ('' gdy pusta). Liczba mnoga przez ucięcie końcówki Y/S."""
    unit = re.sub(r"[^A-Z]", "", str(value or "").upper())
    if unit in _UNIT_ALIASES:
        return _UNIT_ALIASES[unit]
    for suffix in ("Y", "S"):
        if len(unit) >= 3 and unit.endswith(suffix) and unit[:-1] in _UNIT_ALIASES:
            return _UNIT_ALIASES[unit[:-1]]
    return unit


def normalize_ref(raw) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(raw or "").upper())


def get_factor(unit_from, unit_to, ref, conversions: list[dict]) -> float | None:
    """Przelicznik z `unit_from` na `unit_to` dla REF: najpierw reguła per REF, potem
    globalna; obsługuje kierunek odwrotny."""
    uf, ut = canonical_unit(unit_from), canonical_unit(unit_to)
    if not uf or not ut:
        return None
    if uf == ut:
        return 1.0
    ref_norm = normalize_ref(ref)
    for want in ([ref_norm, "*"] if ref_norm else ["*"]):
        for rule in conversions:
            if rule.get("ref_norm", "*") != want or not rule.get("factor"):
                continue
            if rule["unit_from"] == uf and rule["unit_to"] == ut:
                return rule["factor"]
            if rule["unit_from"] == ut and rule["unit_to"] == uf:
                return 1.0 / rule["factor"]
    return None

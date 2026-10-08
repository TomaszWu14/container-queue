"""Import master daty materiałów z xlsx (szablon Compare / ACME) do `Material` +
przeliczników `UomConversion`.

Tolerancyjny na format nagłówka:
- jednowierszowy z nazwami maszynowymi (ref_code, opis_pl, tariff_cn, …), albo
- dwuwierszowy: wiersz 1 = banner poziomów (SZT/OP/OPZ/KAR/PAZ/PPA, scalony),
  wiersz 2 = nazwy pól („Podstawowa jednostka miary”, „Ilość podstawowej jednostki
  miary”, sztuka_wymiar, …).
Idempotentny: upsert po ref_code; SENT/VAT nadpisywane tylko, gdy import podał wartość.
"""
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, noload

from ..models import Material, UomConversion, utcnow
from ..tabular import load_workbook_or_422, normalize_header
from . import uom
from .numbers import normalize_number
from .uom import normalize_ref

_BANNER_LEVEL = {"SZT": "sztuka", "OP": "op", "OPZ": "opz", "KAR": "karton",
                 "PAZ": "paz", "PPA": "ppa"}
_LEVEL_UNIT = {"sztuka": "SZT", "op": "OP", "opz": "OPZ", "karton": "KAR",
               "paz": "PAZ", "ppa": "PPA"}


def _norm_hdr(value) -> str:
    return normalize_header(value).replace(".", "")


# CODE-004: aliasy nagłówków pól globalnych jako dane (zbiory rozłączne — kolejność bez znaczenia)
_GLOBAL_ALIASES = {
    "ref_code": ("ref_code", "ref", "indeks", "kod", "kod_produktu", "material", "materiał"),
    "name_pl": ("opis_pl", "opis polski", "opis pl", "nazwa pl", "name_pl"),
    "name_en": ("opis_en", "opis angielski", "opis en", "nazwa en", "name_en"),
    "family": ("rodzina", "grupa", "rodzina/grupa", "family"),
    "base_uom": ("podstawowa jednostka miary", "jm", "jednostka", "jednostka miary",
                 "podstawowa jm", "base_uom"),
    "producer_code": ("producent", "manufacturer", "kod_producenta", "mfr", "producer_code"),
    "tariff_cn": ("tariff_cn", "taryfa cn", "cn", "taryfa", "kod cn", "tariff"),
    "customs_code": ("customs_code", "kod celny", "kod celny materialu", "kod celny materiału",
                     "kod taryfy celnej", "customs code", "customs"),
    "supplier_codes": ("supplier_codes", "dostawcy", "kody dostawcow", "kody dostawców",
                       "dostawca"),
    "vat_rate": ("vat", "vat_rate", "stawka vat", "stawka_vat", "vat %", "vat%",
                 "stawka podatku vat", "podatek vat"),
    "sent": ("sent", "czy sent", "sent t/n", "sent tak/nie", "nadzor sent", "nadzór sent",
             "monitorowanie sent", "podlega sent"),
}
_GLOBAL_FIELD = {alias: field for field, aliases in _GLOBAL_ALIASES.items() for alias in aliases}
_LEVEL_FIELD_RE = re.compile(r"(sztuka|szt|op|opz|karton|kar|paz|ppa)[_ ](wymiar|ean|artwork_ref|artwork)\b")


def _classify(field_hdr: str, banner: str):
    """('global', pole) | ('level', (poziom, podpole)) | (None, None)."""
    f = _norm_hdr(field_hdr)
    b = str(banner or "").strip().upper()
    lvl_banner = _BANNER_LEVEL.get(b)
    if not f:
        return (None, None)
    if f in _GLOBAL_FIELD:
        return ("global", _GLOBAL_FIELD[f])
    if f == "ean" and not lvl_banner:
        return ("global", "ean")
    if "kod producenta" in f:
        return ("global", "producer_code")
    return _classify_level(f, b, lvl_banner)


def _classify_level(f: str, b: str, lvl_banner: str | None):
    """Pola poziomów opakowań: jawny poziom w nagłówku, przelicznik (qty_base) albo
    podpole pod banerem poziomu (wymiar/EAN/artwork)."""
    m = _LEVEL_FIELD_RE.match(f)
    if m:
        level = {"szt": "sztuka", "kar": "karton"}.get(m.group(1), m.group(1))
        sub = "artwork_ref" if "artwork" in m.group(2) else m.group(2)
        return ("level", (level, sub))
    if "ilosc podstawowej jednostki miary" in f or "ilość podstawowej jednostki miary" in f \
            or f.startswith("przelicznik"):
        level = ("paz" if f.endswith("paz") or b == "PAZ"
                 else "ppa" if f.endswith("ppa") or b == "PPA" else lvl_banner)
        if level:
            return ("level", (level, "qty_base"))
    if lvl_banner:
        if f in ("wymiar", "wymiary"):
            return ("level", (lvl_banner, "wymiar"))
        if f == "ean":
            return ("level", (lvl_banner, "ean"))
        if "artwork" in f:
            return ("level", (lvl_banner, "artwork_ref"))
    return (None, None)


def sent_truthy(value) -> bool:
    return str(value or "").strip().lower() in (
        "1", "tak", "t", "yes", "y", "x", "true", "sent", "prawda")


def clean_ean(raw) -> str:
    """Same cyfry EAN tylko przy poprawnej długości (8/13/14) — inaczej ''."""
    digits = re.sub(r"\D", "", str(raw or ""))
    return digits if len(digits) in (8, 13, 14) else ""


def norm_vat(value) -> str:
    s = str(value or "").strip().lower().replace("%", "").replace(",", ".").strip()
    if s in ("zw", "zw.", "zwolniony", "np", "n/p", "np."):
        return s.replace(".", "")[:10]
    m = re.search(r"\d+(?:\.\d+)?", s)
    if m:
        n = m.group()
        return (n[:-2] if n.endswith(".0") else n)[:10]
    return s[:10]


def _ffill(seq):
    out, last = [], ""
    for value in seq:
        s = str(value or "").strip()
        if s:
            last = s
        out.append(last)
    return out


# ile początkowych wierszy przeszukujemy w poszukiwaniu nagłówka (tytuł arkusza, data
# eksportu, pusta linia nad nagłówkiem — typowe w szablonach xlsx)
_HEADER_SEARCH_ROWS = 15


def _is_header(cells: list[str]) -> bool:
    """Wiersz nagłówka = ma kolumnę REF (ref_code/indeks/kod…)."""
    return any(_classify(c, "")[1] == "ref_code" for c in cells)


def _find_header(rows: list) -> tuple[int, list | None]:
    """(indeks wiersza nagłówka, banner poziomów albo None). Banner = wiersz TUŻ NAD
    nagłówkiem z kodami SZT/OP/OPZ/KAR/PAZ/PPA — sam wiersz nagłówka może mieć kolumnę
    o nazwie „OP” czy „PAZ”, więc o bannerze decyduje brak kolumny REF w tym wierszu."""
    for idx in range(min(len(rows), _HEADER_SEARCH_ROWS)):
        cells = [str(c or "").strip() for c in rows[idx]]
        if _is_header(cells):
            banner = None
            if idx > 0:
                above = [str(c or "").strip() for c in rows[idx - 1]]
                if any(x.upper() in _BANNER_LEVEL for x in above) and not _is_header(above):
                    banner = _ffill(rows[idx - 1])
            return idx, banner
    return -1, None


def parse_workbook_rows(rows: list) -> list[dict]:
    """Wiersze arkusza (nagłówek 1- lub 2-wierszowy, dowolnie wysoko) → rekordy materiałów."""
    rows = [list(r) for r in rows if isinstance(r, (list, tuple))]
    if not rows:
        return []
    hdr_idx, banner = _find_header(rows)
    if hdr_idx < 0:
        return []
    headers = [str(c or "").strip() for c in rows[hdr_idx]]
    colmap = []
    last_level = None
    for ci, header in enumerate(headers):
        b = banner[ci] if (banner and ci < len(banner)) else ""
        kind, key = _classify(header, b)
        if kind == "level":
            last_level = key[0]
        elif kind is None and last_level and "podstawowej jednostki miary" in _norm_hdr(header):
            kind, key = "level", (last_level, "qty_base")
        colmap.append((kind, key))
    # kolumny obecne w arkuszu — import CZĘŚCIOWY (np. sam REF + kod CN) nie może
    # wyzerować pól, których w pliku nie było
    present = {key for kind, key in colmap if kind == "global"}
    levels_present = any(kind == "level" for kind, _ in colmap)

    records = []
    for row in rows[hdr_idx + 1:]:
        glob: dict = {}
        levels: dict = {}
        for ci, (kind, key) in enumerate(colmap):
            if kind is None or ci >= len(row):
                continue
            value = str(row[ci]).strip() if row[ci] is not None else ""
            if not value:
                continue
            if kind == "global":
                glob[key] = value
            else:
                level, sub = key
                # EAN/SSCC (≥12 cyfr) w kolumnie przelicznika to błąd danych — pomijamy
                if sub == "qty_base" and len(re.sub(r"\D", "", value)) >= 12:
                    continue
                levels.setdefault(level, {})[sub] = value
        ref = glob.get("ref_code", "")
        if not ref:
            continue
        records.append({
            "ref_code": ref[:100],
            "ref_norm": normalize_ref(ref),
            "name_pl": glob.get("name_pl", "")[:500],
            "name_en": glob.get("name_en", "")[:500],
            "ean": clean_ean(glob.get("ean", "")),
            "family": glob.get("family", "")[:160],
            "base_uom": glob.get("base_uom", "")[:20],
            "producer_code": glob.get("producer_code", "")[:60],
            "tariff_cn": glob.get("tariff_cn", "")[:30],
            "customs_code": glob.get("customs_code", "")[:30],
            "vat_rate": norm_vat(glob.get("vat_rate", "")),
            "sent": sent_truthy(glob["sent"]) if "sent" in glob else None,
            "supplier_codes": glob.get("supplier_codes", "")[:500],
            "levels": levels,
            "present": present,
            "levels_present": levels_present,
        })
    return records


def load_xlsx_rows(content: bytes) -> list[list]:
    """Wiersze PIERWSZEGO arkusza z nagłówkiem REF (szablony miewają arkusz „Instrukcja”
    na pierwszej karcie); brak takiego → pierwszy arkusz (parser zwróci pusto)."""
    wb = load_workbook_or_422(content)
    first: list[list] | None = None
    for ws in wb.worksheets:
        rows = [list(row) for row in ws.iter_rows(values_only=True)]
        if first is None:
            first = rows
        if _find_header(rows)[0] >= 0:
            return rows
    return first or []


def _conversion_rules(rec: dict) -> list[tuple[str, str, float]]:
    base = (rec.get("base_uom") or "").strip()
    if not base:
        return []
    rules = []
    for level, data in (rec.get("levels") or {}).items():
        q = data.get("qty_base")
        if not q:
            continue
        parsed = normalize_number(q)   # „1 000”, „1.000,5”, „240” — format PL i EN
        if parsed is None or parsed <= 0:
            continue
        factor = float(parsed)
        unit_from = uom.canonical_unit(_LEVEL_UNIT.get(level, level.upper()))
        unit_to = uom.canonical_unit(base)
        if unit_from == unit_to:   # SZT→SZT = no-op zaśmiecający tabelę
            continue
        rules.append((unit_from, unit_to, factor))
    return rules


def import_records(db: Session, records: list[dict], dry_run: bool) -> dict:
    """Upsert materiałów + reguł JM. Zwraca liczniki; przy dry_run nic nie zapisuje."""
    # bez nadpisań per spółka (selectin) — upsert ich nie dotyka, a to drugi pełny odczyt tabeli
    existing = {m.ref_code: m for m in db.scalars(select(Material)
                                                  .options(noload(Material.overrides))).all()}
    rules_existing = {(r.ref_norm, r.unit_from, r.unit_to): r
                      for r in db.scalars(select(UomConversion)).all()}
    new = updated = conversions = 0
    seen: set[str] = set()
    for rec in records:
        if rec["ref_code"] in seen:
            continue
        seen.add(rec["ref_code"])
        material = existing.get(rec["ref_code"])
        if material is None:
            new += 1
        else:
            updated += 1
        rules = _conversion_rules(rec)
        conversions += len(rules)
        if dry_run:
            continue
        is_new = material is None
        if is_new:
            material = Material(ref_code=rec["ref_code"])
            db.add(material)
            existing[rec["ref_code"]] = material
        material.ref_norm = rec["ref_norm"]
        present = rec.get("present") or set()
        for key in ("name_pl", "name_en", "ean", "family", "base_uom",
                    "producer_code", "tariff_cn", "customs_code", "supplier_codes"):
            # kolumna obecna, ale komórka pusta = „brak danych”, nie „wyczyść”: szablon
            # utrzymywany dla części wierszy nie może zerować CN istniejącego materiału
            if is_new or (key in present and rec[key]):
                setattr(material, key, rec[key])
        if rec["vat_rate"]:
            material.vat_rate = rec["vat_rate"]
        if rec["sent"] is not None:
            material.sent = rec["sent"]
        if is_new or rec.get("levels_present"):
            material.levels_json = json.dumps(rec["levels"], ensure_ascii=False)
        material.updated_at = utcnow()
        for unit_from, unit_to, factor in rules:
            key = (rec["ref_norm"], unit_from, unit_to)
            rule = rules_existing.get(key)
            if rule is None:
                rule = UomConversion(ref_norm=rec["ref_norm"], unit_from=unit_from,
                                     unit_to=unit_to, factor=factor)
                db.add(rule)
                rules_existing[key] = rule
            else:
                rule.factor = factor
    return {"total": len(seen), "new": new, "updated": updated, "conversions": conversions}

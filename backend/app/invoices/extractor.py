"""Tabela pozycji faktury z warstwy tekstowej PDF (pdfplumber, bez OCR).

Rozpoznanie kolumn po wielojęzycznych nagłówkach (auto-detekcja) albo z mapy kolumn
dostawcy (`Supplier.column_map`: "ref=Item No.; qty=Q'ty; net=Amount"). Skan bez
tekstu daje pustą listę pozycji — router zamienia to na czytelny błąd dokumentu.
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ..tabular import normalize_header as _norm_header
from .numbers import normalize_number, number_text

# ile wierszy tabeli przeszukujemy w poszukiwaniu nagłówka: strona ze skanu/bez linii
# tabeli jest JEDNĄ tabelą, a nagłówek pozycji siedzi pod blokami adresów (15–25 linii)
_HEADER_SCAN_ROWS = 60

# role kolumn akceptowane w mapie dostawcy (reszta = ignorowana, żeby literówka admina
# nie zawiesiła ekstrakcji)
COLUMN_ROLES = ("ref", "desc", "qty", "price", "net", "unit", "lot",
                "weight_net", "weight_gross", "cartons", "no")
# nazwy ról z repo compare (supplier_profiles.COLUMN_ROLES + role SAD) → nazwy powyżej;
# „skip” z kreatora compare = kolumna pominięta (nie trafia do mapy)
ROLE_ALIASES = {"description": "desc", "quantity": "qty", "amount": "net",
                "net_weight": "weight_net", "gross_weight": "weight_gross",
                "packages": "cartons"}

# (rola, [słowa kluczowe], priorytet) — dopasowanie dokładne liczy podwójnie
_RULES = [
    ("ref", ["product code", "ref / desc", "ref/desc", "ref. / desc", "ref/description",
             "code", "sku", "article no", "article no.", "art. no", "art no",
             "item no", "item no.", "item number", "nr ref", "indeks", "kod art",
             "catalog no", "cat no", "cat. no", "catalogue no", "part no", "part number",
             "material", "material no", "numer art", "numer artykułu",
             "product ref", "ref.", "reference", "reference no"], 10),
    ("qty", ["order qty", "quantity/unit", "quantity", "qty", "ilość", "ilosc",
             "menge", "qty(pcs)", "pcs", "pieces", "count", "liczba",
             "ordered qty", "shipped qty", "shipped quantity", "q-ty", "q'ty",
             "amount qty", "total qty", "quantity (pcs)", "szt"], 8),
    ("price", ["unit-price", "unit price", "price per", "cena jedn", "preis",
               "price", "unit price (usd)", "unit price (eur)", "uprice",
               "unit cost", "cena", "price per unit", "rate",
               "unit value", "cena jednostkowa"], 8),
    ("net", ["net value", "net amount", "wartość netto", "amount (usd)", "amount(usd)",
             "amount", "total amount", "total value", "total net", "netto",
             "line total", "line amount", "extended", "extension", "total price",
             "value", "wartość", "kwota"], 8),
    ("lot", ["lot number", "lot numbers", "lot no", "lot no.", "lot", "batch",
             "batch no", "batch number", "seria", "numer serii", "nr serii",
             "lote", "charge", "chargennummer"], 8),
    ("desc", ["description of goods", "description", "opis", "nazwa", "goods",
              "item description", "goods description", "product description",
              "commodity", "commodity description", "details",
              "name of goods", "product name", "towar"], 8),
    ("unit", ["order unit", "base unit", "unit", "jm", "uom", "j.m.", "um",
              "unit of measure", "jednostka"], 4),
    ("no", ["no", "lp", "l.p.", "s.no", "sno", "no.", "nr", "pos",
            "position", "pozycja", "pos.", "item"], 4),
    ("weight_gross", ["gross weight", "gross wt", "g.w.", "g/w", "gw (kg)",
                      "waga brutto", "brutto (kg)", "waga brutto (kg)"], 9),
    ("weight_net", ["net weight", "nett weight", "net wt", "n.w.", "n/w", "nw (kg)",
                    "waga netto", "netto (kg)", "waga netto (kg)"], 9),
    ("cartons", ["ctns", "cartons", "carton qty", "no. of cartons",
                 "number of cartons", "liczba kartonów", "kartony"], 7),
]

_FUZZY_TARGETS = {
    "ref": ["product code", "reference", "article", "item no"],
    "qty": ["quantity", "ilość", "pcs", "pieces"],
    "price": ["unit price", "price", "cena"],
    "net": ["net value", "amount", "total"],
}


def identify_columns(header_row: list) -> dict[str, int]:
    """{rola: indeks kolumny} dla wiersza nagłówkowego (nagłówki wielojęzyczne, łamane)."""
    headers = [_norm_header(h) for h in header_row]
    assigned: dict[str, int] = {}
    scores: dict[str, int] = {}
    for idx, header in enumerate(headers):
        if not header:
            continue
        best_score, best_role = 0, None
        for role, keywords, priority in _RULES:
            for keyword in keywords:
                if header == keyword:
                    score = len(keyword) * priority * 2
                elif keyword in header:
                    score = len(keyword) * priority
                else:
                    continue
                if score > best_score:
                    best_score, best_role = score, role
        if best_role and best_score > scores.get(best_role, 0):
            assigned[best_role] = idx
            scores[best_role] = best_score

    # fuzzy fallback dla kluczowych kolumn (literówki OCR w nagłówkach)
    for role, targets in _FUZZY_TARGETS.items():
        if role in assigned:
            continue
        for idx, header in enumerate(headers):
            if not header or idx in assigned.values():
                continue
            if any(SequenceMatcher(None, header, t).ratio() >= 0.75 for t in targets):
                assigned[role] = idx
                break

    # „REF / Description” — ref + opis w tej samej komórce
    for idx, header in enumerate(headers):
        if ("ref" in header or "code" in header) and \
                ("desc" in header or "description" in header or "name" in header):
            assigned["ref"] = idx
            assigned["_ref_desc_combined"] = idx
            break
    if "no" in assigned and "ref" not in assigned:
        assigned["ref"] = assigned["no"]
        assigned["_sno_format"] = True
    return assigned


def parse_column_map(text: str) -> dict[str, str]:
    """„ref=Item No.; qty=Q'ty; net=Amount” → {rola: nagłówek}. Nieznane role pomijane."""
    out: dict[str, str] = {}
    for chunk in re.split(r"[;\n]", text or ""):
        if "=" not in chunk:
            continue
        role, header = chunk.split("=", 1)
        role, header = role.strip().lower(), header.strip()
        role = ROLE_ALIASES.get(role, role)
        if role in COLUMN_ROLES and header:
            out[role] = header
    return out


def _alias_score(header: str, target: str) -> float:
    if header == target:
        return 100.0
    if target in header and len(target) > 3:
        return len(target) / max(len(header), 1) * 90
    if header in target and len(header) > 3:
        return len(header) / max(len(target), 1) * 70
    return 0.0


def apply_column_map(header_row: list, column_map: dict[str, str | list[str]]) -> dict | None:
    """Dopasowuje mapę dostawcy do nagłówka; None, gdy nie ma ref + (qty|net). Rola może
    mieć kilka aliasów nagłówka (profil dokumentów) — wygrywa najlepiej pasujący."""
    if not column_map:
        return None
    headers = [_norm_header(h) for h in header_row]
    ci: dict = {}
    for role, names in column_map.items():
        targets = [_norm_header(n) for n in ([names] if isinstance(names, str) else names)]
        best_idx, best_score = None, 0.0
        for idx, header in enumerate(headers):
            score = max((_alias_score(header, t) for t in targets if t), default=0.0)
            if score > best_score:
                best_idx, best_score = idx, score
        if best_idx is not None and best_score > 40:
            ci[role] = best_idx
    if "ref" in ci:
        ref_header = headers[ci["ref"]]
        if "/" in ref_header and ("desc" in ref_header or "ref" in ref_header):
            ci["_ref_desc_combined"] = ci["ref"]
        if "s.no" in ref_header or "sno" in ref_header:
            ci["_sno_format"] = True
    if "ref" in ci and ("qty" in ci or "net" in ci):
        return ci
    return None


_TOTAL_ROW = tuple(re.compile(p) for p in (
    r"(grand\s+|sub\s*)?total(?![\w-])", r"razem\b", r"suma\b", r"łącznie\b"))
_TOTAL_WORDS = {"total", "grand total", "subtotal", "sub total", "razem", "suma", "łącznie"}
_NOT_REF = {"NO", "REF", "CODE", "ITEM", "LOT", "QTY", "PRICE", "NET", "TOTAL", "USD", "EUR"}


def is_total_row(row: list, ci: dict | None = None) -> bool:
    """Wiersz sumy: któraś komórka ZACZYNA się od „total/razem/suma…” i komórka REF nie
    wygląda jak kod towaru — „Total Care nitrile gloves” w opisie pozycji to nie suma."""
    cells = [str(c or "").strip().lower() for c in row]
    if not any(p.match(cell) for cell in cells for p in _TOTAL_ROW):
        return False
    if ci and ci.get("ref") is not None:
        idx = ci["ref"]
        ref_cell = str(row[idx] or "").strip().split("\n")[0] if idx < len(row) else ""
        # kod towaru w kolumnie REF („SUMA-1”, „GLV-TC”) = pozycja; suma ma tam pusto
        # albo samo słowo kluczowe
        if is_ref_value(ref_cell) and ref_cell.lower() not in _TOTAL_WORDS:
            return False
    return True


def is_ref_value(value) -> bool:
    """Czy wartość wygląda jak kod referencyjny (nie nagłówek, nie opis, nie numer PO)."""
    if not value or len(value) < 2 or len(value) > 60:
        return False
    v = value.strip().split("\n")[0].strip()
    if re.match(r"^45\d{8}$", v) or re.match(r"^\d{9,}$", v):
        return False
    if re.match(r"^[A-Za-z0-9][A-Za-z0-9\-_\.]{1,34}$", v) and v.upper() not in _NOT_REF:
        return True
    # kod ze spacją („AT-SGS-XL 1”, „AT-SD-S 1 BLUE-CN” — master ma „AT-SGS-XL_1”): same wielkie
    # litery, max 4 człony, z cyfrą albo myślnikiem — opisy („Disposable Gowns”, „BANK OF CHINA”) nie
    if (len(v) <= 35 and re.match(r"^[A-Z0-9][A-Z0-9\-_\./]*(?: [A-Z0-9\-_\./]+){1,3}$", v)
            and re.search(r"[\d\-]", v)):
        return True
    return bool(re.match(r"^\d+\.(AT|NF|BL|CI|PO|PI)[A-Za-z0-9\-_\s\.]{2,40}$", v))


def get_cell(row: list, ci: dict, role: str) -> str | None:
    idx = ci.get(role)
    if idx is None or idx >= len(row) or row[idx] is None:
        return None
    lines = [line.strip() for line in str(row[idx]).split("\n") if line.strip()]
    return " ".join(lines[:3]) or None


@dataclass
class ParsedDoc:
    items: list = field(default_factory=list)
    total_net: str | None = None
    total_qty: str | None = None
    raw_text: str = ""
    invoice_number: str = ""
    ocr_used: bool = False
    # linie kosztów bez indeksu w tabeli pozycji („LCL handling charge”, „printing plate cost”)
    charges: list = field(default_factory=list)


@dataclass
class PageData:
    text: str = ""
    tables: list = field(default_factory=list)
    ocr: bool = False
    # wiersze z pozycji słów — zapas, gdy „liniowane” tabele pdfplumber nie dadzą pozycji
    # (ramka wokół nagłówka dokumentu wykryta jako tabela, a tabela pozycji bez linii)
    fallback_rows: list = field(default_factory=list)


def read_pages(path: str) -> list[PageData]:
    """Strony PDF: tekst + tabele z warstwy tekstowej (pdfplumber); strona bez tekstu
    (skan) idzie przez OCR — tekst i wiersze odtworzone z pozycji słów (ocr.py).
    Strona z tekstem, ale bez linii tabeli (extract_tables pusty — częste w fakturach
    generowanych z Excela) dostaje wiersze z pozycji słów tą samą metodą co OCR."""
    import pdfplumber

    from . import ocr
    out = []
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if ocr.needs_ocr(text):
                scanned = ocr.ocr_page(path, index)
                if scanned.text:
                    out.append(PageData(text=scanned.text, tables=[scanned.rows], ocr=True))
                    continue
            tables = page.extract_tables() or []
            _, rows = ocr.words_to_rows(ocr.pdf_words(page))
            if not tables:
                out.append(PageData(text=text, tables=[rows] if rows else []))
            else:
                out.append(PageData(text=text, tables=tables, fallback_rows=rows))
    return out


def _as_page(page) -> PageData:
    if isinstance(page, PageData):
        return page
    text, tables = page   # krotka (tekst, tabele) — wygodna w testach
    return PageData(text=text, tables=tables)


def _clean_number(raw: str | None, prefer_decimal: bool = False) -> str | None:
    if not raw:
        return None
    text = number_text(raw.lstrip("$").strip(), prefer_decimal=prefer_decimal)
    return text or raw.lstrip("$").strip()


_QTY_UNIT = re.compile(r"^\s*([-+]?[\d.,\s\u00a0]+)\s*([A-Za-z][A-Za-z./]{0,7})\s*$")


def _split_qty_unit(qty: str | None, unit: str | None) -> tuple[str | None, str | None]:
    """„1,000 PCS” w jednej komórce → ilość „1,000” + jednostka „PCS” (gdy kolumny JM brak)."""
    if not qty:
        return qty, unit
    m = _QTY_UNIT.match(qty)
    if m and m.group(1).strip():
        return m.group(1).strip(), (unit or m.group(2).strip())
    return qty, unit


def _line_amount(qty: str | None, price: str | None) -> str | None:
    """Kwota pozycji, gdy faktura nie ma kolumny wartości: ilość × cena jednostkowa.
    Sama cena jednostkowa NIE jest kwotą pozycji — lepiej puste niż mylące."""
    q, p = normalize_number(qty), normalize_number(price, prefer_decimal=True)
    if q is None or p is None:
        return None
    return number_text(q * p)


def parse_pages(pages: list, column_map: dict[str, str] | None = None) -> ParsedDoc:
    items: list[dict] = []
    totals: dict = {"net": None, "qty": None, "charges": []}
    texts = []
    ocr_used = False
    for page in map(_as_page, pages):
        texts.append(page.text)
        ocr_used = ocr_used or page.ocr
        before = len(items)
        for table in page.tables:
            _parse_table(table, column_map, items, totals)
        if len(items) == before and page.fallback_rows:
            # tabele „z linii” nie dały pozycji (np. tylko ramka nagłówka) → wiersze ze słów
            _parse_table(page.fallback_rows, column_map, items, totals)
    raw = "\n".join(texts)
    return ParsedDoc(items=items, total_net=totals["net"], total_qty=totals["qty"], raw_text=raw,
                     invoice_number=extract_invoice_number(raw), ocr_used=ocr_used,
                     charges=totals["charges"])


def _parse_table(table: list, column_map: dict[str, str] | None, items: list[dict],
                 totals: dict) -> None:
    """Pozycje z jednej tabeli (dopisuje do `items`, sumy do `totals`); tabela bez
    rozpoznanego nagłówka pozycji = nic."""
    if not table or len(table) < 2:
        return
    ci: dict = {}
    header_idx = -1
    for i, row in enumerate(table[:_HEADER_SCAN_ROWS]):
        if not row:
            continue
        candidate = apply_column_map(row, column_map or {}) or identify_columns(row)
        if ("ref" in candidate or "_ref_desc_combined" in candidate) and \
                ("qty" in candidate or "net" in candidate):
            ci, header_idx = candidate, i
            break
    if header_idx < 0:
        return
    ref_col = ci.get("ref", 0)
    combined = "_ref_desc_combined" in ci
    sno_format = "_sno_format" in ci
    for row in table[header_idx + 1:]:
        if not row:
            continue
        if is_total_row(row, ci):
            totals["net"] = get_cell(row, ci, "net") or totals["net"]
            totals["qty"] = get_cell(row, ci, "qty") or totals["qty"]
            continue
        ref_cell = str(row[ref_col] or "") if ref_col < len(row) else ""
        ref_lines = ref_cell.strip().split("\n")
        ref = ref_lines[0].strip()
        if sno_format and ref:
            m = re.match(r"^\d+\.((?:AT|NF|BL|CI|PO|PI)[\w\-\s]+)", ref, re.IGNORECASE)
            if m:
                ref = re.sub(r"\s+", "_", m.group(1).strip())
                ref = re.sub(r"-(\d+)-([A-Z])$", r"_\1_\2", ref).upper()
            elif ref.isdigit():
                continue   # kolumna „S.No” użyta jako REF: „10”, „11” to numery pozycji
        if not is_ref_value(ref) and not (
                sno_format and re.match(r"^(?:AT|NF|BL|CI|PO|PI)", ref, re.IGNORECASE)):
            charge = _charge(row, ci, ref)
            if charge:
                totals.setdefault("charges", []).append(charge)
            continue
        if combined and len(ref_lines) > 1:
            desc = " ".join(ref_lines[1:]).strip()
        else:
            desc = (get_cell(row, ci, "desc") or "").replace("\n", " ").strip()
        qty, unit = _split_qty_unit(get_cell(row, ci, "qty"), get_cell(row, ci, "unit"))
        price = _clean_number(get_cell(row, ci, "price"), prefer_decimal=True)
        net = _clean_number(get_cell(row, ci, "net"))
        items.append({
            "ref": ref, "desc": desc,
            "qty": qty,
            "price": price,
            "net": net,
            "amount": net or _line_amount(qty, price),
            "unit": unit,
            "weight_net": _clean_number(get_cell(row, ci, "weight_net"), prefer_decimal=True),
            "weight_gross": _clean_number(get_cell(row, ci, "weight_gross"), prefer_decimal=True),
            "cartons": get_cell(row, ci, "cartons"),
        })


def _charge(row: list, ci: dict, text: str) -> dict | None:
    """Koszt dodatkowy: w kolumnie REF słowa (małe litery, spacja), bez ilości, z kwotą —
    „LCL handling charge | US$500.00”. Nagłówki/bank/„Say: …” nie mają kwoty w kolumnie wartości."""
    if not (re.search(r"[a-z]", text) and " " in text) or get_cell(row, ci, "qty"):
        return None
    amount = normalize_number(get_cell(row, ci, "net"))
    if not amount:
        return None
    return {"desc": text[:120], "amount": format(amount, "f")}


def parse_pdf(path: str, column_map: dict[str, str] | None = None) -> ParsedDoc:
    return parse_pages(read_pages(path), column_map)


_INVOICE_NO = [
    re.compile(r"(?:COMMERCIAL\s+|PROFORMA\s+|PROFOMA\s+)?INVOICE\s*(?:NO|NUMBER|NR|#)\.?\s*[:：]?\s*"
               r"([A-Z0-9][A-Z0-9\-/\.]{2,30})", re.IGNORECASE),
    re.compile(r"INVOICE\s*[:：]\s*([A-Z0-9][A-Z0-9\-/\.]{2,30})", re.IGNORECASE),
    re.compile(r"(?:NO\.?\s*&\s*DATE\s+OF\s+INVOICE|NR\s+FAKTURY|FAKTURA\s+NR)\s*[:：]?\s*"
               r"([A-Z0-9][A-Z0-9\-/\.]{2,30})", re.IGNORECASE),
]
_NOT_INVOICE_NO = {"DATE", "NO", "AND", "NUMBER"}
_DATE_LIKE = re.compile(r"^(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2}[-./]\d{2,4})$")


def extract_invoice_number(text: str) -> str:
    """Numer faktury z nagłówka; data po „Invoice:” („Date of invoice: 2026-09-01”) nim nie jest."""
    for pattern in _INVOICE_NO:
        for m in pattern.finditer(text or ""):
            value = m.group(1).strip().rstrip(".,:")
            if value.upper() in _NOT_INVOICE_NO or not re.search(r"\d", value):
                continue
            if _DATE_LIKE.match(value):
                continue
            return value[:80]
    return ""


_CONTAINER_RE = re.compile(r"CONTAINER\s*NO\.?\s*[:：]?\s*([A-Z]{4}\s?\d{7})", re.IGNORECASE)
_TERMS_RE = re.compile(r"TERMS\s+OF\s+DELIVERY\s*[:：]?\s*([A-Z]{3}[^\n\r]{0,40})", re.IGNORECASE)
_INCOTERMS = ("EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP",
              "DAP", "DPU", "DDP", "DAT", "DAF", "DES", "DEQ", "DDU")


def header_meta(raw_text: str) -> dict:
    """Numer kontenera i warunki dostawy z nagłówka faktury. Warunki tylko, gdy zaczynają
    się znanym Incotermem — bez tej straży regex łapał przypadkowe linie."""
    text = raw_text or ""
    m = _CONTAINER_RE.search(text)
    d = _TERMS_RE.search(text)
    terms = d.group(1).strip() if d else ""
    if terms[:3].upper() not in _INCOTERMS:
        terms = ""
    return {"container_no": m.group(1).replace(" ", "").upper() if m else "",
            "delivery_terms": terms[:60]}


__all__ = ["COLUMN_ROLES", "ROLE_ALIASES", "PageData", "ParsedDoc", "apply_column_map",
           "extract_invoice_number", "get_cell",
           "header_meta", "identify_columns", "is_ref_value", "is_total_row",
           "normalize_number", "parse_column_map", "parse_pages", "parse_pdf", "read_pages"]

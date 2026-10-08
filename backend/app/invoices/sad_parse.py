"""Odczyt draftu SAD (PDF od agencji celnej) → pola do porównania z fakturami (spec
2026-09-29-agencja-draft-sad §2, PR 2).

Dwa układy (`layout`): „winsad” — wydruk WinSAD od Delta Brokers, dwie kolumny z numerami
elementów danych (`sad_winsad`, PR 5); „generic” — „etykieta: wartość” w jednej linii
(„38 Masa netto (kg): 12,500”), tekst jak faktury: `extractor.read_pages` (skan → OCR).
Pole nieodczytane trafia do `unread`, nigdy nie zgadujemy. Liczby w formacie polskim
(przecinek dziesiętny) → `prefer_decimal`."""
import io
import logging
import re
from decimal import Decimal

from . import extractor, sad_winsad, sad_xml
from .numbers import normalize_number

logger = logging.getLogger(__name__)

# zmiana wzorców → podbij: zapisane odczyty (`SadDraft.parsed`) się odświeżą; 2: WinSAD + kontener
PARSER_VERSION = 2
XML_LAYOUT = "winsad-xml"   # odczyt z XML zastępuje odczyt z PDF tej samej wersji draftu
TEXT_KEEP = 20000        # tekst do szukania numerów faktur (rubryka 44) przy porównaniu
PREVIEW_DPI = 110        # podgląd stron w oknie porównania
HEADER_FIELDS = ("currency", "total", "country_dispatch", "container")
ITEM_REQUIRED = ("cn", "value", "net_mass")

_SEP = r"[ \t]*[:.]?[ \t]*"
# „1 205,50” (grupy tysięcy spacją) albo zwarta liczba „950,00” / „12.500”;
# bez kropki/przecinka na końcu („12,500.” na końcu zdania to 12,5, nie 12 500)
_NUM = r"(\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|\d(?:[\d.,]*\d)?)"
_CC = r"((?-i:[A-Z]{2}))\b"
_I = re.IGNORECASE
_CN = re.compile(r"(?:33\.?[ \t]*)?Kod\s+towaru" + _SEP
                 + r"(\d{4}[ \t]?\d{2}[ \t]?\d{2})(?:[ \t]?\d{2})?", _I)
_TOTAL = re.compile(r"(?:22\.?[ \t]*)?Waluta\s+i\s+(?:ca[łl]kowita|og[óo]lna)\s+kwota\s+fakturowana"
                    + _SEP + r"(?:((?-i:[A-Z]{3}))[ \t]*" + _NUM + r"|" + _NUM
                    + r"[ \t]*((?-i:[A-Z]{3})))", _I)
_DISPATCH = re.compile(r"(?:15[ \t]*a\.?[ \t]*)?Kod\s+kraju\s+wysy[łl]ki(?:\s*/\s*eksportu)?"
                       + _SEP + _CC, _I)
_ORIGIN = re.compile(r"(?:34[ \t]*a?\.?[ \t]*)?Kod\s+kraju\s+pochodzenia" + _SEP + _CC, _I)
_MASS = re.compile(r"(?:38\.?[ \t]*)?Masa\s+netto(?:[ \t]*\(kg\))?" + _SEP + _NUM, _I)
_SUPPL = re.compile(r"(?:41\.?[ \t]*)?Jednostki\s+uzupe[łl]niaj[aą]ce(?:[ \t]*\([^)\n]*\))?"
                    + _SEP + _NUM, _I)
_VALUE = re.compile(r"(?:42\.?[ \t]*)?Cena\s+pozycji" + _SEP + _NUM, _I)
_CONTAINER = re.compile(r"Nr\s+kontenera" + _SEP + r"((?-i:[A-Z]{4})[ \t]?\d{7})", _I)


def _text(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


def _number(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return _text(normalize_number(match.group(1), prefer_decimal=True)) if match else None


def _country(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _total(text: str) -> tuple[str | None, str | None]:
    """Rubryka 22: „USD 1 205,50” albo „1 205,50 USD”."""
    match = _TOTAL.search(text)
    if not match:
        return None, None
    currency, raw = (match.group(1), match.group(2)) if match.group(1) else (match.group(4), match.group(3))
    return currency, _text(normalize_number(raw, prefer_decimal=True))


def _unread(out: dict, declared: int | None) -> list[dict]:
    missing = [{"item": None, "field": f} for f in HEADER_FIELDS if not out[f]]
    if not out["items"] or (declared is not None and declared != len(out["items"])):
        missing.append({"item": None, "field": "items"})     # nie wszystkie pozycje odczytane
    return missing + [{"item": i["no"], "field": f}
                      for i in out["items"] for f in ITEM_REQUIRED if not i[f]]


def _finish(fields: dict, text: str, layout: str, declared: int | None = None) -> dict:
    items = fields["items"]
    out = {"v": PARSER_VERSION, "layout": layout, **fields,
           "country_origin": next((i["origin"] for i in items if i["origin"]), None),
           "text": text[:TEXT_KEEP], "error": None if text.strip() else "no_text"}
    out["unread"] = _unread(out, declared)
    return out


def parse_text(pages: list[str]) -> dict:
    """Tekst stron → pola nagłówka i pozycje (pozycja = od „Kod towaru” do następnego)."""
    text = "\n".join(pages)
    starts = list(_CN.finditer(text))
    items = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[match.end():end]
        items.append({"no": index + 1, "cn": re.sub(r"\D", "", match.group(1)),
                      "value": _number(_VALUE, block), "net_mass": _number(_MASS, block),
                      "suppl_qty": _number(_SUPPL, block), "origin": _country(_ORIGIN, block)})
    currency, total = _total(text)
    container = _CONTAINER.search(text)
    return _finish({"currency": currency, "total": total,
                    "country_dispatch": _country(_DISPATCH, text),
                    "container": re.sub(r"\s", "", container.group(1)) if container else None,
                    "items": items}, text, "generic")


def parse_file(path: str) -> dict:
    """Odczyt pliku; uszkodzony / nie-PDF → wynik z `error` zamiast wyjątku (porównanie ręczne)."""
    winsad = sad_winsad.read_pages(path)
    if winsad is not None:
        text = "\n".join(winsad)
        fields, declared = sad_winsad.parse(text)
        return {**_finish(fields, text, "winsad", declared), "pages": len(winsad), "ocr": False}
    try:
        pages = extractor.read_pages(path)
    except Exception:  # noqa: BLE001 — każdy błąd biblioteki PDF = „nie da się odczytać”
        logger.warning("draft SAD: nie da się odczytać %s", path, exc_info=True)
        return {**parse_text([]), "error": "unreadable_pdf", "pages": 0, "ocr": False}
    out = parse_text([page.text for page in pages])
    out.update(pages=len(pages), ocr=any(page.ocr for page in pages))
    return out


def parse_xml(content: bytes) -> dict | None:
    """XML draftu z WinSAD (`sad_xml`) → ten sam kształt co `parse_file`, `layout` = XML_LAYOUT;
    None — to nie ten XML. Strony podglądu (`pages`) dalej z PDF — ustawia wołający."""
    got = sad_xml.parse(content)
    if got is None:
        return None
    fields, text = got
    out = _finish(fields, text, XML_LAYOUT, declared=len(fields["items"]))
    return {**out, "error": None, "ocr": False}   # brak faktur w [12 03] to nie „brak tekstu”


def page_count(path: str) -> int:
    import pypdfium2 as pdfium
    try:
        pdf = pdfium.PdfDocument(path)
    except Exception:  # noqa: BLE001 — uszkodzony plik = brak stron do podglądu
        return 0
    try:
        return len(pdf)
    finally:
        pdf.close()


def page_png(path: str, index: int) -> bytes:
    """Strona (0-indeksowana) jako PNG — podgląd „PDF obok” (iframe blokuje CSP)."""
    from . import ocr
    buf = io.BytesIO()
    ocr.render_page(path, index, dpi=PREVIEW_DPI).save(buf, format="PNG", optimize=True)
    return buf.getvalue()

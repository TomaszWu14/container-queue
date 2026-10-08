"""Draft SAD z programu WinSAD (Huzar Software) — wydruk „Podgląd danych zgłoszenia celnego
importowego” od Delta Brokers (spec 2026-09-29-agencja-draft-sad, PR 5: dostrojenie odczytu).

Wydruk ma dwie kolumny — lewa: opis, kod CN, dokumenty; prawa: wartości, masy, kraje — a pola
niosą numery elementów danych AIS/IMPORT PLUS („Masa netto [18 01]: 5377.83”). Zwykły
`extract_text` skleja kolumny w jedną linię i rozrywa etykiety, a pola pozycji przechodzą na
następną stronę. Dlatego tekst składamy sami: stronę tniemy na pasy po nagłówkach „Pozycja N”
(lewa kolumna) i w każdym pasie czytamy lewą, potem prawą kolumnę. Wszystko po „Pozycja N” do
następnego nagłówka (także na kolejnej stronie) należy do pozycji N. Liczby z kropką
dziesiętną, bez separatorów tysięcy."""
import collections
import logging
import re
from decimal import Decimal

from .numbers import normalize_number

logger = logging.getLogger(__name__)

_MARK = re.compile(r"WinSAD|Huzar Software", re.IGNORECASE)
_HEADING = re.compile(r"Pozycja\s+\d+")
# etykiety wyłącznie prawej kolumny („Metoda”, „Liczba” bywają też w tabeli opłat po lewej)
_RIGHT_LABELS = frozenset({"Kurs", "Masa", "Kraj", "Wartość", "Procedura", "Preferencje"})
_RIGHT_SHARE = 0.73          # granica kolumn, gdy na stronie nie ma żadnej etykiety prawej

_I = re.IGNORECASE
_NUM = r"(\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|\d(?:[\d.,]*\d)?)"   # jak sad_parse._NUM
_CC = r"((?-i:[A-Z]{2}))\b"


def _de(group: str, element: str) -> str:
    """Numer elementu danych „[14 08]:” — etykieta bywa złamana między liniami („[14⏎08]”)."""
    return r"\[\s*" + group + r"\s*" + element + r"\s*\]\s*:\s*"


_TOTAL = re.compile(r"Warto[śs][ćc]\s+faktur\s*" + _de("14", "06") + _NUM + r"\s*((?-i:[A-Z]{3}))", _I)
_DISPATCH = re.compile(r"Kraj\s+wysy[łl]ki\s*" + _de("16", "06") + _CC, _I)
_CONTAINER = re.compile(r"Nr\s+kontenera\s*:\s*((?-i:[A-Z]{4})\s?\d{7})", _I)
_COUNT = re.compile(r"Liczba\s+pozycji\s*:\s*(\d+)", _I)
_ITEM = re.compile(r"^Pozycja\s+(\d+)\s*$", re.MULTILINE)
_CN = re.compile(r"kod\s+CN\s*" + _de("18", "09") + r"(\d{4}\s?\d{2}\s?\d{2})", _I)
_VALUE = re.compile(r"Warto[śs][ćc]\s+fakturowa\s+poz\.?\s*" + _de("14", "08") + _NUM, _I)
_MASS = re.compile(r"Masa\s+netto\s*" + _de("18", "01") + _NUM, _I)
_SUPPL = re.compile(r"Ilo[śs][ćc]\s+w\s+jedn\.?\s+uzup\.?\s*" + _de("18", "02") + _NUM, _I)
_ORIGIN = re.compile(r"Kraj\s+pochodzenia\s*" + _de("16", "08") + _CC, _I)


def _cut(page) -> float:
    """Granica kolumn: najczęstszy początek etykiet prawej kolumny na stronie."""
    starts = collections.Counter(round(w["x0"]) for w in page.extract_words()
                                 if w["x0"] > page.width / 2 and w["text"] in _RIGHT_LABELS)
    return starts.most_common(1)[0][0] - 2 if starts else page.width * _RIGHT_SHARE


def _page_text(page) -> str:
    cut = _cut(page)
    # -1 pt: nagłówek „Pozycja N” otwiera swój pas, nie zamyka poprzedniego
    heads = sorted(h["top"] - 1 for h in page.search(_HEADING) if h["x0"] < cut)
    edges = [0.0, *heads, float(page.height)]
    parts = []
    for top, bottom in zip(edges, edges[1:], strict=False):
        if bottom - top < 1:
            continue
        for box in ((0, top, cut, bottom), (cut, top, page.width, bottom)):
            parts.append(page.crop(box).extract_text() or "")
    return "\n".join(part for part in parts if part)


def read_pages(path: str) -> list[str] | None:
    """Tekst stron w kolejności pasów i kolumn albo None — to nie wydruk WinSAD (inny układ,
    skan bez tekstu, nie-PDF): wtedy odczyt ogólny w `sad_parse`."""
    import pdfplumber
    try:
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            if not _MARK.search(text):
                return None
            return [_page_text(page) for page in pdf.pages]
    except Exception:  # noqa: BLE001 — błąd biblioteki PDF = „nie ten układ”, dalej odczyt ogólny
        logger.info("draft SAD: nie odczytano jako WinSAD %s", path, exc_info=True)
        return None


def _number(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    value: Decimal | None = normalize_number(match.group(1), prefer_decimal=True) if match else None
    return None if value is None else format(value.normalize(), "f")


def _code(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return re.sub(r"\s", "", match.group(1)) if match else None


def parse(text: str) -> tuple[dict, int | None]:
    """Pola jak `sad_parse` (currency, total, country_dispatch, container, items) + liczba
    pozycji zadeklarowana w nagłówku (kontrola, czy odczytaliśmy wszystkie)."""
    starts = list(_ITEM.finditer(text))
    head = text[:starts[0].start()] if starts else text
    items = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[match.end():end]
        items.append({"no": int(match.group(1)), "cn": _code(_CN, block) or "",
                      "value": _number(_VALUE, block), "net_mass": _number(_MASS, block),
                      "suppl_qty": _number(_SUPPL, block), "origin": _code(_ORIGIN, block)})
    total = _TOTAL.search(head)
    count = _COUNT.search(head)
    fields = {"currency": total.group(2) if total else None,
              "total": _number(_TOTAL, head),
              "country_dispatch": _code(_DISPATCH, head),
              "container": _code(_CONTAINER, text), "items": items}
    return fields, int(count.group(1)) if count else None

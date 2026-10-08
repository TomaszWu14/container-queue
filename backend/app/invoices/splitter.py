"""Tnie PDF-zestaw (CIPL / komplet kontenerowy) na osobne dokumenty po klasyfikacji stron.

Klasyfikacja po tekście strony (warstwa tekstowa albo OCR skanu; strona bez tekstu → „other”).
Tekst czyta pdfplumber, zakresy stron zapisuje pypdf; oba importowane leniwie, żeby moduły bez tej
ścieżki (testy logiki) nie ciągnęły zależności PDF.
"""
import pathlib
import re
from difflib import SequenceMatcher

from ..config import settings
from ..models import INVOICE_LIKE_KINDS, InvoiceDocKind
from . import ml
from .extractor import extract_invoice_number

# Kolejność ma znaczenie: strona packing listy zawiera słowo "invoice" w nagłówku
# („No. & date of invoice”), więc PACKING LIST sprawdzamy przed fakturami.
# Literówki z realnych dokumentów: PROFOMA, PORFORMA.
_MARKERS = [
    (InvoiceDocKind.packing_list, ("PACKING LIST", "PACKING NOTE", "LISTA PAKOWANIA",
                                   "SPECYFIKACJA PAKOWANIA")),
    (InvoiceDocKind.proforma, ("PROFORMA INVOICE", "PROFOMA INVOICE", "PORFORMA INVOICE",
                               "PRO-FORMA INVOICE")),
    (InvoiceDocKind.invoice, ("COMMERCIAL INVOICE",)),
    (InvoiceDocKind.other, ("BILL OF LADING", "OCEAN BILL", "SEA WAYBILL")),
    # B/L z nagłówkiem jako grafiką (brak „BILL OF LADING” w tekście) — klauzule typowe tylko dla B/L
    (InvoiceDocKind.other, ("SHIPPED ON BOARD", "SHIPPER'S LOAD", "SHIPPERS LOAD")),
]
# kafelek BL: klauzule B/L albo tytuł „BILL OF LADING” — ale nie wzmianka „BILL OF LADING NO: …”
# w piśmie przewodnim/awizie wysyłki (ono też jest „other”, ale konosamentem nie jest)
_BL_RE = re.compile(r"SHIPPED ON BOARD|SHIPPERS?'? LOAD|OCEAN BILL|SEA WAYBILL"
                    r"|BILL OF LADING(?!\s*(?:NO\b|NUMBER|#|:|：))")


def _marker_kind(text: str) -> InvoiceDocKind | None:
    """Typ z jawnego markera w tekście (także „other” dla B/L) albo None, gdy brak markera."""
    t = re.sub(r"\s+", " ", (text or "")).upper().strip()
    for kind, markers in _MARKERS:
        if any(m in t for m in markers):
            return kind
    return None


def is_bill_of_lading(text: str) -> bool:
    """Część „other” to konosament (B/L) — do kafelka BL dostawy."""
    t = re.sub(r"\s+", " ", (text or "")).upper()
    return bool(_BL_RE.search(t))


def marker_in(text: str, marker: str) -> bool:
    """Znacznik z profilu dostawcy w tekście strony: dokładnie (po ujednoliceniu spacji
    i wielkości liter) albo z literówką/OCR („PACK1NG LlST”) — okno tylu słów, ile ma
    znacznik, podobieństwo ≥ 0,85 (jak PROFOMA/PORFORMA w _MARKERS, ale bez listy)."""
    m = re.sub(r"\s+", " ", marker or "").upper().strip()
    if not m:
        return False
    t = re.sub(r"\s+", " ", text or "").upper()
    if m in t:
        return True
    words, n = t.split(), len(m.split())
    return any(SequenceMatcher(None, " ".join(words[i:i + n]), m).ratio() >= 0.85
               for i in range(len(words) - n + 1))


def _page_kind(text: str, pl_marker: str) -> InvoiceDocKind | None:
    """Znacznik PL z profilu dostawcy ma pierwszeństwo; bez niego — markery ogólne."""
    if pl_marker and marker_in(text, pl_marker):
        return InvoiceDocKind.packing_list
    return _marker_kind(text)


def classify_first_page(text: str) -> InvoiceDocKind:
    """Typ pierwszej strony dokumentu (bez „kontynuacji”): jawny marker ma pierwszeństwo
    (także B/L → other); bez markera — klasyfikator ML (OCR skanu potrafi zniekształcić
    nagłówek: „COMMERC1AL 1NVOICE”). Bez pewnego wyniku ML strona z tekstem to faktura
    (najczęstszy dokument w paczce), strona bez tekstu — other."""
    kind = _marker_kind(text)
    if kind is not None:
        return kind
    if _is_blank(text):
        return InvoiceDocKind.other
    predicted = ml.predict_doc_kind(text)
    if predicted and predicted[1] >= settings.ml_dockind_threshold:
        try:
            return InvoiceDocKind(predicted[0])
        except ValueError:   # model sprzed zmiany enumu — nie wywracamy uploadu
            pass
    return InvoiceDocKind.invoice


def page_texts(path: str) -> list[str]:
    """Tekst stron; strona bez warstwy tekstowej (skan) przez OCR (pusty, gdy OCR
    niedostępny — wtedy klasyfikuje się jako „other”)."""
    import pdfplumber

    from . import ocr
    out = []
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if ocr.needs_ocr(text):
                # tylko Tesseract: do rozpoznania typu strony wystarczy; vision przy ekstrakcji
                text = ocr.ocr_page(path, index, vision=False).text or text
            out.append(text)
    return out


def write_range(path: str, page_from: int, page_to: int, out_path: str) -> None:
    """Strony 1-indeksowane, zakres domknięty."""
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(path)
    writer = PdfWriter()
    for index in range(page_from - 1, page_to):
        writer.add_page(reader.pages[index])
    with open(out_path, "wb") as handle:
        writer.write(handle)


def _is_blank(text: str) -> bool:
    return len((text or "").strip()) < 30


def _starts_new_document(text: str, current: dict | None) -> bool:
    """Strona bez markera zaczyna NOWY dokument, gdy ma własny numer faktury inny niż
    bieżąca część (drugi skan w zestawie z nagłówkiem zniekształconym przez OCR:
    „COMMERC1AL 1NVOICE B”). Strona bez numeru albo z tym samym numerem = kontynuacja."""
    if current is None:
        return True
    number = extract_invoice_number(text)
    return bool(number) and number != current.get("invoice_number")


def _continues_same_invoice(marker: InvoiceDocKind, text: str, current: dict) -> bool:
    """Faktura z nagłówkiem „COMMERCIAL INVOICE” powtórzonym na KAŻDEJ stronie (typowe dla
    wydruków z ERP): strona z markerem tego samego typu i TYM SAMYM numerem faktury co
    bieżąca część to jej ciąg dalszy, nie nowy dokument (inaczej 3-stronicowa faktura
    dawałaby 3 osobne dokumenty, każdy z ułamkiem pozycji)."""
    if marker != current["kind"] or marker not in INVOICE_LIKE_KINDS:
        return False
    number = extract_invoice_number(text)
    return bool(number) and number == current.get("invoice_number")


def split_pdf(path: str, pl_marker: str = "", texts: list[str] | None = None) -> list[dict]:
    """[{kind, page_from, page_to, out_path, text}]. Jednodokumentowy PDF → jedna część
    wskazująca ORYGINALNY plik (bez kopii). `pl_marker` = `split_marker` profilu dostawcy;
    `texts` = tekst stron już przeczytany przez wołającego (rozpoznanie dostawcy)."""
    from . import ocr
    parts: list[dict] = []
    texts = page_texts(path) if texts is None else texts
    for number, text in enumerate(texts, start=1):
        marker = _page_kind(text, pl_marker)
        current = parts[-1] if parts else None
        if current is not None:
            # pusta strona (rewers duplexu, skan bez OCR) w środku dokumentu należy do niego —
            # nie może zaczynać części „other”, która połknęłaby dalsze strony tabeli
            if marker is None and (_is_blank(text) or not _starts_new_document(text, current)):
                current["page_to"] = number
                continue
            if marker is not None and _continues_same_invoice(marker, text, current):
                current["page_to"] = number
                continue
        kind = marker if marker is not None else classify_first_page(text)
        parts.append({"kind": kind, "page_from": number, "page_to": number,
                      "invoice_number": extract_invoice_number(text)})
    # tekst części = dane treningowe klasyfikatora typu (także dla PL i „other”)
    for part in parts:
        part["text"] = "\n".join(texts[part["page_from"] - 1:part["page_to"]])
        part.pop("invoice_number", None)
    if len(parts) <= 1:
        if parts:
            parts[0]["out_path"] = path
        return parts
    base = pathlib.Path(path)
    written: list[pathlib.Path] = []
    try:
        for n, part in enumerate(parts, start=1):
            out = base.with_name(f"{base.stem}_doc{n}_{part['kind'].value}.pdf")
            write_range(path, part["page_from"], part["page_to"], str(out))
            written.append(out)
            part["out_path"] = str(out)
            # strony części mają już wynik OCR pod ścieżką źródła — przepisujemy, nie liczymy 2×
            for offset, page_index in enumerate(range(part["page_from"] - 1, part["page_to"])):
                ocr.alias_page(path, page_index, str(out), offset)
    except BaseException:
        # część 2 padła (uszkodzona strona) → część 1 nie może zostać osieroconym plikiem
        for out in written:
            out.unlink(missing_ok=True)
        raise
    return parts

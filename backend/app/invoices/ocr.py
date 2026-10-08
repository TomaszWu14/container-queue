"""OCR skanów: strona PDF bez warstwy tekstowej → obraz (pypdfium2) → Tesseract.

Zwraca tekst strony (do klasyfikacji dokumentu i nagłówka faktury) oraz „tabelę”:
wiersze z komórkami odtworzonymi z pozycji słów (Tesseract `image_to_data`) — sąsiednie
słowa łączone w komórkę, większa przerwa pozioma = granica kolumny. Wynik trafia do
tego samego rozpoznawania nagłówków co tabele z pdfplumber (extractor).

Cache per (plik, mtime, strona): splitter i ekstraktor czytają tę samą stronę, a OCR
jednej strony to ~1–3 s.
"""
import logging
import os
import shutil
import statistics
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Annotated

from pydantic import (BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StringConstraints,
                      ValidationError, field_validator)

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class OcrPage:
    text: str = ""
    rows: list = field(default_factory=list)   # list[list[str]] — jedna „tabela” strony
    vision_tried: bool = False   # warstwa vision już próbowana (cache bez vision ≠ ostateczny)


def is_available() -> bool:
    """OCR włączony konfiguracją i binarka tesseract w PATH."""
    return bool(settings.ocr_enabled and shutil.which("tesseract"))


def render_page(path: str, index: int, dpi: int | None = None):
    """Strona (0-indeksowana) jako PIL.Image RGB."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(path)
    try:
        page = pdf[index]
        try:
            return page.render(scale=(dpi or settings.ocr_dpi) / 72).to_pil().convert("RGB")
        finally:
            page.close()
    finally:
        pdf.close()


# limit czasu na jedną stronę — zawieszony tesseract (uszkodzony obraz) nie może zająć
# wątku workera na zawsze
TESSERACT_TIMEOUT_S = 90


def _words(image) -> list[dict]:
    """Słowa z pozycjami (Tesseract TSV) — szew do testów (podmieniany bez binarki)."""
    import pytesseract
    data = pytesseract.image_to_data(image, lang=settings.ocr_lang, config="--psm 6",
                                     output_type=pytesseract.Output.DICT,
                                     timeout=TESSERACT_TIMEOUT_S)
    out = []
    for i, text in enumerate(data.get("text", [])):
        text = (text or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError, KeyError):
            conf = 0.0
        if conf < 0:
            continue
        out.append({"block": data["block_num"][i], "par": data["par_num"][i],
                    "line": data["line_num"][i], "left": int(data["left"][i]),
                    "top": int(data["top"][i]), "width": int(data["width"][i]),
                    "height": int(data["height"][i]), "text": text})
    return out


def _group_lines(words: list[dict]) -> list[list[dict]]:
    """Słowa → linie po współrzędnej pionowej (środek słowa), nie po numerach linii
    Tesseracta: PSM 6 tnie wiersz tabeli na osobne bloki (opis po lewej, liczby po prawej),
    co dawałoby dwa „wiersze” z jednej pozycji. Słowa o środkach w odległości < ½ typowej
    wysokości należą do tej samej linii."""
    if not words:
        return []
    heights = [max(w["height"], 1) for w in words]
    tolerance = max(statistics.median(heights) * 0.5, 3.0)
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"] + w["height"] / 2, w["left"])):
        center = word["top"] + word["height"] / 2
        if lines:
            last = lines[-1]
            last_center = statistics.fmean(w["top"] + w["height"] / 2 for w in last)
            if abs(center - last_center) <= tolerance:
                last.append(word)
                continue
        lines.append([word])
    return lines


def words_to_rows(words: list[dict]) -> tuple[str, list[list[str]]]:
    """Słowa (left/top/width/height/text) → (tekst strony, wiersze z komórkami).

    Komórka kończy się, gdy przerwa do następnego słowa przekracza ~2.5 szerokości
    znaku (mediana w wierszu) — kolumny faktur są rozdzielone wyraźnie szerszym
    odstępem niż słowa w opisie. Działa dla słów z Tesseracta i z pdfplumber
    (PDF z warstwą tekstową, ale bez linii tabeli)."""
    text_lines, rows = [], []
    for ws in _group_lines(words):
        ws = sorted(ws, key=lambda w: w["left"])
        text_lines.append(" ".join(w["text"] for w in ws))
        char_widths = [w["width"] / max(len(w["text"]), 1) for w in ws]
        gap_limit = max(statistics.median(char_widths) * 2.5, 8.0)
        cells, current, prev_right = [], [], None
        for w in ws:
            if prev_right is not None and w["left"] - prev_right > gap_limit and current:
                cells.append(" ".join(current))
                current = []
            current.append(w["text"])
            prev_right = w["left"] + w["width"]
        if current:
            cells.append(" ".join(current))
        rows.append(cells)
    return "\n".join(text_lines), rows


def _cache_key(path: str, index: int) -> tuple:
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError:
        mtime = 0
    return (os.path.abspath(path), mtime, index, settings.ocr_lang, settings.ocr_dpi)


# własny cache zamiast lru_cache: splitter tnie zestaw na pliki części i te same strony
# trafiają do ekstraktora pod NOWĄ ścieżką — alias_page() przepisuje gotowy wynik OCR
# na nowy klucz, żeby żadna strona nie była czytana dwa razy
_CACHE_MAX = 512
_cache: OrderedDict = OrderedDict()
_cache_lock = threading.Lock()


def _cache_get(key: tuple) -> OcrPage | None:
    with _cache_lock:
        page = _cache.get(key)
        if page is not None:
            _cache.move_to_end(key)
        return page


def _cache_put(key: tuple, page: OcrPage) -> None:
    with _cache_lock:
        _cache[key] = page
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)


def vision_available() -> bool:
    from .. import llm
    return bool(settings.ocr_enabled and settings.ocr_vision_model and llm.is_configured())


_VISION_PROMPT = (
    "To skan strony dokumentu handlowego (faktura, packing list). Przepisz go wiernie. "
    "Zwróć WYŁĄCZNIE JSON: {\"text\": \"cały tekst strony, linia po linii\", "
    "\"rows\": [[\"komórka\", ...], ...]} — rows to tabela pozycji wiersz po wierszu "
    "łącznie z wierszem nagłówka, liczby dokładnie jak na dokumencie. Bez tabeli: rows = [].")


# AI-003: odpowiedź modelu obrazowego to dane z dokumentu dostawcy (treść skanu może nieść
# instrukcje — prompt injection). Przyjmujemy tylko ten kształt; cokolwiek poza nim (zły typ,
# nadmiar wierszy/kolumn/tekstu) = pusty wynik warstwy vision i wpis w logu. Nieznane klucze
# i „wiersze” niebędące listą (śmieć formatu) są pomijane — czytamy wyłącznie `text` i `rows`.
VISION_MAX_TEXT, VISION_MAX_ROWS, VISION_MAX_COLS, VISION_MAX_CELL = 20_000, 500, 30, 1_000
_VisionCell = (Annotated[str, StringConstraints(strict=True, max_length=VISION_MAX_CELL)]
               | StrictInt | StrictFloat | None)


class VisionPage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: Annotated[str, StringConstraints(strict=True, max_length=VISION_MAX_TEXT)] | None = None
    rows: Annotated[list[Annotated[list[_VisionCell], Field(max_length=VISION_MAX_COLS)]],
                    Field(max_length=VISION_MAX_ROWS)] | None = None

    @field_validator("rows", mode="before")
    @classmethod
    def _skip_non_list_rows(cls, value):
        if not isinstance(value, list):
            return value
        rows = [row for row in value if isinstance(row, list)]
        if len(rows) != len(value):
            logger.warning("OCR vision: pominięto %d wierszy niebędących listą",
                           len(value) - len(rows))
        return rows


def parse_vision(raw: str) -> tuple[str, list[list[str]]]:
    """Odpowiedź modelu → (tekst, wiersze) albo ("", []) + log, gdy wychodzi poza schemat."""
    try:
        page = VisionPage.model_validate_json(raw[raw.find("{"):raw.rfind("}") + 1])
    except ValidationError as exc:
        first = exc.errors()[0]
        logger.warning("OCR vision: odpowiedź modelu poza schematem — odrzucona (%d błędów, "
                       "np. %s przy %s)", exc.error_count(), first["type"],
                       ".".join(map(str, first["loc"])) or "-")
        return "", []
    rows = [["" if c is None else str(c) for c in row] for row in page.rows or []]
    return page.text or "", rows


def _vision(image) -> tuple[str, list[list[str]]]:
    """Strona → (tekst, wiersze) przez lokalny model obrazowy Ollamy — szew do testów."""
    import base64
    import io

    from .. import llm
    image = image.copy()
    image.thumbnail((1280, 1280))   # mały model na CPU: każdy piksel to czas i RAM
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    raw = llm.chat(settings.ocr_vision_model, _VISION_PROMPT, json_mode=True,
                   images=[base64.b64encode(buf.getvalue()).decode()],
                   # strona na CPU to minuty; OCR czeka na slot, nie oblewa strony, gdy asystent liczy
                   timeout=settings.ollama_timeout, wait=settings.ollama_timeout,
                   purpose="ocr_vision")
    return parse_vision(raw)


def ocr_page(path: str, index: int, vision: bool = True) -> OcrPage:
    """OCR strony (0-indeksowanej) warstwami: Tesseract → lokalny model obrazowy Ollamy (gdy Tesseract
    niedostępny albo nie dał czytelnego tekstu). Pusty OcrPage, gdy żadna warstwa nie dała.

    `vision=False` (budżet, audyt 2026-10-06 #3): klasyfikacja stron zestawu tylko Tesseractem —
    vision (minuty na stronę na CPU) dopiero przy ekstrakcji faktur/PL, nie dla certyfikatów."""
    tesseract, vision = is_available(), vision and vision_available()
    if not (tesseract or vision):
        return OcrPage()
    key = _cache_key(path, index)
    cached = _cache_get(key)
    if cached is not None and (cached.vision_tried or not vision or not needs_ocr(cached.text)):
        return cached
    # kopia (obiekt z cache współdzielą wątki); Tesseract już był — dokładamy tylko vision
    page = OcrPage(cached.text, list(cached.rows)) if cached is not None else OcrPage()
    if cached is not None:
        tesseract = False
    try:
        image = render_page(path, index)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR render %s s.%d: %s", os.path.basename(path), index + 1, exc)
        image = None
    # porażki też cache'ujemy: splitter i ekstraktor pytają o tę samą stronę, a timeout
    # tesseracta (90 s) ×2 × liczba stron zablokowałby wątek na godziny; ponowna próba
    # tylko jawnie (forget → /reprocess)
    source = "brak"   # AI-004: która warstwa dała tekst — do oceny, czy vision się opłaca
    for name, enabled, layer in (("tesseract", tesseract, lambda im: words_to_rows(_words(im))),
                                 ("vision", vision, _vision)):
        if image is None or not enabled or not needs_ocr(page.text):
            continue
        try:
            text, rows = layer(image)
            if len(text.split()) > len(page.text.split()):
                page, source = OcrPage(text=text, rows=rows), name
        except Exception as exc:  # noqa: BLE001 — OCR to best-effort; brak tekstu = skan „do ręki”
            logger.warning("OCR %s %s s.%d: %s", name, os.path.basename(path), index + 1, exc)
    page.vision_tried = vision   # także przy nieudanym renderze — bez ponawiania co wywołanie
    if image is not None:
        logger.info("OCR %s s.%d: warstwa %s, %d słów, %d wierszy", os.path.basename(path),
                    index + 1, source, len(page.text.split()), len(page.rows))
    _cache_put(key, page)
    return page


def forget(path: str) -> None:
    """Usuwa z cache wszystkie strony pliku — ponowna ekstrakcja (/reprocess) ma
    naprawdę spróbować OCR jeszcze raz (np. po chwilowym błędzie tesseracta)."""
    target = os.path.abspath(path)
    with _cache_lock:
        for key in [k for k in _cache if k[0] == target]:
            del _cache[key]


def alias_page(src_path: str, src_index: int, dst_path: str, dst_index: int) -> None:
    """Przepisuje wynik OCR strony pliku źródłowego na stronę pliku części (po cięciu)."""
    cached = _cache_get(_cache_key(src_path, src_index))
    if cached is not None:
        _cache_put(_cache_key(dst_path, dst_index), cached)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


# poniżej tego progu uznajemy warstwę tekstową za pustą (skan z samym numerem strony
# albo znakiem wodnym) — liczymy słowa, nie znaki, bo watermark „CONFIDENTIAL DRAFT COPY”
# ma 25 znaków, a żadnej treści
TEXT_LAYER_MIN_WORDS = 8


def needs_ocr(text: str) -> bool:
    return len((text or "").split()) < TEXT_LAYER_MIN_WORDS


def pdf_words(page) -> list[dict]:
    """Słowa strony pdfplumber w formacie words_to_rows (PDF z tekstem, ale bez linii
    tabeli — extract_tables() nic nie zwraca, a pozycje słów wystarczą do odtworzenia kolumn)."""
    out = []
    for w in page.extract_words(keep_blank_chars=False, use_text_flow=False):
        text = (w.get("text") or "").strip()
        if not text:
            continue
        out.append({"left": float(w["x0"]), "top": float(w["top"]),
                    "width": max(float(w["x1"]) - float(w["x0"]), 0.1),
                    "height": max(float(w["bottom"]) - float(w["top"]), 0.1), "text": text})
    return out

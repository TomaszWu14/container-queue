# Agencja: draft SAD — PR 2 (odczyt PDF + porównanie z fakturami) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przy każdej wersji draftu SAD przycisk „Porównaj” otwiera okno: nagłówek (faktury, waluta, suma, kraj) i grupy CN „nasze ↔ SAD” ze statusem, a obok strony PDF — z tolerancjami profilu dostawcy; pole nieodczytane jest jawne, nigdy zgadywane.

**Architecture:** Trzy moduły domeny w `app/invoices/`: `sad_parse.py` (tekst PDF → pola SAD, bez bazy), `sad_ours.py` (paczka faktur → grupy CN, z bazy), `sad_compare.py` (czysta funkcja: nasze + SAD → wynik). Orkiestracja w istniejącym `sad_drafts.py`: odczyt raz (cache w nowej kolumnie `sad_drafts.parsed`, odświeżany po zmianie `PARSER_VERSION`), porównanie zawsze z bieżącymi pozycjami, wynik w `sad_drafts.comparison` (PR 3 weźmie z niego rozbieżności do maila). Dwie nowe trasy w `routers/sad_drafts.py`: `POST …/compare` i `GET …/pages/{n}` (PNG strony). Front: `SadCompareModal` otwierany z `AgencySadSection`.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, pdfplumber / pypdfium2 (już w zależnościach), pytest (+xdist), React + TypeScript, Vitest.

Spec: `docs/superpowers/specs/2026-09-29-agencja-draft-sad-design.md` (§2). PR 1: `docs/superpowers/plans/2026-09-29-agencja-draft-sad-pr1.md`.

## Global Constraints

- Max **500 linii** na plik (`scripts/check_file_lengths.py`, BASELINE pusty).
- Teksty UI tylko w **`frontend/src/i18n/features/agencja-sad.ts`** (plik funkcji z PR 1).
- Każda nowa trasa API → wpis w **`tests/permissions.yaml`** (sekcja `# --- invoice_agency ---`, jak trasy PR 1).
- Migracja od jedynej głowy — dziś **`sad001`** (sprawdź przed pisaniem: `grep -l 'down_revision = "sad001"' backend/migrations/versions/` ma być puste). Nowe kolumny także w dev-shimie `ensure_new_columns()` (`backend/app/db_bootstrap.py`), test `test_dev_schema_shim.py`.
- **ARCH-001**: moduły `app/invoices/*` nie importują `app.routers.*` (`tests/test_architecture_imports.py`).
- Ruff: `except Exception:` tylko z `# noqa: BLE001 — powód` (konwencja `ingest.py`); złożoność ≤ 20 (C90).
- Front: ikony z `lucide-react` (strażnik `icons.emoji.test.ts` zabrania ✗/⚠/✅; „✓” dozwolone); `<img>` z `width`, `height`, `loading` (`images.test.ts`); `<table className="grid">`; bez kolorów hex (tylko `var(--…)`); `formatNum` z `./dates` zamiast `toLocaleString`.
- Uwaga testowa: `invoices.dom.test.tsx` / `invoices.polling.dom.test.tsx` mockują `./dates` tylko z `formatDateTime` i renderują `AgencySadSection` — nowe importy z `./dates` wolno używać tylko w kodzie wykonywanym po otwarciu okna porównania (nie przy renderze sekcji).
- Pełny pytest przed pushem: `python -m pytest tests/ -q -n auto` (z `backend/`, Python 3.12); pełny vitest: `npx vitest run` + `npx tsc -b --noEmit` (z `frontend/`).
- Mypy baseline (`scripts/mypy_baseline.py`): nowe pliki bez błędów.

## Decyzje projektowe (w tym PR)

1. **Odczyt przy pierwszym „Porównaj”, nie przy wgraniu.** Wgranie zostaje szybkie (także dla automatu z PR 4); skan idzie przez OCR (1–3 s/stronę) tylko raz — wynik w `parsed`. Zmiana wzorców = podbicie `PARSER_VERSION` → zapisane odczyty odświeżą się same.
2. **Parser „etykieta: wartość” z opcjonalnym numerem rubryki** (`38 Masa netto (kg): 12,500`). Bez próbki od agencji nie zgadujemy układu kratek — to PR 5 (dostrojenie do draftu Deltaa). Czego nie odczytano, to trafia do `unread`, a status grupy to „sprawdź ręcznie”.
3. **Numery faktur (rubryka 44)**: szukamy naszych numerów w całym tekście draftu (bez spacji/znaków) — odporne na format rubryki.
4. **Masa netto**: tolerancja `tol_qty_pct` z profilu **albo ±1 kg** (zgłoszenie podaje kg zaokrąglone; domyślne `tol_qty_pct = 0` inaczej dawałoby fałszywe alarmy).
5. **J. uzupełniające (41)**: porównywane tylko, gdy nasz materiał ma `suppl_unit` + `suppl_factor` (jedyny sygnał „CN tego wymaga”); grupa z materiałem bez przelicznika → „sprawdź ręcznie”.
6. **Waluta**: nasza z profilu dostawcy (`SupplierDocProfile.currency`) — faktury jej nie przechowują; brak = nie porównujemy (znak „?”).
7. **Kraj**: rubryka 15a (wysyłka) ↔ `Supplier.country`; kraj pochodzenia (34a) pokazany informacyjnie.
8. **Koszty dodatkowe** (`check_data.charges`) wchodzą do sumy nagłówka (jak Excel); grupy CN porównują same pozycje.
9. **PDF obok = obrazki PNG stron** renderowane na serwerze (`ocr.render_page`, pypdfium2): nagłówki bezpieczeństwa (`X-Frame-Options: DENY`, CSP bez `frame-src`/`blob:`) blokują `iframe`/`object`; `<img src="/api/…">` działa (cookie, `img-src 'self'`) — jak zdjęcia reklamacji.

## File Structure

| Plik | Odpowiedzialność |
|---|---|
| `backend/app/models/sad_drafts.py` | + kolumny `parsed`, `comparison` (JSON) |
| `backend/migrations/versions/sad002_draft_sad_odczyt.py` (nowy) | dwie kolumny JSON w `sad_drafts` |
| `backend/app/db_bootstrap.py` | dev-shim: te same kolumny |
| `backend/app/invoices/sad_parse.py` (nowy) | tekst PDF → pola SAD; liczba stron i PNG strony |
| `backend/app/invoices/sad_ours.py` (nowy) | paczka faktur → nagłówek + grupy CN |
| `backend/app/invoices/sad_compare.py` (nowy) | porównanie (czysta funkcja) |
| `backend/app/invoices/sad_drafts.py` | `compare_draft`, `page_png`, `summary` w `state` |
| `backend/app/routers/sad_drafts.py` | `POST …/compare`, `GET …/pages/{page}` |
| `tests/permissions.yaml` | 2 wpisy |
| `backend/tests/test_sad_parse.py`, `test_sad_compare.py` (nowe), `test_sad_drafts.py` | testy |
| `frontend/src/types/invoices.ts` | typy porównania |
| `frontend/src/SadCompareModal.tsx` + `.css` + `.dom.test.tsx` (nowe) | okno porównania |
| `frontend/src/AgencySadSection.tsx` (+ test) | przycisk „Porównaj”, podsumowanie, kolory decyzji |
| `frontend/src/i18n/features/agencja-sad.ts` | teksty PL/EN/PT |

**Kolejność:** Task 1 → (Task 2, 3, 4, 6 niezależne — równolegle) → Task 5 → Task 7.

---

### Task 1: Kolumny `parsed` / `comparison` + migracja `sad002`

**Files:**
- Modify: `backend/app/models/sad_drafts.py`
- Create: `backend/migrations/versions/sad002_draft_sad_odczyt.py`
- Modify: `backend/app/db_bootstrap.py` (`ensure_new_columns`)
- Test: `backend/tests/test_migration_chain.py`, `backend/tests/test_dev_schema_shim.py` (istniejące)

- [ ] **Step 1: Model** — w `backend/app/models/sad_drafts.py` dopisz `JSON` do importu z `sqlalchemy` i w klasie `SadDraft` przed `attachment`:
```python
    # PR 2: odczyt PDF (invoices/sad_parse) i ostatni wynik porównania (invoices/sad_compare)
    parsed: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    comparison: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 2: Migracja** `backend/migrations/versions/sad002_draft_sad_odczyt.py`:
```python
"""Draft SAD: dane odczytane z PDF i wynik porównania z fakturami (JSON).

Revision ID: sad002
Revises: sad001
"""
import sqlalchemy as sa
from alembic import op

revision = "sad002"
down_revision = "sad001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sad_drafts", sa.Column("parsed", sa.JSON, nullable=True))
    op.add_column("sad_drafts", sa.Column("comparison", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("sad_drafts", "comparison")
    op.drop_column("sad_drafts", "parsed")
```

- [ ] **Step 3: Dev-shim** — w `ensure_new_columns()` (`backend/app/db_bootstrap.py`, słownik tabel obok `'supplier_doc_samples'`) dopisz:
```python
        # draft SAD: odczyt PDF i porównanie (migracja sad002)
        'sad_drafts': {'parsed': "JSON", 'comparison': "JSON"},
```

- [ ] **Step 4: Weryfikacja** (z `backend/`): `python -c "import app.main" && python -m pytest tests/test_migration_chain.py tests/test_dev_schema_shim.py -q` → PASS (jedna głowa `sad002`).

- [ ] **Step 5: Commit**
```bash
git add backend/app/models/sad_drafts.py backend/migrations/versions/sad002_draft_sad_odczyt.py backend/app/db_bootstrap.py
git commit -m "feat(agencja): kolumny odczytu i porównania draftu SAD + migracja sad002"
```

---

### Task 2: Odczyt draftu SAD (`app/invoices/sad_parse.py`)

**Files:**
- Create: `backend/app/invoices/sad_parse.py`
- Test: `backend/tests/test_sad_parse.py`

**Interfaces:**
- Consumes: `extractor.read_pages(path) -> list[PageData]` (`.text`, `.ocr`); `ocr.render_page(path, index, dpi)`; `normalize_number(raw, prefer_decimal=True)`.
- Produces:
  - `PARSER_VERSION: int`
  - `parse_text(pages: list[str]) -> dict` — `{"v", "layout", "currency", "total", "country_dispatch", "country_origin", "items": [{"no", "cn", "value", "net_mass", "suppl_qty", "origin"}], "text", "error": None | "no_text", "unread": [{"item": int | None, "field": str}]}`; liczby jako znormalizowany tekst (`"1205.5"`) albo `None`.
  - `parse_file(path: str) -> dict` — jak wyżej + `"pages": int`, `"ocr": bool`; nie-PDF → `"error": "unreadable_pdf"` (bez wyjątku).
  - `page_count(path: str) -> int` (0 dla uszkodzonego pliku), `page_png(path: str, index: int) -> bytes`.

- [ ] **Step 1: Test (czerwony)** `backend/tests/test_sad_parse.py`:
```python
"""Odczyt draftu SAD (PR 2, spec 2026-09-29-agencja-draft-sad §2): etykiety rubryk → pola,
pozycje od „Kod towaru”, pole nieodczytane jawnie w `unread`, brak tekstu / nie-PDF → błąd
zamiast zgadywania."""
from pypdf import PdfWriter

from app.invoices import extractor, sad_parse
from app.invoices.extractor import PageData

SAD = """ZGŁOSZENIE CELNE — DRAFT
15a Kod kraju wysyłki/eksportu: CN
22 Waluta i całkowita kwota fakturowana: USD 1 205,50
44 Dodatkowe informacje/Przedstawione dokumenty: N380 T-1; N380 T-2
Pozycja 1
33 Kod towaru: 9018 39 00 00
34a Kod kraju pochodzenia: CN
38 Masa netto (kg): 12,500
42 Cena pozycji: 950,00
Pozycja 2
33 Kod towaru: 40151900
38 Masa netto (kg): 3
41 Jednostki uzupełniające: 775
42 Cena pozycji: 255,50
"""


def test_parse_text_reads_header_and_items():
    out = sad_parse.parse_text([SAD])
    assert (out["currency"], out["total"]) == ("USD", "1205.5")
    assert (out["country_dispatch"], out["country_origin"]) == ("CN", "CN")
    assert [(i["cn"], i["value"], i["net_mass"], i["suppl_qty"]) for i in out["items"]] == [
        ("90183900", "950", "12.5", None), ("40151900", "255.5", "3", "775")]
    assert out["unread"] == [] and out["error"] is None and "T-2" in out["text"]


def test_unread_fields_are_explicit_never_guessed():
    out = sad_parse.parse_text(["33 Kod towaru: 90183900\n42 Cena pozycji: 10,00\n"])
    assert out["total"] is None and out["items"][0]["net_mass"] is None
    assert {"item": None, "field": "total"} in out["unread"]
    assert {"item": 1, "field": "net_mass"} in out["unread"]
    assert sad_parse.parse_text([""])["error"] == "no_text"
    reversed_order = sad_parse.parse_text(["22 Waluta i całkowita kwota fakturowana 1 305,50 EUR"])
    assert (reversed_order["currency"], reversed_order["total"]) == ("EUR", "1305.5")


def test_parse_file_pages_ocr_flag_and_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(extractor, "read_pages",
                        lambda path: [PageData(text=SAD), PageData(text="", ocr=True)])
    out = sad_parse.parse_file("draft.pdf")
    assert out["pages"] == 2 and out["ocr"] is True and len(out["items"]) == 2
    monkeypatch.undo()
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"to nie jest PDF")
    broken = sad_parse.parse_file(str(bad))
    assert broken["error"] == "unreadable_pdf" and broken["pages"] == 0
    assert sad_parse.page_count(str(bad)) == 0


def test_page_png_renders_real_pdf(tmp_path):
    path = tmp_path / "draft.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as fh:
        writer.write(fh)
    assert sad_parse.page_count(str(path)) == 1
    assert sad_parse.page_png(str(path), 0).startswith(b"\x89PNG")
```

Run (z `backend/`): `python -m pytest tests/test_sad_parse.py -q` → FAIL (`ImportError: sad_parse`).

- [ ] **Step 2: Implementacja** `backend/app/invoices/sad_parse.py`:
```python
"""Odczyt draftu SAD (PDF od agencji celnej) → pola do porównania z fakturami (spec
2026-09-29-agencja-draft-sad §2, PR 2).

Tekst jak faktury: `extractor.read_pages` (strona bez warstwy tekstowej → OCR). Pola po
etykietach rubryk z opcjonalnym numerem w układzie „etykieta: wartość” w jednej linii
(„38 Masa netto (kg): 12,500”). Programy agencji drukują drafty różnie — PR 5 dostroi wzorce
do draftu Deltaa (`layout`). Pole nieodczytane trafia do `unread`, nigdy nie zgadujemy.
Liczby w formacie polskim (przecinek dziesiętny) → `prefer_decimal`."""
import io
import logging
import re
from decimal import Decimal

from . import extractor
from .numbers import normalize_number

logger = logging.getLogger(__name__)

PARSER_VERSION = 1       # zmiana wzorców → podbij: zapisane odczyty (`SadDraft.parsed`) się odświeżą
TEXT_KEEP = 20000        # tekst do szukania numerów faktur (rubryka 44) przy porównaniu
PREVIEW_DPI = 110        # podgląd stron w oknie porównania
HEADER_FIELDS = ("currency", "total", "country_dispatch")
ITEM_REQUIRED = ("value", "net_mass")

_SEP = r"[ \t]*[:.]?[ \t]*"
# „1 205,50” (grupy tysięcy spacją) albo zwarta liczba „950,00” / „12.500”
_NUM = r"(\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|\d[\d.,]*)"
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


def _unread(out: dict) -> list[dict]:
    missing = [{"item": None, "field": f} for f in HEADER_FIELDS if not out[f]]
    if not out["items"]:
        missing.append({"item": None, "field": "items"})
    return missing + [{"item": i["no"], "field": f}
                      for i in out["items"] for f in ITEM_REQUIRED if i[f] is None]


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
    out = {"v": PARSER_VERSION, "layout": "generic", "currency": currency, "total": total,
           "country_dispatch": _country(_DISPATCH, text),
           "country_origin": next((i["origin"] for i in items if i["origin"]), None),
           "items": items, "text": text[:TEXT_KEEP],
           "error": None if text.strip() else "no_text"}
    out["unread"] = _unread(out)
    return out


def parse_file(path: str) -> dict:
    """Odczyt pliku; uszkodzony / nie-PDF → wynik z `error` zamiast wyjątku (porównanie ręczne)."""
    try:
        pages = extractor.read_pages(path)
    except Exception:  # noqa: BLE001 — każdy błąd biblioteki PDF = „nie da się odczytać”
        logger.warning("draft SAD: nie da się odczytać %s", path, exc_info=True)
        return {**parse_text([]), "error": "unreadable_pdf", "pages": 0, "ocr": False}
    out = parse_text([page.text for page in pages])
    out.update(pages=len(pages), ocr=any(page.ocr for page in pages))
    return out


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
```

- [ ] **Step 3:** `python -m pytest tests/test_sad_parse.py -q` → PASS (4). `python -m ruff check app/invoices/sad_parse.py tests/test_sad_parse.py` → czysto.

- [ ] **Step 4: Commit**
```bash
git add backend/app/invoices/sad_parse.py backend/tests/test_sad_parse.py
git commit -m "feat(agencja): odczyt draftu SAD z PDF (etykiety rubryk, pola nieodczytane jawnie)"
```

---

### Task 3: Nasza strona — paczka faktur w grupach CN (`app/invoices/sad_ours.py`)

**Files:**
- Create: `backend/app/invoices/sad_ours.py`
- Test: `backend/tests/test_sad_compare.py` (pierwszy test pliku; Task 4 dopisze resztę)

**Interfaces:**
- Consumes: `effective`, `get_material`, `load_conversions` (`matching.py`); `cn_codes` (`symbols.py`); `_to_base`, `DEFAULT_TOL_AMOUNT`, `DEFAULT_TOL_QTY` (`checks.py`); `INVOICE_LIKE_KINDS`, `InvoiceJobStatus` (`app.models`).
- Produces: `batch_side(db, batch) -> dict`:
  `{"invoices": [str], "currency": str, "total": str, "charges": str, "country": str, "groups": {cn8: {"cn", "value", "net_mass": str | None, "suppl_qty": str | None, "suppl_unit": str, "refs": [str]}}, "no_cn": [str], "tol_amount_pct": float, "tol_qty_pct": float}`; `confirmed_jobs(batch) -> list[InvoiceJob]`.

- [ ] **Step 1: Test (czerwony)** — utwórz `backend/tests/test_sad_compare.py`:
```python
"""Porównanie draftu SAD z paczką faktur (PR 2, spec 2026-09-29-agencja-draft-sad §2):
nasza strona w grupach CN (kartoteka, wagi, j. uzupełniające, koszty dodatkowe) i reguły
porównania — zgodne, rozbieżny CN / wartość / masa, brakujące i nadmiarowe CN, nieodczytane."""
import copy

from sqlalchemy import select

from app.invoices import sad_ours
from app.models import (Company, InvoiceBatch, InvoiceDocKind, InvoiceItem, InvoiceJob,
                        InvoiceJobStatus, Material, Supplier, SupplierDocProfile)
from tests.test_invoices_api import _container


def test_batch_side_groups_by_cn(client, admin_headers, db_session):
    company = db_session.scalars(select(Company)).first()
    sup = Supplier(name="Acme SAD", country="cn")
    sup.doc_profile = SupplierDocProfile(status="draft", currency="usd",
                                         tol_amount_pct=1.0, tol_qty_pct=2.0)
    db_session.add_all([
        sup,
        Material(ref_code="A1", ref_norm="A1", base_uom="SZT", tariff_cn="4015 19 00",
                 suppl_unit="pary", suppl_factor=0.5),
        Material(ref_code="B2", ref_norm="B2", base_uom="SZT", tariff_cn="40151900",
                 suppl_unit="pary", suppl_factor=1.0),
        Material(ref_code="C3", ref_norm="C3", base_uom="SZT", tariff_cn="")])
    db_session.commit()
    cid = _container(client, admin_headers, company_id=company.id, supplier_id=sup.id)
    batch = InvoiceBatch(container_id=cid, supplier_id=sup.id)
    db_session.add(batch)
    db_session.flush()
    job = InvoiceJob(batch_id=batch.id, filename="ci.pdf", stored_name="ci.pdf",
                     status=InvoiceJobStatus.confirmed, invoice_number="T-1",
                     check_data={"charges": [{"desc": "freight", "amount": "100.00"}]})
    packing = InvoiceJob(batch_id=batch.id, filename="pl.pdf", stored_name="pl.pdf",
                         doc_kind=InvoiceDocKind.packing_list, status=InvoiceJobStatus.packing_list)
    db_session.add_all([job, packing])
    db_session.flush()
    db_session.add_all([
        InvoiceItem(job_id=job.id, line_no=1, raw_ref="A1", master_ref="A1", qty="100",
                    amount="1,000.00", weight_net="12,500"),
        InvoiceItem(job_id=job.id, line_no=2, raw_ref="A1", master_ref="A1", qty="50",
                    amount="500.00"),                         # waga REF tylko na 1. linii (PL)
        InvoiceItem(job_id=job.id, line_no=3, raw_ref="B2", master_ref="B2", qty="10",
                    amount="55.50", weight_net="1"),
        InvoiceItem(job_id=job.id, line_no=4, raw_ref="C3", master_ref="C3", qty="1", amount="5"),
        InvoiceItem(job_id=job.id, line_no=5, raw_ref="X9", qty="1", amount="999", skipped=True)])
    db_session.commit()

    ours = sad_ours.batch_side(db_session, db_session.get(InvoiceBatch, batch.id))
    assert (ours["invoices"], ours["currency"], ours["country"]) == (["T-1"], "USD", "CN")
    assert (ours["total"], ours["charges"]) == ("1660.5", "100")     # pozycje + koszty, bez pominiętej
    assert ours["no_cn"] == ["C3"] and (ours["tol_amount_pct"], ours["tol_qty_pct"]) == (1.0, 2.0)
    assert ours["groups"] == {"40151900": {
        "cn": "40151900", "value": "1555.5", "net_mass": "13.5", "suppl_qty": "85",
        "suppl_unit": "pary", "refs": ["A1", "B2"]}}
```

Run: `python -m pytest tests/test_sad_compare.py -q` → FAIL (`ImportError: sad_ours`).

- [ ] **Step 2: Implementacja** `backend/app/invoices/sad_ours.py`:
```python
"""Nasza strona porównania z draftem SAD (spec 2026-09-29-agencja-draft-sad §2, PR 2): paczka
faktur zsumowana w grupy CN — agencja łączy pozycje po kodzie towaru.

Źródła jak Excel i mail do agencji: pozycje zatwierdzonych faktur/proform bez pominiętych.
CN świeżo z kartoteki (`effective` + `cn_codes`); `InvoiceItem.tariff_cn` to migawka z chwili
dopasowania — tylko gdy materiału brak. Masa netto = suma wag pozycji (PL wpisuje wagę REF na
jego pierwszą linię); REF bez żadnej wagi = masa grupy nieznana. J. uzupełniające = ilość
w j. podstawowej × `Material.suppl_factor`, gdy materiał ma `suppl_unit`."""
import re
from decimal import Decimal

from sqlalchemy.orm import Session

from ..models import (INVOICE_LIKE_KINDS, InvoiceBatch, InvoiceItem, InvoiceJob,
                      InvoiceJobStatus, Material)
from .checks import DEFAULT_TOL_AMOUNT, DEFAULT_TOL_QTY, _to_base
from .matching import effective, get_material, load_conversions
from .numbers import normalize_number
from .symbols import cn_codes


def _num(raw, weight: bool = False) -> Decimal | None:
    return normalize_number(raw, prefer_decimal=weight) if raw not in (None, "") else None


def _text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def confirmed_jobs(batch: InvoiceBatch) -> list[InvoiceJob]:
    """Dokumenty wysłane agencji — ten sam wybór co Excel i szkic maila."""
    return [j for j in batch.jobs
            if j.doc_kind in INVOICE_LIKE_KINDS and j.status == InvoiceJobStatus.confirmed]


class _Groups:
    """Akumulator grup CN: reguły jednej pozycji w `add`, podsumowanie w `result`."""

    def __init__(self, db: Session, company_id: int | None) -> None:
        self.db, self.company_id = db, company_id
        self.conversions = load_conversions(db)
        self.materials: dict[str, Material | None] = {}
        self.groups: dict[str, dict] = {}
        self.weighed: dict[str, bool] = {}
        self.no_cn: set[str] = set()

    def _material(self, ref: str) -> Material | None:
        if ref not in self.materials:
            self.materials[ref] = get_material(self.db, ref)
        return self.materials[ref]

    def add(self, item: InvoiceItem, amount: Decimal) -> None:
        ref = item.master_ref or item.raw_ref
        material = self._material(item.master_ref)
        view = effective(material, self.company_id) if material else None
        cn = (cn_codes(view["tariff_cn"], view["customs_code"])[0] if view
              else re.sub(r"\D", "", item.tariff_cn or "")[:8])
        if len(cn) != 8:
            self.no_cn.add(ref)
            return
        group = self.groups.setdefault(cn, {"value": Decimal(0), "net_mass": Decimal(0),
                                            "suppl_qty": Decimal(0), "suppl_unit": "",
                                            "suppl_missing": False, "refs": set()})
        group["value"] += amount
        group["refs"].add(ref)
        weight = _num(item.weight_net, weight=True)
        group["net_mass"] += weight or Decimal(0)
        self.weighed[ref] = self.weighed.get(ref, False) or weight is not None
        self._suppl(group, item, material, view, ref)

    def _suppl(self, group: dict, item: InvoiceItem, material: Material | None,
               view: dict | None, ref: str) -> None:
        if material is None or view is None or not material.suppl_unit or not material.suppl_factor:
            group["suppl_missing"] = True     # w grupie z j. uzupełniającą ten REF jej nie ma
            return
        group["suppl_unit"] = material.suppl_unit
        base = _to_base(_num(item.qty) or Decimal(0), item.uom_src, view["base_uom"], ref,
                        self.conversions)
        if base is None:
            group["suppl_missing"] = True
        else:
            group["suppl_qty"] += base * Decimal(str(material.suppl_factor))

    def result(self) -> dict[str, dict]:
        out = {}
        for cn, group in sorted(self.groups.items()):
            unit = group["suppl_unit"]
            weighed = all(self.weighed[ref] for ref in group["refs"])
            out[cn] = {"cn": cn, "value": _text(group["value"]),
                       "net_mass": _text(group["net_mass"]) if weighed else None,
                       "suppl_qty": _text(group["suppl_qty"])
                       if unit and not group["suppl_missing"] else None,
                       "suppl_unit": unit, "refs": sorted(group["refs"])}
        return out


def batch_side(db: Session, batch: InvoiceBatch) -> dict:
    """Paczka faktur jako nagłówek + grupy CN (liczone z bieżących pozycji przy każdym porównaniu)."""
    container = batch.container
    supplier = batch.supplier or (container.supplier if container else None)
    profile = supplier.doc_profile if supplier else None
    jobs = confirmed_jobs(batch)
    acc = _Groups(db, container.company_id if container else None)
    total = charges = Decimal(0)
    for job in jobs:
        for charge in (job.check_data or {}).get("charges") or []:
            charges += _num(charge.get("amount")) or Decimal(0)
        for item in job.items:
            if item.skipped:
                continue
            amount = _num(item.amount) or Decimal(0)
            total += amount
            acc.add(item, amount)
    return {"invoices": sorted({j.invoice_number for j in jobs if j.invoice_number}),
            "currency": (profile.currency or "").upper() if profile else "",
            "total": _text(total + charges), "charges": _text(charges),
            "country": (supplier.country or "").upper() if supplier else "",
            "groups": acc.result(), "no_cn": sorted(acc.no_cn),
            "tol_amount_pct": profile.tol_amount_pct if profile else DEFAULT_TOL_AMOUNT,
            "tol_qty_pct": profile.tol_qty_pct if profile else DEFAULT_TOL_QTY}
```
Sprawdź przed implementacją: `Container.supplier` (relacja — używana w `routers/invoice_agency.py`), `Material.is_active` domyślnie `True` (inaczej `get_material` nie znajdzie materiału z testu), sygnatura `_container` w `tests/test_invoices_api.py`.

- [ ] **Step 3:** `python -m pytest tests/test_sad_compare.py -q` → PASS (1).

- [ ] **Step 4: Commit**
```bash
git add backend/app/invoices/sad_ours.py backend/tests/test_sad_compare.py
git commit -m "feat(agencja): paczka faktur w grupach CN — nasza strona porównania z SAD"
```

---

### Task 4: Porównanie (`app/invoices/sad_compare.py`)

**Files:**
- Create: `backend/app/invoices/sad_compare.py`
- Test: `backend/tests/test_sad_compare.py` (dopisz)

**Interfaces:**
- Consumes: wynik `sad_ours.batch_side` (Task 3) i `sad_parse.parse_text/parse_file` (Task 2) — w testach słowniki syntetyczne; `_cmp`, `_num`, `_s` (`checks.py`).
- Produces: `compare(ours: dict, parsed: dict) -> dict`:
  - `header`: 4 wiersze `{"field": "invoices"|"currency"|"total"|"country", "ours": str, "sad": str | None, "diff_pct": float | None, "ok": bool | None, "detail": str}` (`ok is None` = nie da się sprawdzić automatycznie; `detail`: brakujące faktury / koszty dodatkowe / kraj pochodzenia);
  - `groups`: `{"cn", "status": "ok"|"diff"|"manual"|"missing_in_sad"|"extra_in_sad", "refs", "sad_items", "suppl_unit", "value": F, "net_mass": F, "suppl_qty": F | None}`, gdzie `F = {"ours", "sad", "diff_pct", "ok"}`;
  - `no_cn`, `unread`, `error`, `tolerances: {"amount_pct", "qty_pct", "mass_abs_kg"}`, `summary: {"groups", "ok", "diff", "manual", "all_ok"}`.

- [ ] **Step 1: Test (czerwony)** — dopisz do `backend/tests/test_sad_compare.py` (import `sad_compare`, `sad_parse` i `SAD` na górze pliku):
```python
from app.invoices import sad_compare, sad_parse
from tests.test_sad_parse import SAD

OURS = {"invoices": ["T-1", "T-2"], "currency": "USD", "total": "1205.5", "charges": "0",
        "country": "CN", "no_cn": [], "tol_amount_pct": 0.5, "tol_qty_pct": 0.0,
        "groups": {"90183900": {"cn": "90183900", "value": "950", "net_mass": "12.5",
                                "suppl_qty": None, "suppl_unit": "", "refs": ["NL753"]},
                   "40151900": {"cn": "40151900", "value": "255.5", "net_mass": "3",
                                "suppl_qty": "775", "suppl_unit": "pary", "refs": ["A1"]}}}


def _statuses(result: dict) -> dict:
    return {g["cn"]: g["status"] for g in result["groups"]}


def test_all_matching():
    result = sad_compare.compare(OURS, sad_parse.parse_text([SAD]))
    assert result["summary"] == {"groups": 2, "ok": 2, "diff": 0, "manual": 0, "all_ok": True}
    assert [h["ok"] for h in result["header"]] == [True, True, True, True]


def test_discrepancies_value_missing_extra_invoice():
    ours = copy.deepcopy(OURS)
    ours["invoices"].append("T-3")
    ours["groups"]["90183900"].update(value="900", net_mass="12")    # masa: 0,5 kg = w ±1 kg
    ours["groups"]["84713000"] = {"cn": "84713000", "value": "10", "net_mass": "1",
                                  "suppl_qty": None, "suppl_unit": "", "refs": ["Z9"]}
    del ours["groups"]["40151900"]
    result = sad_compare.compare(ours, sad_parse.parse_text([SAD]))
    assert _statuses(result) == {"40151900": "extra_in_sad", "84713000": "missing_in_sad",
                                 "90183900": "diff"}
    row = next(g for g in result["groups"] if g["cn"] == "90183900")
    assert row["value"]["ok"] is False and row["net_mass"]["ok"] is True
    assert result["header"][0]["ok"] is False and result["header"][0]["detail"] == "T-3"
    assert result["summary"]["all_ok"] is False


def test_mass_beyond_one_kg_and_charges_in_header_total():
    ours = copy.deepcopy(OURS)
    ours["groups"]["90183900"]["net_mass"] = "14"
    assert _statuses(sad_compare.compare(ours, sad_parse.parse_text([SAD])))["90183900"] == "diff"
    ours = copy.deepcopy(OURS)
    ours.update(total="1305.5", charges="100")                      # koszty dodatkowe w sumie
    header = sad_compare.compare(ours, sad_parse.parse_text(
        [SAD.replace("USD 1 205,50", "USD 1 305,50")]))["header"]
    assert header[2]["ok"] is True and header[2]["detail"] == "100"
    assert sad_compare.compare(ours, sad_parse.parse_text([SAD]))["header"][2]["ok"] is False


def test_unread_or_missing_data_means_manual_check():
    ours = copy.deepcopy(OURS)
    ours["groups"]["90183900"]["net_mass"] = None                    # REF bez wagi po naszej stronie
    parsed = sad_parse.parse_text([SAD.replace("41 Jednostki uzupełniające: 775\n", "")])
    result = sad_compare.compare(ours, parsed)
    assert _statuses(result) == {"40151900": "manual", "90183900": "manual"}
    assert result["summary"]["manual"] == 2 and result["summary"]["all_ok"] is False
```

Run: `python -m pytest tests/test_sad_compare.py -q` → FAIL (`ImportError: sad_compare`).

- [ ] **Step 2: Implementacja** `backend/app/invoices/sad_compare.py`:
```python
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


def _norm(text: str | None) -> str:
    return re.sub(r"[^0-9A-Z]", "", (text or "").upper())


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
        side, key = (ours, "ours") if sad is None else (sad, "sad")
        assert side is not None
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
    text = _norm(parsed.get("text"))
    missing = [n for n in ours["invoices"] if _norm(n) not in text]
    currency = parsed.get("currency")
    total = _field(parsed.get("total"), ours["total"], ours["tol_amount_pct"])
    dispatch = parsed.get("country_dispatch")
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
```

- [ ] **Step 3:** `python -m pytest tests/test_sad_compare.py tests/test_sad_parse.py -q` → PASS; `python -m ruff check app/invoices/sad_compare.py` → czysto (bez `assert` w kodzie produkcyjnym, jeśli ruff/bandit go zgłosi — zastąp jawnym `if side is None: raise ValueError`).

- [ ] **Step 4: Commit**
```bash
git add backend/app/invoices/sad_compare.py backend/tests/test_sad_compare.py
git commit -m "feat(agencja): porównanie draftu SAD z fakturami w grupach CN z tolerancjami profilu"
```

---

### Task 5: Orkiestracja + trasy HTTP + macierz uprawnień

**Files:**
- Modify: `backend/app/invoices/sad_drafts.py`
- Modify: `backend/app/routers/sad_drafts.py`
- Modify: `tests/permissions.yaml`
- Test: `backend/tests/test_sad_drafts.py` (dopisz), `backend/tests/test_permissions_matrix.py`

**Interfaces:**
- Consumes: Task 1–4.
- Produces (HTTP, używane przez front w Task 6):
  - `POST /api/invoice-batches/{batch_id}/sad-drafts/{draft_id}/compare` → `{"draft_id", "version", "pages", "at", **compare(...)}`; 404 obcy draft; 410 brak pliku.
  - `GET /api/invoice-batches/{batch_id}/sad-drafts/{draft_id}/pages/{page}` → `image/png` (1-indeksowane; poza zakresem 404).
  - `GET …/sad-drafts` — każdy draft ma dodatkowo `"summary"` (z ostatniego porównania albo `null`).

- [ ] **Step 1: Test (czerwony)** — dopisz do `backend/tests/test_sad_drafts.py`:
```python
from app.invoices import extractor
from app.invoices.extractor import PageData
from tests.test_sad_parse import SAD


def test_compare_parses_once_and_keeps_summary(client, admin_headers, db_session,
                                               monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    calls = []
    monkeypatch.setattr(extractor, "read_pages",
                        lambda path: calls.append(path) or [PageData(text=SAD)])
    _, bid = _batch(client, admin_headers, db_session)
    v1 = _upload(client, admin_headers, bid, _pdf("v1")).json()["draft"]["id"]
    url = f"/api/invoice-batches/{bid}/sad-drafts/{v1}/compare"
    first = client.post(url, headers=admin_headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["pages"] == 1 and body["version"] == 1 and body["at"]
    assert {g["status"] for g in body["groups"]} == {"extra_in_sad"}   # paczka bez faktur
    assert client.post(url, headers=admin_headers).status_code == 200
    assert len(calls) == 1                                              # odczyt PDF raz (cache)
    state = client.get(f"/api/invoice-batches/{bid}/sad-drafts", headers=admin_headers).json()
    assert state["drafts"][0]["summary"]["groups"] == 2
    assert client.post(f"/api/invoice-batches/{bid}/sad-drafts/999999/compare",
                       headers=admin_headers).status_code == 404


def test_page_preview_png_and_bounds(client, admin_headers, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    _, bid = _batch(client, admin_headers, db_session)
    v1 = _upload(client, admin_headers, bid, _pdf("v1")).json()["draft"]["id"]
    page = client.get(f"/api/invoice-batches/{bid}/sad-drafts/{v1}/pages/1", headers=admin_headers)
    assert page.status_code == 200 and page.headers["content-type"] == "image/png"
    assert page.content.startswith(b"\x89PNG")
    assert client.get(f"/api/invoice-batches/{bid}/sad-drafts/{v1}/pages/2",
                      headers=admin_headers).status_code == 404
```
Run: `python -m pytest tests/test_sad_drafts.py -q` → 2 nowe FAIL (404/405 — brak tras).

- [ ] **Step 2: Logika** — w `backend/app/invoices/sad_drafts.py`:
  - import: `from . import sad_compare, sad_ours, sad_parse` (moduły domeny — ARCH-001 OK);
  - wydziel sprawdzenie draftu z `decide` do funkcji i użyj jej w `decide`:
```python
def _draft(db: Session, batch: InvoiceBatch, draft_id: int) -> SadDraft:
    draft = db.get(SadDraft, draft_id)
    if draft is None or draft.batch_id != batch.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma takiego draftu SAD w tej paczce.")
    return draft


def _file(draft: SadDraft) -> str:
    path = pathlib.Path(settings.uploads_dir) / draft.attachment.stored_name
    if not path.is_file():
        raise HTTPException(status.HTTP_410_GONE, "Plik draftu SAD zniknął z serwera — wgraj go ponownie.")
    return str(path)


def compare_draft(db: Session, batch: InvoiceBatch, draft_id: int) -> dict:
    """Porównanie wersji draftu z paczką. PDF czytany raz (`parsed`, ponownie po zmianie
    PARSER_VERSION); nasza strona zawsze z bieżących pozycji; wynik zapisany w `comparison`
    (PR 3: rozbieżności do szkicu odpowiedzi „Do poprawy”)."""
    draft = _draft(db, batch, draft_id)
    parsed = draft.parsed
    if not parsed or parsed.get("v") != sad_parse.PARSER_VERSION:
        parsed = sad_parse.parse_file(_file(draft))
        draft.parsed = parsed
    comparison = {**sad_compare.compare(sad_ours.batch_side(db, batch), parsed),
                  "at": utcnow().isoformat()}
    draft.comparison = comparison
    db.commit()
    return {"draft_id": draft.id, "version": draft.version, "pages": parsed.get("pages", 0),
            **comparison}


def page_png(db: Session, batch: InvoiceBatch, draft_id: int, page: int) -> bytes:
    path = _file(_draft(db, batch, draft_id))
    if not 1 <= page <= sad_parse.page_count(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma takiej strony draftu.")
    return sad_parse.page_png(path, page - 1)
```
  - w `state()` do słownika każdego draftu dopisz: `"summary": (d.comparison or {}).get("summary"),`.

- [ ] **Step 3: Trasy** — w `backend/app/routers/sad_drafts.py`:
```python
@router.post("/invoice-batches/{batch_id}/sad-drafts/{draft_id}/compare")
def compare_sad_draft(batch_id: int, draft_id: int, db: Session = Depends(get_db),
                      user: User = docs_senders) -> dict:
    return flow.compare_draft(db, _get_batch(db, batch_id, user), draft_id)


@router.get("/invoice-batches/{batch_id}/sad-drafts/{draft_id}/pages/{page}")
def sad_draft_page(batch_id: int, draft_id: int, page: int, db: Session = Depends(get_db),
                   user: User = docs_senders) -> Response:
    png = flow.page_png(db, _get_batch(db, batch_id, user), draft_id, page)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=600"})
```

- [ ] **Step 4:** `python -m pytest tests/test_sad_drafts.py tests/test_sad_compare.py tests/test_sad_parse.py -q` → PASS.

- [ ] **Step 5: Macierz uprawnień** — `python ../tests/gen_permissions.py` (z `backend/`) wypisze 2 brakujące trasy; wklej je do `tests/permissions.yaml` pod wpisami `sad-drafts` z PR 1 z tymi samymi rolami (anon 401; admin/logistics/purchasing dostęp — wartość jak generator/istniejące wpisy; warehouse/forwarder/customs/sales 403). `python -m pytest tests/test_permissions_matrix.py tests/test_idor_scoping.py tests/test_routes_require_auth.py -q` → PASS.

- [ ] **Step 6: Commit**
```bash
git add backend/app/invoices/sad_drafts.py backend/app/routers/sad_drafts.py backend/tests/test_sad_drafts.py tests/permissions.yaml
git commit -m "feat(agencja): trasy porównania draftu SAD i podglądu stron + macierz uprawnień"
```

---

### Task 6: Front — okno „Porównaj”

**Files:**
- Modify: `frontend/src/types/invoices.ts`
- Modify: `frontend/src/i18n/features/agencja-sad.ts`
- Create: `frontend/src/SadCompareModal.tsx`, `frontend/src/SadCompareModal.css`, `frontend/src/SadCompareModal.dom.test.tsx`
- Modify: `frontend/src/AgencySadSection.tsx`, `frontend/src/AgencySadSection.dom.test.tsx`

**Interfaces:**
- Consumes: trasy z Task 5 (kontrakt wyżej — front testowany na mocku, nie czeka na backend); `Modal` (`./components`, props `title`, `onClose`, `width`); `formatNum` (`./dates`); `CheckIcon`, `TriangleAlertIcon` (`lucide-react`).
- Produces: `export function SadCompareModal({ batchId, draft, onClose, onCompared })`.

- [ ] **Step 1: Typy** — w `frontend/src/types/invoices.ts` po `AgencySadState` dopisz, a w `SadDraft` dodaj pole `summary?: SadSummary | null`:
```ts
export interface SadSummary { groups: number; ok: number; diff: number; manual: number; all_ok: boolean }

// pole porównania: nasze ↔ SAD; ok === null → nie sprawdzono automatycznie (sprawdź w PDF)
export interface SadField { ours: string | null; sad: string | null; diff_pct: number | null; ok: boolean | null }

export interface SadGroup {
  cn: string
  status: 'ok' | 'diff' | 'manual' | 'missing_in_sad' | 'extra_in_sad'
  refs: string[]
  sad_items: number[]
  suppl_unit: string
  value: SadField
  net_mass: SadField
  suppl_qty: SadField | null
}

export interface SadHeaderRow {
  field: 'invoices' | 'currency' | 'total' | 'country'
  ours: string
  sad: string | null
  diff_pct: number | null
  ok: boolean | null
  detail: string
}

export interface SadComparison {
  draft_id: number
  version: number
  pages: number
  at: string
  header: SadHeaderRow[]
  groups: SadGroup[]
  no_cn: string[]
  unread: { item: number | null; field: string }[]
  error: 'no_text' | 'unreadable_pdf' | null
  tolerances: { amount_pct: number; qty_pct: number; mass_abs_kg: number }
  summary: SadSummary
}
```
(`SadSummary` musi być zadeklarowany przed użyciem w `SadDraft` albo w tym samym pliku — TS pozwala na kolejność dowolną dla interfejsów.)

- [ ] **Step 2: Teksty** — w `frontend/src/i18n/features/agencja-sad.ts` dopisz w każdym języku:
```ts
  // pl
    sadCompare: 'Porównaj', sadCompareTitle: 'Draft SAD v{v} ↔ faktury paczki', sadPage: 'Strona draftu',
    sadVerdictOk: 'zgodne', sadVerdictBad: 'rozbieżność', sadVerdictManual: 'nie sprawdzono automatycznie — porównaj z PDF',
    sadField_invoices: 'Faktury (44)', sadField_currency: 'Waluta (22)', sadField_total: 'Wartość faktur (22)',
    sadField_country: 'Kraj wysyłki (15a)', sadField_country_dispatch: 'Kraj wysyłki (15a)', sadField_items: 'Pozycje (33)',
    sadField_value: 'Cena pozycji (42)', sadField_net_mass: 'Masa netto (38)',
    sadDetail_invoices: 'brak w SAD: {v}', sadDetail_total: 'w tym koszty dodatkowe {v}', sadDetail_country: 'pochodzenie {v}',
    sadColCn: 'Kod CN (33)', sadColValue: 'Wartość: nasze / SAD', sadColMass: 'Masa netto kg: nasze / SAD',
    sadColSuppl: 'J. uzupełniające: nasze / SAD', sadColStatus: 'Status',
    sadStatus_ok: 'zgodne', sadStatus_diff: 'rozbieżność', sadStatus_manual: 'sprawdź ręcznie',
    sadStatus_missing_in_sad: 'brak w SAD', sadStatus_extra_in_sad: 'nadmiarowe w SAD',
    sadUnread: 'Nie odczytano: {list} — sprawdź w PDF obok.', sadItem: 'poz.',
    sadNoCn: 'Bez kodu CN w kartotece (poza porównaniem): {list}',
    sadErr_no_text: 'Nie odczytano tekstu z PDF (skan, a OCR niedostępny) — porównaj ręcznie.',
    sadErr_unreadable_pdf: 'Pliku nie da się otworzyć jako PDF.',
    sadTolerance: 'Tolerancje z profilu dostawcy: kwoty {a}%, masa i ilości {q}% (masa netto także ±{kg} kg).',
    sadSummaryOk: '{ok}/{n} zgodne', sadSummaryIssues: 'do wyjaśnienia: {n}',
  // en
    sadCompare: 'Compare', sadCompareTitle: 'Draft SAD v{v} ↔ batch invoices', sadPage: 'Draft page',
    sadVerdictOk: 'matches', sadVerdictBad: 'mismatch', sadVerdictManual: 'not checked automatically — compare with the PDF',
    sadField_invoices: 'Invoices (44)', sadField_currency: 'Currency (22)', sadField_total: 'Invoice total (22)',
    sadField_country: 'Country of dispatch (15a)', sadField_country_dispatch: 'Country of dispatch (15a)', sadField_items: 'Items (33)',
    sadField_value: 'Item price (42)', sadField_net_mass: 'Net mass (38)',
    sadDetail_invoices: 'missing in SAD: {v}', sadDetail_total: 'incl. additional costs {v}', sadDetail_country: 'origin {v}',
    sadColCn: 'CN code (33)', sadColValue: 'Value: ours / SAD', sadColMass: 'Net mass kg: ours / SAD',
    sadColSuppl: 'Suppl. units: ours / SAD', sadColStatus: 'Status',
    sadStatus_ok: 'matches', sadStatus_diff: 'mismatch', sadStatus_manual: 'check manually',
    sadStatus_missing_in_sad: 'missing in SAD', sadStatus_extra_in_sad: 'extra in SAD',
    sadUnread: 'Not read: {list} — check the PDF alongside.', sadItem: 'item',
    sadNoCn: 'No CN code in master data (not compared): {list}',
    sadErr_no_text: 'No text could be read from the PDF (scan, OCR unavailable) — compare manually.',
    sadErr_unreadable_pdf: 'The file cannot be opened as a PDF.',
    sadTolerance: 'Supplier profile tolerances: amounts {a}%, mass and quantities {q}% (net mass also ±{kg} kg).',
    sadSummaryOk: '{ok}/{n} match', sadSummaryIssues: 'to resolve: {n}',
  // pt
    sadCompare: 'Comparar', sadCompareTitle: 'Rascunho DAU v{v} ↔ faturas do lote', sadPage: 'Página do rascunho',
    sadVerdictOk: 'conforme', sadVerdictBad: 'divergência', sadVerdictManual: 'não verificado automaticamente — compare com o PDF',
    sadField_invoices: 'Faturas (44)', sadField_currency: 'Moeda (22)', sadField_total: 'Valor das faturas (22)',
    sadField_country: 'País de expedição (15a)', sadField_country_dispatch: 'País de expedição (15a)', sadField_items: 'Adições (33)',
    sadField_value: 'Preço do artigo (42)', sadField_net_mass: 'Massa líquida (38)',
    sadDetail_invoices: 'em falta no DAU: {v}', sadDetail_total: 'inclui custos adicionais {v}', sadDetail_country: 'origem {v}',
    sadColCn: 'Código NC (33)', sadColValue: 'Valor: nosso / DAU', sadColMass: 'Massa líquida kg: nossa / DAU',
    sadColSuppl: 'Unid. suplementares: nosso / DAU', sadColStatus: 'Estado',
    sadStatus_ok: 'conforme', sadStatus_diff: 'divergência', sadStatus_manual: 'verificar manualmente',
    sadStatus_missing_in_sad: 'em falta no DAU', sadStatus_extra_in_sad: 'a mais no DAU',
    sadUnread: 'Não lido: {list} — verifique no PDF ao lado.', sadItem: 'adição',
    sadNoCn: 'Sem código NC na ficha (fora da comparação): {list}',
    sadErr_no_text: 'Não foi possível ler texto do PDF (digitalização sem OCR) — compare manualmente.',
    sadErr_unreadable_pdf: 'O ficheiro não pode ser aberto como PDF.',
    sadTolerance: 'Tolerâncias do perfil do fornecedor: valores {a}%, massa e quantidades {q}% (massa líquida também ±{kg} kg).',
    sadSummaryOk: '{ok}/{n} conformes', sadSummaryIssues: 'a esclarecer: {n}',
```

- [ ] **Step 3: Test (czerwony)** `frontend/src/SadCompareModal.dom.test.tsx`:
```tsx
// @vitest-environment jsdom
// Strażnik (2026-09-30, spec agencja-draft-sad PR 2): okno porównania draftu SAD z fakturami.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import type { SadComparison, SadDraft } from './types'

const post = vi.fn()
vi.mock('./api', () => ({ api: { post: (p: string, b: unknown) => post(p, b) }, errorMessage: String }))
vi.mock('./i18n', async orig => ({ ...(await orig<typeof import('./i18n')>()), useT: () => (k: string) => k }))

import { SadCompareModal } from './SadCompareModal'

const f = (ours: string | null, sad: string | null, ok: boolean | null, diff_pct: number | null = null) =>
  ({ ours, sad, ok, diff_pct })
const RESULT: SadComparison = {
  draft_id: 5, version: 2, pages: 2, at: '2026-09-30T10:00:00', error: null,
  no_cn: ['C3'], unread: [{ item: 1, field: 'net_mass' }],
  tolerances: { amount_pct: 0.5, qty_pct: 0, mass_abs_kg: 1 },
  summary: { groups: 3, ok: 1, diff: 2, manual: 0, all_ok: false },
  header: [
    { field: 'invoices', ours: 'T-1, T-3', sad: null, ok: false, diff_pct: null, detail: 'T-3' },
    { field: 'total', ours: '1205.5', sad: '1205.5', ok: true, diff_pct: 0, detail: '' }],
  groups: [
    { cn: '90183900', status: 'diff', refs: ['NL753'], sad_items: [1], suppl_unit: '',
      value: f('900', '950', false, 5.56), net_mass: f('12.5', '12.5', true, 0), suppl_qty: null },
    { cn: '84713000', status: 'missing_in_sad', refs: ['Z9'], sad_items: [], suppl_unit: '',
      value: f('10', null, null), net_mass: f('1', null, null), suppl_qty: null }],
}
const draft = { id: 5, version: 2 } as SadDraft

afterEach(() => { cleanup(); post.mockReset() })

describe('SadCompareModal', () => {
  it('porównuje wersję: grupy CN, nagłówek, strony PDF obok', async () => {
    post.mockResolvedValue(RESULT)
    const onCompared = vi.fn()
    render(<SadCompareModal batchId={7} draft={draft} onClose={() => {}} onCompared={onCompared} />)
    expect(await screen.findByText('90183900')).toBeTruthy()
    expect(post).toHaveBeenCalledWith('/api/invoice-batches/7/sad-drafts/5/compare', {})
    expect(screen.getByText('sadStatus_diff')).toBeTruthy()
    expect(screen.getByText('sadStatus_missing_in_sad')).toBeTruthy()
    expect(screen.getAllByRole('img', { name: /sadPage/ })).toHaveLength(2)
    expect(screen.getByRole('img', { name: 'sadVerdictBad' })).toBeTruthy()
    expect(onCompared).toHaveBeenCalled()
  })

  it('PDF bez tekstu: komunikat zamiast zgadywania', async () => {
    post.mockResolvedValue({ ...RESULT, error: 'no_text', groups: [] })
    render(<SadCompareModal batchId={7} draft={draft} onClose={() => {}} />)
    expect(await screen.findByText('sadErr_no_text')).toBeTruthy()
  })
})
```
Run (z `frontend/`): `npx vitest run src/SadCompareModal` → FAIL (brak modułu).

- [ ] **Step 4: Komponent** `frontend/src/SadCompareModal.tsx`:
```tsx
// Okno „Porównaj” draftu SAD z paczką faktur (spec 2026-09-29-agencja-draft-sad §2, PR 2):
// nagłówek (faktury, waluta, suma, kraj), grupy CN nasze ↔ SAD, strony PDF obok jako obrazki
// (CSP blokuje iframe/object — backend renderuje strony do PNG).
import { useEffect, useState } from 'react'
import { CheckIcon, TriangleAlertIcon } from 'lucide-react'
import { api, errorMessage } from './api'
import { Modal } from './components'
import { formatNum } from './dates'
import { useT } from './i18n'
import type { SadComparison, SadDraft, SadField, SadGroup } from './types'
import './SadCompareModal.css'

const STATUS_CLASS: Record<SadGroup['status'], string> = {
  ok: 'badge-ok', diff: 'badge-danger', missing_in_sad: 'badge-danger', extra_in_sad: 'badge-danger', manual: '',
}

function Verdict({ ok, t }: { ok: boolean | null; t: (key: string) => string }) {
  if (ok === true) return <span className="sad-ok" role="img" aria-label={t('sadVerdictOk')}><CheckIcon size={14} /></span>
  if (ok === false) return <span className="sad-warn" role="img" aria-label={t('sadVerdictBad')}><TriangleAlertIcon size={14} /></span>
  return <span className="muted" title={t('sadVerdictManual')}>?</span>
}

const pct = (d: number | null) => (d ? ` (${formatNum(d, 2)}%)` : '')
const pair = (f: SadField) => `${formatNum(f.ours)} / ${formatNum(f.sad)}${pct(f.diff_pct)}`

export function SadCompareModal({ batchId, draft, onClose, onCompared }: {
  batchId: number
  draft: SadDraft
  onClose: () => void
  onCompared?: () => void
}) {
  const t = useT()
  const base = `/api/invoice-batches/${batchId}/sad-drafts/${draft.id}`
  const [data, setData] = useState<SadComparison | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.post<SadComparison>(`${base}/compare`, {})
      .then(res => { setData(res); onCompared?.() })
      .catch(err => setError(errorMessage(err)))
  }, [base, onCompared])

  const unread = data?.unread.map(u => t(`sadField_${u.field}`) + (u.item ? ` (${t('sadItem')} ${u.item})` : '')) ?? []
  return (
    <Modal title={t('sadCompareTitle').replace('{v}', String(draft.version))} onClose={onClose} width={1240}>
      {error && <p className="error">{error}</p>}
      {!data && !error && <p className="muted">…</p>}
      {data && (
        <div className="sad-compare">
          <div>
            {data.error && <p className="error">{t(`sadErr_${data.error}`)}</p>}
            <ul className="sad-head">
              {data.header.map(h => (
                <li key={h.field}>
                  <Verdict ok={h.ok} t={t} /> <b>{t(`sadField_${h.field}`)}</b>: {h.ours || '—'} / {h.sad || '—'}{pct(h.diff_pct)}
                  {h.detail && <span className="muted"> · {t(`sadDetail_${h.field}`).replace('{v}', h.detail)}</span>}
                </li>
              ))}
            </ul>
            <div style={{ overflowX: 'auto' }}>
              <table className="grid">
                <thead>
                  <tr>
                    <th>{t('sadColCn')}</th><th>{t('sadColValue')}</th><th>{t('sadColMass')}</th>
                    <th>{t('sadColSuppl')}</th><th>{t('sadColStatus')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.groups.map(g => (
                    <tr key={g.cn}>
                      <td className="mono" title={g.refs.join(', ')}>{g.cn}</td>
                      <td className="num">{pair(g.value)}</td>
                      <td className="num">{pair(g.net_mass)}</td>
                      <td className="num">{g.suppl_qty ? `${pair(g.suppl_qty)} ${g.suppl_unit}` : '—'}</td>
                      <td><span className={`badge ${STATUS_CLASS[g.status]}`}>{t(`sadStatus_${g.status}`)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {unread.length > 0 && <p className="muted">{t('sadUnread').replace('{list}', unread.join(', '))}</p>}
            {data.no_cn.length > 0 && <p className="muted">{t('sadNoCn').replace('{list}', data.no_cn.join(', '))}</p>}
            <p className="muted">
              {t('sadTolerance').replace('{a}', formatNum(data.tolerances.amount_pct))
                .replace('{q}', formatNum(data.tolerances.qty_pct)).replace('{kg}', formatNum(data.tolerances.mass_abs_kg))}
            </p>
          </div>
          <div className="sad-pages">
            {Array.from({ length: data.pages }, (_, i) => (
              <img key={i} src={`${base}/pages/${i + 1}`} alt={`${t('sadPage')} ${i + 1}`}
                   width={420} height={594} loading="lazy" decoding="async" />
            ))}
          </div>
        </div>
      )}
    </Modal>
  )
}
```

`frontend/src/SadCompareModal.css` (tokeny sprawdź w `styles/00-tokens.css` / `01-tokens-base.css`: `--good`, `--danger`, `--border`):
```css
/* Okno porównania draftu SAD (SadCompareModal): tabela + strony PDF obok; wąski ekran — pod spodem */
.sad-compare { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 16px; align-items: start; }
.sad-pages { display: grid; gap: 8px; max-height: 72vh; overflow-y: auto; }
.sad-pages img { width: 100%; height: auto; border: 1px solid var(--border); border-radius: 4px; }
.sad-head { list-style: none; margin: 0 0 10px; padding: 0; display: grid; gap: 4px; }
.sad-ok { color: var(--good); }
.sad-warn { color: var(--danger); }
@media (max-width: 900px) { .sad-compare { grid-template-columns: 1fr; } }
```

- [ ] **Step 5: Sekcja „Agencja”** — w `frontend/src/AgencySadSection.tsx`:
  - `import { SadCompareModal } from './SadCompareModal'`; stan `const [comparing, setComparing] = useState<SadDraft | null>(null)`;
  - kolory decyzji (klasy `st-*` z PR 1 nie mają reguł CSS): `const DECISION_CLASS = { pending: '', accepted: 'badge-ok', rejected: 'badge-danger' }`;
  - w `<li>` wersji, zaraz po przycisku PDF:
```tsx
              {' '}<button type="button" className="btn small secondary" onClick={() => setComparing(d)}>
                {t('sadCompare')}</button>
              {d.summary && (
                <span className={`badge ${d.summary.all_ok ? 'badge-ok' : 'badge-danger'}`}>
                  {d.summary.all_ok
                    ? t('sadSummaryOk').replace('{ok}', String(d.summary.ok)).replace('{n}', String(d.summary.groups))
                    : t('sadSummaryIssues').replace('{n}', String(d.summary.diff + d.summary.manual))}
                </span>
              )}
```
  - na końcu sekcji (przed zamykającym `</div>`):
```tsx
      {comparing && <SadCompareModal batchId={batchId} draft={comparing}
                                     onClose={() => setComparing(null)} onCompared={load} />}
```
  - w `AgencySadSection.dom.test.tsx` dopisz mock okna i test:
```tsx
vi.mock('./SadCompareModal', () => ({
  SadCompareModal: ({ draft }: { draft: { version: number } }) => <p>compare v{draft.version}</p> }))

  it('„Porównaj” otwiera okno porównania wybranej wersji', async () => {
    get.mockResolvedValue({ ack: null, drafts: [draft(2), draft(1, 'rejected')] })
    render(<AgencySadSection batchId={7} />)
    fireEvent.click((await screen.findAllByRole('button', { name: 'sadCompare' }))[1])
    expect(await screen.findByText('compare v1')).toBeTruthy()
  })
```

- [ ] **Step 6: Testy frontu** (z `frontend/`): `npx tsc -b --noEmit && npx vitest run` → PASS (w tym strażniki: i18n.features/unused — prefiksy `sadField_`, `sadDetail_`, `sadStatus_`, `sadErr_` są dynamiczne; a11y.labels/buttons; images; icons.emoji; hardcoded-colors; tables.class). `npm run lint` (po `npm run lint:setup`) → bez nowych ostrzeżeń.

- [ ] **Step 7: Commit**
```bash
git add frontend/src/types/invoices.ts frontend/src/i18n/features/agencja-sad.ts frontend/src/SadCompareModal.tsx frontend/src/SadCompareModal.css frontend/src/SadCompareModal.dom.test.tsx frontend/src/AgencySadSection.tsx frontend/src/AgencySadSection.dom.test.tsx
git commit -m "feat(agencja): okno porównania draftu SAD z fakturami i podglądem stron PDF"
```

---

### Task 7: Weryfikacja całości i PR

- [ ] **Step 1:** z `backend/`: `python -m pytest tests/ -q -n auto` → PASS; `python -m ruff check .` → czysto; `python scripts/mypy_baseline.py` → „brak nowych błędów”.
- [ ] **Step 2:** migracja na PostgreSQL jak CI „Dryf schematu” (jeśli lokalny PostgreSQL dostępny): `alembic upgrade head` → `scripts/db_enum_drift.py` → `scripts/db_drift.py` → `alembic downgrade -1` → `alembic upgrade head`.
- [ ] **Step 3:** z repo: `python3 scripts/check_file_lengths.py` → OK; z `frontend/`: `npx tsc -b --noEmit && npx vitest run` → PASS.
- [ ] **Step 4:** `git fetch origin main && git merge origin/main` (merge, nie rebase), ponownie `test_migration_chain` (czy głowa nadal jedna).
- [ ] **Step 5:** push, PR na `main` z opisem: zakres PR 2, decyzje projektowe z tego planu, wyniki testów.

---

## Kolejne PR-y (osobne plany)
3. Szkic `.eml` odpowiedzi „Akceptuję” / „Do poprawy” — rozbieżności z `sad_drafts.comparison` w treści (reużycie `app/eml.py`, adresaci jak `invoice_agency.py`) + stan odprawy na kafelku kolejki („SAD do akceptacji” / „SAD OK”).
4. Wejście automatu (n8n): endpoint z tokenem automatyzacji → `add_draft(..., source="automation")`.
5. Dostrojenie odczytu do przykładowego draftu SAD od Deltaa: wzorce/układ w `sad_parse` (podbić `PARSER_VERSION`), ewentualnie rozdział kosztów dodatkowych na grupy CN, jeśli agencja je rozkłada.

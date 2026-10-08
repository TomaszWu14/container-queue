"""Kreator profilu dostawcy (etap 4): podgląd tabeli z próbki PDF i test profilu na
próbkach — BEZ zapisu faktur (nic nie trafia do InvoiceBatch/InvoiceJob).

Tylko CZYTA ekstraktor faktur (invoices/*). Produkcyjna ekstrakcja wg profilu to etap 2;
tu jest cienki adapter mapy profilu {rola: [aliasy]} → column_map ekstraktora {rola: nagłówek}.
Wzorzec z compare (supplier_profiles.extract_table_preview): nagłówki + 5 wierszy + propozycja ról.
"""
import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from .invoices import extractor, splitter
from .invoices.matching import get_material, resolve_supplier_ref
from .invoices.numbers import normalize_number
from .models import InvoiceDocKind, Supplier

logger = logging.getLogger(__name__)

PREVIEW_ROWS = 5
_SCAN_ROWS = 60


def _text(cell) -> str:
    return " ".join(str(cell or "").split())


def split_pages(pages: list, marker: str) -> dict[str, list[int]]:
    """Indeksy stron CI i PL: strona ze słowem-znacznikiem profilu = PL; bez znacznika —
    istniejący klasyfikator treści (splitter)."""
    # ponytail: strona-kontynuacja PL bez nagłówka trafia do CI; etap 2 (podział wg profilu)
    # łączy strony w dokumenty — tu wystarcza do podglądu i testu próbki
    out: dict[str, list[int]] = {"ci": [], "pl": []}
    for index, page in enumerate(pages):
        text = page.text or ""
        if marker.strip():
            is_pl = marker.strip().upper() in " ".join(text.split()).upper()
        else:
            is_pl = splitter.classify_first_page(text) == InvoiceDocKind.packing_list
        out["pl" if is_pl else "ci"].append(index)
    return out


def map_variants(role_map: dict[str, list[str]]) -> list[dict[str, str]]:
    """{rola: [a1, a2]} → [{rola: a1}, {rola: a2}] (krótsza lista powtarza ostatni alias);
    ekstraktor przyjmuje jeden nagłówek na rolę, próbki różnych faktur mają różne."""
    roles = {r: a for r, a in (role_map or {}).items() if a}
    depth = max((len(a) for a in roles.values()), default=0)
    return [{r: a[min(i, len(a) - 1)] for r, a in roles.items()} for i in range(depth)] or [{}]


def _tables(page) -> list:
    return [*page.tables, page.fallback_rows] if page.fallback_rows else list(page.tables)


def preview(pages: list, indexes: list[int], role_map: dict[str, list[str]]) -> dict:
    """Pierwsza tabela z nagłówkiem pozycji na wskazanych stronach: nagłówki, do 5 wierszy
    i propozycja ról z auto-detekcji ekstraktora ({rola: indeks kolumny})."""
    variants = map_variants(role_map)
    for index in indexes:
        for table in _tables(pages[index]):
            for pos, row in enumerate((table or [])[:_SCAN_ROWS]):
                if not row:
                    continue
                auto = extractor.identify_columns(row)
                mapped = any(extractor.apply_column_map(row, v) for v in variants if v)
                if not mapped and not ("ref" in auto and ("qty" in auto or "net" in auto)):
                    continue
                rows = [[_text(c)[:60] for c in r] for r in table[pos + 1:pos + 1 + PREVIEW_ROWS] if r]
                return {"found": True, "page": index + 1, "headers": [_text(c) for c in row],
                        "rows": rows,
                        "detected": {k: v for k, v in auto.items() if not k.startswith("_")}}
    return {"found": False, "page": None, "headers": [], "rows": [], "detected": {}}


def _parse(pages: list, role_map: dict[str, list[str]]) -> extractor.ParsedDoc:
    """Najlepszy wynik ekstrakcji (najwięcej pozycji) spośród wariantów aliasów."""
    return max((extractor.parse_pages(pages, v or None) for v in map_variants(role_map)),
               key=lambda doc: len(doc.items))


def _amount(value) -> Decimal:
    return normalize_number(value) or Decimal(0)


def run_test(db: Session, supplier: Supplier, profile, path: str) -> dict:
    """Test profilu na jednej próbce. `profile` = SupplierDocProfileIn (niezapisany stan
    kreatora) albo model. Kody błędów tłumaczy frontend."""
    try:
        pages = extractor.read_pages(path)
    except Exception:  # noqa: BLE001 — uszkodzony PDF = wynik testu, nie 500
        logger.warning("test profilu dostawcy: próbka %s nieczytelna", path, exc_info=True)
        return {"ok": False, "errors": ["unreadable"], "pages": {"ci": [], "pl": []},
                "ci_items": 0, "pl_items": 0, "matched": 0, "items": []}
    parts = split_pages(pages, profile.split_marker)
    ci = _parse([pages[i] for i in parts["ci"]], profile.ci_map)
    pl_items = len(_parse([pages[i] for i in parts["pl"]], profile.pl_map).items) if parts["pl"] else 0
    items = []
    for item in ci.items:
        ref = item["ref"]
        if profile.ref_kind == "supplier":
            ref = resolve_supplier_ref(db, supplier.client_company_id, supplier.id, ref) or ref
        items.append({"ref": item["ref"], "master_ref": ref, "qty": item["qty"],
                      "amount": item["amount"], "matched": get_material(db, ref) is not None})
    total = normalize_number(ci.total_net)
    sum_items = sum((_amount(i["amount"]) for i in ci.items), Decimal(0))         + sum((_amount(c["amount"]) for c in ci.charges), Decimal(0))
    sum_ok = None
    if total is not None:
        tolerance = abs(total) * Decimal(str(profile.tol_amount_pct)) / 100 + Decimal("0.005")
        sum_ok = abs(sum_items - total) <= tolerance
    errors = []
    if not ci.items:
        errors.append("no_ci_items")
    if sum_ok is False:
        errors.append("sum_mismatch")
    # zielony wynik bez kwot / bez pozycji PL przepuszczał nieczytelne faktury (2026-09-29, US$)
    if ci.items and sum_items == 0:
        errors.append("no_amounts")
    if parts["pl"] and not pl_items:
        errors.append("no_pl_items")
    return {"ok": not errors, "errors": errors,
            "pages": {k: [i + 1 for i in v] for k, v in parts.items()},
            "ci_items": len(ci.items), "pl_items": pl_items,
            "matched": sum(1 for i in items if i["matched"]), "items": items[:50],
            "sum_items": float(sum_items), "total": float(total) if total is not None else None,
            "sum_ok": sum_ok, "invoice_number": ci.invoice_number, "charges": ci.charges}

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field

from ..tabular import normalize_header, read_rows, to_float

logger = logging.getLogger(__name__)

REQUIRED = ("data", "produkt", "ilosc")

@dataclass
class IngestReport:
    rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    unknown_products: list[str] = field(default_factory=list)
    duplicates: int = 0

def _read_table(data: bytes, filename: str) -> tuple[list[str], list[list[str]]]:
    rows = [["" if c is None else str(c) for c in r] for r in read_rows(data, filename)]
    if not rows:
        return [], []
    return rows[0], rows[1:]

def parse_issues(data: bytes, filename: str) -> IngestReport:
    rep = IngestReport()
    try:
        header, body = _read_table(data, filename)
    except Exception:
        logger.warning("analityka: nie udało się odczytać pliku %s", filename, exc_info=True)
        rep.errors.append("Nie udało się odczytać pliku")
        return rep
    cols = {normalize_header(h, accents=False): i for i, h in enumerate(header)}
    missing = [c for c in REQUIRED if c not in cols]
    if missing:
        rep.errors.append(f"Brak kolumny: {', '.join(missing)}")
        return rep
    seen: set[tuple] = set()
    for n, raw in enumerate(body, start=2):
        def cell(name: str, raw=raw) -> str:  # raw wiązany per iteracja (B023)
            i = cols.get(name)
            return raw[i].strip() if i is not None and i < len(raw) else ""
        if not any(raw):
            continue
        try:
            d = datetime.date.fromisoformat(cell("data")[:10])
            qty = to_float(cell("ilosc") or 0)
            if qty is None:
                raise ValueError
        except ValueError:
            rep.errors.append(f"Wiersz {n}: zła data/ilość")
            continue
        produkt = cell("produkt")
        if not produkt:
            rep.errors.append(f"Wiersz {n}: brak produktu")
            continue
        magazyn = cell("magazyn")
        key = (produkt, d, magazyn)
        if key in seen:
            rep.duplicates += 1
            continue
        seen.add(key)
        rep.rows.append({"produkt": produkt, "date": d, "qty": qty,
                         "firma": cell("firma"), "magazyn": magazyn,
                         "kontrahent": cell("kontrahent")})
    return rep

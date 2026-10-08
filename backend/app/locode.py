"""Dopasowanie współrzędnych portów do bazy UN/LOCODE (UNECE, domena publiczna).

Zasób app/data/unlocode.csv.gz to przycięty oficjalny code-list (kolumny:
country, location, name, lat, lon; tylko wiersze ze współrzędnymi). Lista portów
klienta nie ma współrzędnych — dopasowujemy w kolejności:
  1) pełny kod 5-znakowy (o ile nie zaczyna się od ZZ/XX — te są niestandardowe),
  2) kraj + nazwa znormalizowana (upper, bez diakrytyków i nawiasów),
  3) lekki fuzzy (prefiks/zawieranie) TYLKO w obrębie tego samego kraju
     i tylko przy jednoznacznym (pojedynczym) kandydacie.
Brak dopasowania → None (nie zgadujemy między krajami — dane wejściowe bywają
śmieciowe, np. zły kraj przy ICD)."""
import csv
import gzip
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "unlocode.csv.gz"

Coords = tuple[float, float]


def norm_name(name: str) -> str:
    """Normalizacja nazwy do porównań: upper, bez diakrytyków, bez nawiasów,
    znaki niealfanumeryczne → spacja."""
    text = re.sub(r"\([^)]*\)", " ", name or "")
    # litery bez formy rozkładalnej w NFKD (Ł, Ø, Đ…) — mapowane ręcznie
    text = text.translate(str.maketrans("ŁłØøĐđÆæ", "LlOoDdAa"))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^0-9A-Z]+", " ", text.upper()).strip()


@lru_cache(maxsize=1)
def _index() -> tuple[dict[str, Coords], dict[tuple[str, str], Coords],
                      dict[str, list[tuple[str, Coords]]]]:
    """(kod 5-znakowy → coords, (kraj, nazwa znorm.) → coords, kraj → lista nazw).
    Ładowane raz per proces (~93k wierszy, <1 s)."""
    by_code: dict[str, Coords] = {}
    by_name: dict[tuple[str, str], Coords] = {}
    by_country: dict[str, list[tuple[str, Coords]]] = {}
    with gzip.open(_DATA, "rt", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            coords = (float(row["lat"]), float(row["lon"]))
            cc = row["country"].upper()
            by_code.setdefault(cc + row["location"].upper(), coords)
            nn = norm_name(row["name"])
            if nn:
                by_name.setdefault((cc, nn), coords)
                by_country.setdefault(cc, []).append((nn, coords))
    return by_code, by_name, by_country


def match_coords(code: str, name: str, country_code: str) -> Coords | None:
    """Współrzędne (lat, lon) dla portu z listy klienta albo None."""
    by_code, by_name, by_country = _index()
    code = (code or "").strip().upper()
    cc = (country_code or "").strip().upper()
    # 1) pełny kod — tylko standardowe (ZZ/XX to wewnętrzne kody klienta)
    if len(code) == 5 and code[:2] not in ("ZZ", "XX"):
        hit = by_code.get(code)
        if hit:
            return hit
    nn = norm_name(name)
    if not nn or not cc:
        return None
    # 2) kraj + nazwa znormalizowana
    hit = by_name.get((cc, nn))
    if hit:
        return hit
    # 3) fuzzy w obrębie kraju: prefiks/zawieranie, tylko jednoznaczny kandydat
    if len(nn) >= 4:
        candidates = {coords for cand, coords in by_country.get(cc, ())
                      if cand.startswith(nn) or nn.startswith(cand)
                      or (len(cand) >= 4 and cand in nn)}
        if len(candidates) == 1:
            return next(iter(candidates))
    return None

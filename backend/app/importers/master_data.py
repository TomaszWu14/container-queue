"""Parsery plików master data: MARM (jednostki), stany DLT, porty kontenerowe + auto-rozpoznanie
typu pliku po nagłówkach (LFA1 — importers/lfa1.py)."""

from fastapi import HTTPException, status

from ..tabular import text_rows as _parse_cport_text
from .excel import _cap, _cell_getter, _map_headers, _num, _open_first_sheet, _text
from .lfa1 import LFA1_HEADERS
from .purchasing import EKKO_HEADERS

# --- import jednostek materiałów (MARM) z eksportu SAP ---

# nagłówki SAP-owe i polskie; kolejność ma znaczenie: fragmenty jednostek
# („JEDNOSTKA OBJ”, VOLEH) przed „OBJĘTOŚĆ”/VOLUM, bo nagłówek jednostki zawiera oba.
MARM_HEADERS = [
    ("EAN", "ean"),               # „Kod EAN/UPC” (EAN11)
    ("MATNR", "material_no"),
    ("MATERIA", "material_no"),
    ("VOLEH", "volume_unit"),
    ("JEDNOSTKA OBJ", "volume_unit"),
    ("JEDN. OBJ", "volume_unit"),
    ("VOLUM", "volume"),
    ("OBJĘTOŚĆ", "volume"),
    ("UMREZ", "numerator"),
    ("LICZNIK", "numerator"),
    ("UMREN", "denominator"),
    ("MIANOWNIK", "denominator"),
    ("BRGEW", "gross_weight"),
    ("WAGA BRUTTO", "gross_weight"),
    ("GEWEI", "weight_unit"),
    ("JEDNOSTKA WAGI", "weight_unit"),
    ("JEDN. WAGI", "weight_unit"),
    ("LAENG", "length"),
    ("DŁUGOŚĆ", "length"),
    ("BREIT", "width"),
    ("SZEROKOŚĆ", "width"),
    ("HOEH", "height"),
    ("WYSOKOŚĆ", "height"),
    # MEABM / „Jedn. wymiaru” PRZED generycznym „JEDN” (unit), bo zawiera ten fragment
    ("MEABM", "dimension_unit"),
    ("JEDN. WYM", "dimension_unit"),
    ("JEDNOSTKA WYM", "dimension_unit"),
    ("MEINH", "unit"),
    ("JEDN", "unit"),           # „Jedn. miary” / „Jednostka miary” (po fragmentach wyżej)
]


def _ratio(value) -> int | None:
    """Licznik/mianownik MARM: pusto albo „0” (placeholder SAP) → 1 jak dotąd; tekst,
    liczba ujemna albo ułamek → None (błąd wiersza, zamiast cichego przelicznika 1)."""
    number = _num(value)
    if number is None:
        return 1 if not _text(value) else None
    if number == 0:
        return 1
    return int(number) if number > 0 and number.is_integer() else None


def _parse_marm_rows(content: bytes, errors: list[dict] | None = None) -> tuple[list[dict], int]:
    """Wiersze MARM + licznik pominiętych placeholderów (jednostka „0” = śmieciowy
    wiersz eksportu bez realnej jednostki — odfiltrowany). Wiersz z nieliczbowym
    przelicznikiem pomijany i dopisywany do `errors` (gdy podane)."""
    sheet = _open_first_sheet(content)
    columns: dict[str, int] = {}
    parsed: list[dict] = []
    placeholders = 0
    for line, row in enumerate(sheet.iter_rows(values_only=True), start=1):
        if not columns:
            columns = _map_headers(row, MARM_HEADERS)
            if "material_no" in columns and "unit" in columns:
                continue
            columns = {}
            continue
        get = _cell_getter(row, columns)
        material_no = _cap(_text(get("material_no")), 60)
        unit = _cap(_text(get("unit")), 10).upper()
        if not material_no:
            continue
        if unit in ("", "0"):
            placeholders += 1
            continue
        numerator = _ratio(get("numerator"))
        denominator = _ratio(get("denominator"))
        if numerator is None or denominator is None:
            if errors is not None:
                errors.append({"row": line, "material_no": material_no, "unit": unit,
                               "reason": "licznik/mianownik nie jest dodatnią liczbą całkowitą"})
            continue
        volume = _num(get("volume"))
        parsed.append({
            "material_no": material_no,
            "unit": unit,
            "numerator": numerator,
            "denominator": denominator,
            # objętość „0” to placeholder SAP — trzymamy None (brak danych)
            "volume": volume if volume else None,
            "volume_unit": _cap(_text(get("volume_unit")), 10).upper(),
            "gross_weight": _num(get("gross_weight")),
            "weight_unit": _cap(_text(get("weight_unit")), 10).upper(),
            # wymiary „0” to placeholder SAP — trzymamy None (brak danych)
            "length": _num(get("length")) or None,
            "width": _num(get("width")) or None,
            "height": _num(get("height")) or None,
            "dimension_unit": _cap(_text(get("dimension_unit")), 10).upper(),
            "ean": _cap(_text(get("ean")), 20),
        })
    if not columns:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie znaleziono nagłówków eksportu MARM (Materiał / Jednostka).")
    return parsed, placeholders


# --- import stanów DLT z xlsx (fallback gdy Power BI ich nie podaje) ---

# kolejność: bardziej szczegółowe fragmenty przed generycznymi
DLT_HEADERS = [
    ("PRODUKT", "produkt"),
    ("MATERIA", "produkt"),         # MATERIAŁ / MATERIAL
    ("INDEKS", "produkt"),
    ("NR HU", "hu"),
    ("NUMER HU", "hu"),
    ("GŁÓWNA HU", "hu"),
    ("HU", "hu"),
    ("ILOŚĆ", "ilosc"),
    ("ILOSC", "ilosc"),
    ("STAN", "ilosc"),
    ("SZT", "ilosc"),
    ("QTY", "ilosc"),
    ("LOKAL", "lokalizacja"),
    ("MIEJSC", "lokalizacja"),
    ("LOCATION", "lokalizacja"),
]


def _parse_dlt_stock_rows(content: bytes) -> list[dict]:
    """Wiersze stanów DLT. Wymagane nagłówki: produkt + ilość (HU/lokalizacja opcjonalne).
    Wiersze bez produktu pomijane; 422 gdy nie znaleziono nagłówków."""
    sheet = _open_first_sheet(content)
    columns: dict[str, int] = {}
    parsed: list[dict] = []
    for row in sheet.iter_rows(values_only=True):
        if not columns:
            columns = _map_headers(row, DLT_HEADERS)
            if "produkt" in columns and "ilosc" in columns:
                continue
            columns = {}
            continue
        get = _cell_getter(row, columns)
        produkt = _cap(_text(get("produkt")), 60)
        if not produkt:
            continue
        parsed.append({
            "produkt": produkt,
            "ilosc": _num(get("ilosc")) or 0.0,
            "hu": _cap(_text(get("hu")), 64),
            "lokalizacja": _cap(_text(get("lokalizacja")), 120),
        })
    if not columns:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie znaleziono nagłówków stanów DLT (Produkt / Ilość).")
    return parsed


# --- import portów kontenerowych (słownik globalny, warstwa mapy trackingu) ---

# kolejność ma znaczenie: „COUNTRY NAME” przed „COUNTRY”, „PORT NAME” przed „NAME”
CPORT_HEADERS = [
    ("COUNTRY NAME", "country_name"),
    ("NAZWA KRAJU", "country_name"),
    ("PORT NAME", "name"),
    ("NAZWA", "name"),
    ("CODE", "code"),
    ("KOD", "code"),
    ("COUNTRY", "country_code"),
    ("KRAJ", "country_code"),
]


def _parse_cport_rows(content: bytes, filename: str) -> list[dict]:
    """Porty z xlsx albo pliku tekstowego z tabulatorami — dopasowanie po nagłówkach."""
    if (filename or "").lower().endswith((".xlsx", ".xlsm")):
        raw_rows = [list(r) for r in _open_first_sheet(content).iter_rows(values_only=True)]
    else:
        raw_rows = _parse_cport_text(content)
    columns: dict[str, int] = {}
    parsed: list[dict] = []
    for row in raw_rows:
        if not columns:
            columns = _map_headers(row, CPORT_HEADERS)
            if "code" in columns and "name" in columns:
                continue
            columns = {}
            continue
        get = _cell_getter(row, columns)
        code = _cap(_text(get("code")), 10).upper()
        name = _cap(_text(get("name")), 160)
        if not code or not name:
            continue
        parsed.append({
            "code": code,
            "name": name,
            "country_code": _cap(_text(get("country_code")), 2).upper(),
            "country_name": _cap(_text(get("country_name")), 80),
        })
    if not columns:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie znaleziono nagłówków listy portów (CODE / PORT NAME).")
    return parsed


# --- auto-rozpoznanie pliku master data (#18): jeden dropzone, typ po nagłówkach ---

# typ → (mapa nagłówków, klucze wymagane do pełnego dopasowania)
MASTER_TYPES: dict[str, tuple[list[tuple[str, str]], set[str]]] = {
    "marm": (MARM_HEADERS, {"material_no", "unit"}),
    "ekko": (EKKO_HEADERS, {"order_number", "supplier_sap"}),
    "lfa1": (LFA1_HEADERS, {"sap_code", "name1"}),
    "cports": (CPORT_HEADERS, {"code", "name"}),
}


def detect_master_type(content: bytes, filename: str) -> tuple[str | None, list[str]]:
    """Rozpoznaje typ pliku master data po nagłówkach (pierwsze 20 wierszy).

    Zwraca (typ, częściowe dopasowania). Pełne dopasowanie = komplet kluczy wymaganych;
    przy kilku pełnych wygrywa najwyższy licznik dopasowanych kolumn (LFA1 vs porty:
    „NAZWA 1"/„KOD POCZT." łapią też generyczne fragmenty portów). Remis → niepewność."""
    is_xlsx = (filename or "").lower().endswith((".xlsx", ".xlsm"))
    if is_xlsx:
        sheet = _open_first_sheet(content)
        raw_rows = [list(r) for _, r in zip(range(20), sheet.iter_rows(values_only=True), strict=False)]
    else:
        raw_rows = _parse_cport_text(content)[:20]
    full: dict[str, int] = {}
    partial: list[str] = []
    for kind, (headers, required) in MASTER_TYPES.items():
        if not is_xlsx and kind != "cports":
            continue  # pliki tekstowe obsługuje tylko import portów
        best: dict[str, int] = {}
        for row in raw_rows:
            cols = _map_headers(row, headers)
            if len(cols) > len(best):
                best = cols
        if required <= set(best):
            full[kind] = len(best)
        elif best:
            partial.append(kind)
    if len(full) == 1:
        return next(iter(full)), []
    if full:
        ranked = sorted(full.items(), key=lambda kv: -kv[1])
        if ranked[0][1] > ranked[1][1]:
            return ranked[0][0], []
        return None, [k for k, _ in ranked]
    return None, partial

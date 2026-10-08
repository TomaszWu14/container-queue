"""Parsery zamówień: arkusz ETD (zamówienia zakupowe, wczesny etap) i eksport
SAP EKKO (nagłówki zamówień) + auto-link zamówienia do kontenera po numerze."""
from fastapi import HTTPException, status

from ..order_numbers import split_order_numbers
from .excel import _cap, _cell_getter, _date, _map_headers, _num, _open_first_sheet, _text

# nagłówek ETD -> pole. Kolejność ma znaczenie: „INLAND" przed „AMOUNT", bo nagłówek
# „Expected Inland Charge Max. Amount/40'HQ" zawiera oba (pierwsze dopasowanie wygrywa).
ETD_HEADERS = [
    ("ORDER NO", "order_no"),
    ("ETD", "etd"),
    ("SUPPLIER", "supplier"),
    ("PI NO", "pi_no"),
    ("PRODUCT", "products"),
    ("CBM", "cbm"),
    ("STANDARD TT", "tt_type"),
    ("BY SEA", "transport_mode"),
    ("YES/NO", "purchase_decision"),
    ("PORT OF DEPARTURE", "port_of_departure"),
    ("INLAND", "expected_inland_charge"),
    ("CONTAINER", "container_type"),
    ("AMOUNT", "amount"),
    ("READY", "ready_date"),
    ("OEM", "oem_sample_date"),
    ("SHIPPER", "shipper_contact"),
    ("CONSIGNEE", "consignee"),
    ("DISCHARGE", "port_of_discharge"),
    ("FORWARDER", "forwarder"),
]


def _order_tokens(text: str) -> set[str]:
    """Numery zamówień jako CAŁE tokeny (kanon: order_numbers.split_order_numbers).
    order_no bywa złożony („A & B", „4500625519A") — token „4500625519A" zostaje cały.
    Dodatkowo części po myślniku (jak przed kanonem): ETD „4500625519-1" linkuje się
    do kontenera z „4500625519"."""
    tokens = set(split_order_numbers(text))
    return tokens | {p for t in tokens for p in t.split("-") if p}


def _link_container_id(order_no: str, containers: list[tuple[int, str]]) -> int | None:
    """ID kontenera, którego order_numbers dzieli wspólny CAŁY numer z order_no.
    Dopasowanie po równości tokenów (nie substring) — „4500024” nie zlinkuje się
    fałszywie do kontenera z „4500624622” (i odwrotnie)."""
    tokens = _order_tokens(order_no)
    for cid, order_numbers in containers:
        if tokens & _order_tokens(order_numbers):
            return cid
    return None


def _parse_etd_rows(content: bytes) -> list[dict]:
    sheet = _open_first_sheet(content)
    columns: dict[str, int] = {}
    parsed: list[dict] = []
    for row in sheet.iter_rows(values_only=True):
        if not columns:
            columns = _map_headers(row, ETD_HEADERS)
            if "order_no" in columns:
                continue
            columns = {}
            continue
        get = _cell_getter(row, columns)
        order_no = _cap(_text(get("order_no")), 120)
        if not order_no:
            continue  # wiersz pusty / separator
        parsed.append({
            "order_no": order_no,
            "etd": _date(get("etd")),
            "supplier": _cap(_text(get("supplier")), 160),
            "pi_no": _cap(_text(get("pi_no")), 120),
            "products": _text(get("products")),
            "cbm": _num(get("cbm")),
            "tt_type": _cap(_text(get("tt_type")), 40),
            "transport_mode": _cap(_text(get("transport_mode")), 40),
            "purchase_decision": _cap(_text(get("purchase_decision")), 20),
            "port_of_departure": _cap(_text(get("port_of_departure")), 120),
            "container_type": _cap(_text(get("container_type")), 40),
            "expected_inland_charge": _cap(_text(get("expected_inland_charge")), 80),
            "amount": _num(get("amount")),
            "ready_date": _cap(_text(get("ready_date")), 60),
            "oem_sample_date": _cap(_text(get("oem_sample_date")), 60),
            "shipper_contact": _cap(_text(get("shipper_contact")), 200),
            "consignee": _cap(_text(get("consignee")), 120),
            "port_of_discharge": _cap(_text(get("port_of_discharge")), 120),
            "forwarder": _cap(_text(get("forwarder")), 160),
        })
    if not columns:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie znaleziono nagłówka arkusza ETD (kolumna „Order No.”).")
    return parsed


# --- import nagłówków zamówień (EKKO) z eksportu SAP ---

EKKO_HEADERS = [
    ("DOK.ZAOPATRZ", "order_number"),
    ("RODZAJ DOK", "doc_kind"),
    ("DOSTAWCA MATERIA", "_ignore"),     # przed „DOSTAWCA”: inaczej złapie tę kolumnę
    ("DOSTAWCA", "supplier_sap"),
    ("UTWORZONE PRZEZ", "buyer"),
    ("GRUPA ZAOPATRZ", "buyer_group"),
    ("WARUNKI PŁAT", "payment_terms"),
    ("PŁATNOŚĆ DO", "payment_days"),
    ("KURS WALUTY", "fx_rate"),          # przed „WALUTA” — inaczej złapie tę kolumnę
    ("WALUTA", "currency"),
    ("WART.CAŁK", "amount"),
    ("INCOTERMS (CZ", "incoterms_place"),
    ("INCOTERMS", "incoterms"),
    ("DATA DOKUMENTU", "doc_date"),
    ("DATA DOSTAWY", "delivery_date"),
    ("WYMAGANA DATA WYSY", "required_ship_date"),
    ("PLANOWANA DATA WYSY", "planned_ship_date"),
    ("ZAMÓWIENIE DOSTAWCY", "supplier_order_no"),
    ("ASAP", "is_asap"),
    ("POTWIERDZONE PRZEZ DOSTAWC", "supplier_confirmed"),
    ("ZATWIERDZONE ARTWORKI", "artwork_approved"),
]

EKKO_DATES = ("doc_date", "delivery_date", "required_ship_date", "planned_ship_date")
EKKO_FLAGS = ("is_asap", "supplier_confirmed", "artwork_approved")


def _parse_ekko_rows(content: bytes) -> list[dict]:
    """Nagłówki zamówień z eksportu EKKO. Kolumny stałe (jednostka gosp., schemat, NIP)
    świadomie pomijane — nie niosą informacji."""
    sheet = _open_first_sheet(content)
    columns: dict[str, int] = {}
    parsed: list[dict] = []
    for row in sheet.iter_rows(values_only=True):
        if not columns:
            columns = _map_headers(row, EKKO_HEADERS)
            if "order_number" in columns and "supplier_sap" in columns:
                continue
            columns = {}
            continue
        get = _cell_getter(row, columns)
        order_number = _cap(_text(get("order_number")), 60)
        if not order_number:
            continue
        payment_days = _num(get("payment_days"))
        entry: dict[str, object] = {
            "order_number": order_number,
            "doc_kind": _cap(_text(get("doc_kind")), 10),
            "supplier_sap": _cap(_text(get("supplier_sap")), 20),
            "buyer": _cap(_text(get("buyer")), 40),
            "buyer_group": _cap(_text(get("buyer_group")), 10),
            "payment_terms": _cap(_text(get("payment_terms")), 20),
            "payment_days": int(payment_days) if payment_days is not None else None,
            "currency": _cap(_text(get("currency")), 3),
            "fx_rate": _num(get("fx_rate")),
            "amount": _num(get("amount")),
            "incoterms": _cap(_text(get("incoterms")), 10),
            "incoterms_place": _cap(_text(get("incoterms_place")), 60),
            "supplier_order_no": _cap(_text(get("supplier_order_no")), 60),
        }
        entry |= {key: _date(get(key)) for key in EKKO_DATES}
        # SAP koduje flagi jako „X” albo pusto
        entry |= {key: _text(get(key)).upper() == "X" for key in EKKO_FLAGS}
        parsed.append(entry)
    if not columns:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie znaleziono nagłówków eksportu EKKO "
                            "(Dok.zaopatrz. / Dostawca).")
    return parsed


# --- import pozycji zamówień (REF / EKPO) z eksportu SAP ---

SAP_HEADERS = [
    ("DOK.ZAOPATRZ", "order_number"),
    ("POZYCJA", "position"),
    ("KRÓTKI TEKST", "description"),
    ("MATERIA", "material"),
    ("ILOŚĆ ZAM", "quantity"),
    ("JEDN. MIARY", "unit"),
    ("WAGA NETTO", "net_weight"),
    ("WAGA BRUTTO", "gross_weight"),
    ("OBJĘTOŚĆ", "volume"),
    ("JEDNOSTKA OBJ", "volume_unit"),
    ("PLANOWANA DATA WYSY", "planned_ship_date"),
]


def _qty_text(value) -> str | None:
    """Ilość jako tekst znormalizowanej liczby („1 200,5” → „1200.5”) — kolumna zostaje
    tekstowa, ale odczyty (to_float) dostają zawsze liczbę. "" gdy pusto, None gdy to nie
    jest nieujemna liczba (wiersz trafia do raportu błędów)."""
    if not _text(value):
        return ""
    number = _num(value)
    if number is None or number < 0:
        return None
    return str(int(number)) if number.is_integer() else repr(number)


def _parse_ref_rows(content: bytes) -> tuple[list[dict], list[dict], int]:
    """Pozycje REF (EKPO) → (wiersze, błędy, duplikaty). Numer pozycji musi przyjść z SAP:
    przyjęcia (goods_receipt_lines) wiążą się z pozycją po jej numerze, więc syntetyczne
    „#1, #2” wg kolejności w pliku przepinały przyjęcia po reimporcie (DATA-003).
    Powtórzone (zamówienie, pozycja) — pierwszy wiersz wygrywa, reszta liczona."""
    sheet = _open_first_sheet(content)
    columns: dict[str, int] = {}
    parsed: list[dict] = []
    errors: list[dict] = []
    seen: set[tuple[str, str]] = set()
    duplicates = 0
    for line, row in enumerate(sheet.iter_rows(values_only=True), start=1):
        if not columns:
            columns = _map_headers(row, SAP_HEADERS)
            if not ("order_number" in columns and "material" in columns):
                columns = {}
            continue
        get = _cell_getter(row, columns)
        order_number = _text(get("order_number"))
        if not order_number:
            continue
        position = _text(get("position"))
        quantity = _qty_text(get("quantity"))
        if not position or quantity is None:
            errors.append({"row": line, "order_number": order_number, "position": position,
                           "reason": "brak numeru pozycji" if not position else
                           f"ilość „{_text(get('quantity'))}” nie jest liczbą"})
            continue
        if (order_number, position) in seen:
            duplicates += 1
            continue
        seen.add((order_number, position))
        parsed.append({
            "order_number": order_number,
            "position": position,
            "material": _text(get("material")),
            "description": _text(get("description")),
            "quantity": quantity,
            "unit": _text(get("unit")),
            "net_weight": _text(get("net_weight")),
            "gross_weight": _text(get("gross_weight")),
            "volume": _text(get("volume")),
            "volume_unit": _text(get("volume_unit")),
            "planned_ship_date": _date(get("planned_ship_date")),
        })
    if not columns:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie znaleziono nagłówków eksportu SAP (Dok.zaopatrz. / Materiał).")
    return parsed, errors, duplicates

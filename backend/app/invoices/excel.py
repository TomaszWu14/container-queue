"""Excel „Faktury” o STAŁYM kontrakcie kolumn (konsumenci pliku polegają na kolejności)."""
from ..exports import append_row
from ..models import InvoiceItem, InvoiceJob
from .numbers import normalize_number

COLUMNS = ["Nr faktury", "Ilość", "REF", "Nazwa PL", "Waga netto", "Waga brutto",
           "Przelicznik jednostki", "Kwota", "Kod celny (CN)", "SENT",
           "Status dopasowania"]


def _cell(value: str, prefer_decimal: bool = False):
    """Liczba jako komórka LICZBOWA (odbiorca sumuje/importuje do SAP) — tekst „1,000”
    Excel traktowałby jako napis; nierozpoznana wartość zostaje tekstem, nie znika."""
    text = (value or "").strip()
    if not text:
        return ""
    number = normalize_number(text, prefer_decimal=prefer_decimal)
    if number is None:
        return text
    return int(number) if number == number.to_integral_value() else float(number)


def row_values(item: InvoiceItem, invoice_number: str) -> list:
    return [
        invoice_number or "",
        _cell(item.qty),
        item.master_ref or item.raw_ref or "",
        item.name_pl or "",
        _cell(item.weight_net, prefer_decimal=True),
        _cell(item.weight_gross, prefer_decimal=True),
        _cell(item.uom_factor, prefer_decimal=True),
        _cell(item.amount),
        item.tariff_cn or "",
        "TAK" if item.sent else "NIE",
        getattr(item.match_status, "value", item.match_status) or "",
    ]


def build_workbook(jobs: list[InvoiceJob]):
    """Arkusz z zatwierdzonych dokumentów; pozycje pominięte nie wchodzą."""
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Faktury"
    append_row(ws, COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for job in jobs:
        for item in job.items:
            if item.skipped:
                continue
            append_row(ws, row_values(item, job.invoice_number))
        # koszty dodatkowe z faktury (bez REF) — osobny wiersz, żeby suma zgadzała się z fakturą
        for charge in (job.check_data or {}).get("charges") or []:
            append_row(ws, [job.invoice_number or "", "", "", f"Koszty dodatkowe: {charge.get('desc', '')}",
                            "", "", "", _cell(charge.get("amount")), "", "", "koszt dodatkowy"])
    return wb


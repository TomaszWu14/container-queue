"""Jedno miejsce prawdy dla eksportów arkuszy (xlsx/csv) — ochrona przed wstrzyknięciem formuł.

Każdy eksport backendu zapisuje wiersze przez `append_row` (xlsx) albo `csv_safe` (csv);
bez tego tekst użytkownika zaczynający się od „=” (np. =HYPERLINK(...)) staje się żywą formułą.
"""

from openpyxl.cell.cell import Cell

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def append_row(ws, values) -> None:
    """`ws.append` + wymuszenie typu tekstowego: openpyxl zapisałby napis od „=” jako FORMUŁĘ.
    Liczby/daty zostają sobą, każdy napis zostaje napisem (bez zmiany treści).

    Typ ustawiany na komórce PRZED dołożeniem wiersza — wcześniej szukanie dołożonego wiersza
    przez `ws[ws.max_row]` skanowało cały arkusz przy każdym wierszu (O(n²): 2000 wierszy ≈ 38 s,
    audyt PERF-002)."""
    cells = []
    for value in values:
        cell = Cell(ws, value=value)
        if isinstance(value, str) and cell.data_type != "s":
            cell.data_type = "s"
        cells.append(cell)
    ws.append(cells)


_FORMULA_START = ("=", "+", "-", "@")


def csv_safe(value) -> str:
    """Neutralizuje wstrzyknięcie formuł CSV (Excel) — pola zaczynające się od = + - @,
    także po wiodących białych znakach (Excel je pomija), oraz od \\t i \\r (OWASP, SEC-008)."""
    text = "" if value is None else str(value)
    risky = (text[:1] in ("\t", "\r")
             or text.lstrip(" \t\r\n")[:1] in _FORMULA_START)
    return "'" + text if risky else text

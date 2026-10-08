"""Wspólne helpery importów z Excela: odczyt komórek, dopasowanie nagłówków, skoroszyt."""
import datetime

from ..tabular import load_workbook_or_422 as _load_workbook
from ..tabular import to_float as _num  # noqa: F401 — nazwa importów (master_data, purchasing)


def _cap(value: str, n: int) -> str:
    """Przycina wartość do limitu kolejny (import nie może wywalić się na za długiej
    komórce Excela — lepiej wpisać skróconą wartość niż stracić cały wiersz)."""
    return value if len(value) <= n else value[:n]


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    return str(value).strip()


def _date(value) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return None


def _map_headers(header_row, mapping: list[tuple[str, str]]) -> dict[str, int]:
    """Dopasowuje nagłówki arkusza do kluczy wg fragmentów tekstu (odporne na kolejność)."""
    columns: dict[str, int] = {}
    for index, cell in enumerate(header_row):
        title = _text(cell).upper()
        if not title:
            continue
        for fragment, key in mapping:
            if fragment in title and key not in columns:
                columns[key] = index
                break
    return columns


def _cell_getter(row, columns: dict[str, int]):
    """Zwraca funkcję pobierającą wartość komórki po kluczu (None gdy poza zakresem)."""
    def get(key: str):
        return row[columns[key]] if key in columns and columns[key] < len(row) else None
    return get


def _open_first_sheet(content: bytes):
    """Pierwszy arkusz skoroszytu."""
    return _load_workbook(content).worksheets[0]


"""Jedno miejsce prawdy dla importów tabelarycznych: skoroszyt xlsx, tekst csv/tsv,
liczby i nagłówki. Importy (kolejka, master data, PAZ, analityka, materiały) używają tego
zamiast własnych kopii — ta sama obsługa błędów (uszkodzony plik = 422, nie 500)."""
import csv
import io
import re
import unicodedata
import zipfile

from fastapi import HTTPException, status

from .invoices.numbers import normalize_number

XLSX_EXT = (".xlsx", ".xlsm")
# SEC-009: xlsx to ZIP — limit sumy rozmiarów po rozpakowaniu (anty zip-bomba). zipfile
# (którego używa openpyxl) nie rozpakuje więcej, niż deklaruje ZipInfo.file_size.
XLSX_MAX_UNCOMPRESSED_MB = 200


def load_workbook_or_422(content: bytes):
    """Skoroszyt (read-only, wartości zamiast formuł); 422 gdy pliku nie da się odczytać."""
    from openpyxl import load_workbook
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            total = sum(info.file_size for info in archive.infolist())
    except (zipfile.BadZipFile, ValueError):
        total = 0   # nie-ZIP: niech openpyxl zgłosi błąd formatu (422) jak dotąd
    if total > XLSX_MAX_UNCOMPRESSED_MB * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"Skoroszyt po rozpakowaniu przekracza {XLSX_MAX_UNCOMPRESSED_MB} MB.")
    try:
        return load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Nie udało się odczytać pliku — wymagany format .xlsx/.xlsm.") from exc


def text_rows(content: bytes) -> list[list[str]]:
    """Wiersze pliku tekstowego (csv/tsv/txt), puste linie pominięte. Separator z pierwszej
    linii: tab ma pierwszeństwo, potem częstszy z ; i , (Excel PL zapisuje csv ze średnikiem)."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1250", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    first = lines[0]
    delimiter = "\t" if "\t" in first else (";" if first.count(";") >= first.count(",") else ",")
    return list(csv.reader(lines, delimiter=delimiter))


def read_rows(content: bytes, filename: str) -> list[list]:
    """Wszystkie wiersze (z nagłówkiem) pierwszego arkusza xlsx albo pliku tekstowego."""
    if (filename or "").lower().endswith(XLSX_EXT):
        wb = load_workbook_or_422(content)
        try:
            return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
        finally:
            wb.close()
    return text_rows(content)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_header(value, accents: bool = True) -> str:
    """Nagłówek do porównań: małe litery, zwinięte białe znaki; `accents=False` zdejmuje
    polskie znaki („Ilość” → „ilosc”)."""
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    return text if accents else strip_accents(text)


def to_float(value) -> float | None:
    """Liczba z komórki albo None (pusto/nie-liczba). Tekst przez normalize_number: spacje,
    NBSP, „1 234,5”, „1.234,5”, „1,234.5”; pojedynczy przecinek to separator dziesiętny
    („1,500” = 1.5 — jak dotychczasowe kopie `.replace(",", ".")`)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    number = normalize_number(value, prefer_decimal=True)
    return None if number is None else float(number)

"""Walidacja numeru kontenera wg ISO 6346 (4 litery + 6 cyfr + cyfra kontrolna)."""
import re

_FORMAT = re.compile(r"^[A-Z]{4}\d{7}$")

def _build_letter_values() -> dict[str, int]:
    """A=10, dalej +1 z pominięciem wielokrotności 11 (11, 22, 33)."""
    values, v = {}, 10
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if v % 11 == 0:
            v += 1
        values[ch] = v
        v += 1
    return values


_LETTER_VALUES = _build_letter_values()


def normalize(number: str) -> str:
    return re.sub(r"\s+", "", (number or "")).upper()


def check_digit(number: str) -> int:
    """Reszta z dzielenia przez 11 dla pierwszych 10 znaków numeru (0-10).

    Reszta 10 → cyfra kontrolna 0 (norma tylko ZALECA unikać takich numerów seryjnych) —
    `validate` przyjmuje je z ostrzeżeniem (decyzja właściciela 2026-09-28, audyt DATA-004).
    """
    total = 0
    for i, ch in enumerate(number[:10]):
        value = _LETTER_VALUES[ch] if ch.isalpha() else int(ch)
        total += value * (2 ** i)
    return total % 11


def validate(number: str) -> tuple[bool, str]:
    """Zwraca (czy_poprawny, komunikat_po_polsku)."""
    n = normalize(number)
    if not _FORMAT.match(n):
        return False, "Numer kontenera musi mieć format ISO 6346: 4 litery + 7 cyfr (np. MSDU0806613)."
    expected = check_digit(n)
    if expected == 10:
        if n[10] != "0":
            return False, f"Błędna cyfra kontrolna ISO 6346 — dla {n[:10]} powinna być 0."
        # poprawny wg normy, ale rzadki (seria „do unikania”) — przyjmujemy, sprawdź numer
        return True, f"Uwaga: {n} ma rzadką cyfrę kontrolną 0 (reszta 10) — sprawdź numer z dokumentem."
    if int(n[10]) != expected:
        return False, f"Błędna cyfra kontrolna ISO 6346 — dla {n[:10]} powinna być {expected}."
    return True, ""

"""Jedno miejsce prawdy dla dzielenia Container.order_numbers (i order_no zamówień).

Numer = CAŁY token: separatorem jest wszystko poza [0-9A-Za-z-] (przecinek, średnik,
spacja, nowa linia, „&", „/"...). Sufiks zostaje („4500625519A"), myślnik wewnątrz
numeru też („PO-100"); myślniki na brzegach tokenu są odcinane."""
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Container

_SEP = re.compile(r"[^0-9A-Za-z-]+")


def split_order_numbers(text: str | None) -> list[str]:
    """Numery z tekstu w kolejności wystąpienia, bez duplikatów i pustych."""
    out: dict[str, None] = {}
    for tok in _SEP.split(text or ""):
        tok = tok.strip("-")
        if tok:
            out[tok] = None
    return list(out)


def container_order_numbers(container: "Container") -> list[str]:
    """Numery zamówień kontenera: powiązane PO + numery z pola tekstowego.
    Całe tokeny z numerem (≥4 cyfry, np. „4500625519A") PLUS każdy ciąg \\d{4,} — ten
    drugi zbiór to stare zachowanie („PO4500012345" → numer SAP „4500012345")."""
    text = container.order_numbers or ""
    numbers = {t for t in split_order_numbers(text) if re.search(r"\d{4,}", t)}
    numbers.update(re.findall(r"\d{4,}", text))
    if container.order:
        numbers.add(container.order.number)
    return sorted(numbers)

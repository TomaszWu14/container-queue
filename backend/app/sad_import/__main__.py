"""CLI: podglądy WinSAD (PDF) → walidacja + raport Excel. Z katalogu backend/:

    python -m app.sad_import SAD1.pdf SAD2.pdf -o raport.xlsx

Na stdout krótkie podsumowanie każdego pliku (bez danych osobowych — parser ich nie czyta),
plik spoza WinSAD → komunikat na stderr i dalej z kolejnymi. Kod wyjścia: 0 = wszystkie pliki
odczytane i żadnego ERROR, 1 = jakikolwiek ERROR albo plik nie do odczytania."""
import argparse
import io
import sys
from pathlib import Path

from .excel import build_workbook
from .parser import SadFormatError, Zgloszenie, parse_sad
from .validator import ERROR, OK, WARN, Wynik, najgorszy, validate


def _podsumowanie(plik: Path, z: Zgloszenie, wyniki: list[Wynik]) -> str:
    liczba = {s: sum(w.status == s for w in wyniki) for s in (WARN, ERROR)}
    linie = [f"{plik.name}: SAD {z.numer or '?'}, pozycji {len(z.pozycje)}, "
             f"status {najgorszy(wyniki)} (WARN: {liczba[WARN]}, ERROR: {liczba[ERROR]})"]
    for w in wyniki:
        if w.status != OK:
            gdzie = f"poz. {w.pozycja}" if w.pozycja is not None else "zgłoszenie"
            linie.append(f"  {w.status} [{gdzie}] {w.regula}: oczekiwane {w.oczekiwane}, "
                         f"odczytane {w.odczytane}")
    return "\n".join(linie)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):   # konsola cp1250 nie zna „Σ”/„×” z nazw reguł
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(prog="python -m app.sad_import",
                                     description="Walidacja podglądów zgłoszeń WinSAD i raport xlsx.")
    parser.add_argument("pliki", nargs="+", type=Path, help="PDF „Podgląd danych zgłoszenia”")
    parser.add_argument("-o", "--output", type=Path, default=Path("raport_sad.xlsx"),
                        help="plik wynikowy xlsx (domyślnie raport_sad.xlsx)")
    args = parser.parse_args(argv)

    zgloszenia: list[Zgloszenie] = []
    wyniki: list[list[Wynik]] = []
    blad = False
    for plik in args.pliki:
        if not plik.is_file():
            print(f"{plik}: nie ma takiego pliku", file=sys.stderr)
            blad = True
            continue
        try:
            z = parse_sad(str(plik))
        except SadFormatError as exc:
            print(f"{plik.name}: {exc}", file=sys.stderr)
            blad = True
            continue
        z.plik = plik.name
        w = validate(z)
        print(_podsumowanie(plik, z, w))
        zgloszenia.append(z)
        wyniki.append(w)
        blad = blad or najgorszy(w) == ERROR

    if not zgloszenia:
        print("Żadnego zgłoszenia do raportu — plik xlsx nie powstał.", file=sys.stderr)
        return 1
    args.output.write_bytes(build_workbook(zgloszenia, wyniki).getvalue())
    print(f"Raport: {args.output} ({len(zgloszenia)} zgłoszeń)")
    return 1 if blad else 0


if __name__ == "__main__":
    sys.exit(main())

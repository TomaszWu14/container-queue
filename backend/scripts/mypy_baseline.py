"""mypy w CI z listą znanych błędów (CODE-003) — jak BASELINE w scripts/check_file_lengths.py.

Kod ma adnotacje, ale mypy zgłaszał ~180 błędów (w większości fałszywe alarmy z zawężania
typów w SQLAlchemy/FastAPI). Zamiast wyłączać całe moduły trzymamy listę znanych błędów
(bez numerów linii — edycje obok ich nie „odświeżają”) i blokujemy tylko NOWE.

  python scripts/mypy_baseline.py            # CI: nowe błędy → kod 1, naprawione → podpowiedź
  python scripts/mypy_baseline.py --update   # po naprawach: zapisz mniejszą listę

Konfiguracja mypy: [tool.mypy] w pyproject.toml. Lista: mypy-baseline.txt (może tylko maleć).
"""
import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
BASELINE = BACKEND / "mypy-baseline.txt"
_LOC = re.compile(r"^(?P<path>[^:\n]+?):\d+(?::\d+)?: error: (?P<msg>.*)$")


def normalize(output: str) -> Counter:
    """Linie `plik:linia[:kol]: error: …` → licznik `plik: …` (bez numerów linii i notatek)."""
    found: Counter = Counter()
    for line in output.splitlines():
        m = _LOC.match(line.strip())
        if m:
            path = m["path"].replace("\\", "/")
            msg = re.sub(r"\bline \d+\b", "line N", m["msg"].strip())
            found[f"{path}: {msg}"] += 1
    return found


def compare(current: Counter, baseline: Counter) -> tuple[list[str], list[str]]:
    """(nowe, naprawione) — każdy wpis tyle razy, o ile liczba się zmieniła."""
    return sorted((current - baseline).elements()), sorted((baseline - current).elements())


def _read_baseline() -> Counter:
    if not BASELINE.exists():
        return Counter()
    return Counter(ln for ln in BASELINE.read_text(encoding="utf-8").splitlines()
                   if ln.strip() and not ln.startswith("#"))


def _run_mypy() -> str:
    from mypy import api   # import tutaj: testy logiki nie wymagają mypy
    os.chdir(BACKEND)   # [tool.mypy] z backend/pyproject.toml, ścieżki `app/...`
    stdout, stderr, status = api.run([])   # pliki i opcje z [tool.mypy]
    if status == 2:   # błąd samego mypy (konfiguracja, składnia), nie typów
        sys.exit(f"mypy nie wystartował:\n{stdout}{stderr}")
    return stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="zapisz bieżące błędy jako listę")
    args = parser.parse_args()
    current = normalize(_run_mypy())
    if args.update:
        header = ("# Znane błędy mypy (CODE-003) — generuje: python scripts/mypy_baseline.py --update\n"
                  "# Lista może tylko maleć. Nowy błąd = popraw kod albo `# type: ignore[kod]` z powodem.\n")
        BASELINE.write_text(header + "".join(f"{e}\n" for e in sorted(current.elements())),
                            encoding="utf-8")
        print(f"zapisano {sum(current.values())} znanych błędów w {BASELINE.name}")
        return 0
    new, fixed = compare(current, _read_baseline())
    if fixed:
        print(f"Naprawione ({len(fixed)}) — zmniejsz listę: python scripts/mypy_baseline.py --update")
    if new:
        print(f"NOWE błędy mypy ({len(new)}):")
        print("\n".join(f"  {e}" for e in new))
        return 1
    print(f"mypy: brak nowych błędów (znanych: {sum(current.values())})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

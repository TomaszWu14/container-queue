"""Strażnik limitu długości pliku (konwencja repo: max 500 linii).

Nowy plik > LIMIT = błąd. Pliki już za długie są w BASELINE i mogą się tylko skracać —
przy refaktorze obniż (albo usuń) ich wpis. Uruchamiane w CI backendu i frontendu:
    python scripts/check_file_lengths.py
"""
import re
import subprocess
import sys
from pathlib import Path

LIMIT = 500
INCLUDE = re.compile(r"^(backend/.*\.py|frontend/src/.*\.(ts|tsx|css)|scripts/.*\.py)$")
EXCLUDE = re.compile(r"/migrations/")

# Pusty od 2026-09-24 — wszystkie pliki ≤ LIMIT. Wpis tu = świadomy wyjątek z uzasadnieniem.
BASELINE: dict[str, int] = {}


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True,
                           check=True).stdout.splitlines()
    errors = []
    for path in files:
        if not INCLUDE.match(path) or EXCLUDE.search(path) or not (root / path).is_file():
            continue
        lines = len((root / path).read_text(encoding="utf-8", errors="replace").splitlines())
        ceiling = BASELINE.get(path, LIMIT)
        if lines > ceiling:
            hint = "nie może rosnąć — wydziel kod" if path in BASELINE else f"limit {LIMIT}"
            errors.append(f"{path}: {lines} linii > {ceiling} ({hint})")
    for e in errors:
        print(e)
    if errors:
        print(f"\n{len(errors)} plik(ów) ponad limit. Podziel plik zamiast podnosić BASELINE.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

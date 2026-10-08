"""Moduły frontend/src/pages/*.tsx, których żaden test vitest nie importuje wprost (TEST-007).

Uruchamianie z katalogu głównego: python scripts/frontend_untested_pages.py
Wynik przepisz do docs/testy/E2E.md (sekcja „Strony bez testów”). Import pośredni
(strona testowana przez komponent nadrzędny) się nie liczy — lista jest zachowawcza.
"""
import re
import sys
from pathlib import Path

FE = (Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "frontend").resolve()
SRC = FE / "src"
IMPORT = re.compile(r"""(?:from\s+|import\s*\(\s*|vi\.mock\(\s*)['"](\.{1,2}/[^'"]+)['"]""")
EXTS = ("", ".tsx", ".ts", "/index.tsx", "/index.ts")


def _resolve(base: Path, spec: str) -> Path | None:
    for ext in EXTS:
        p = (base / (spec + ext)).resolve()
        if p.is_file():
            return p
    return None


def untested() -> tuple[int, list[str]]:
    imported = set()
    for t in SRC.rglob("*.test.ts*"):
        for spec in IMPORT.findall(t.read_text(encoding="utf-8")):
            if (r := _resolve(t.parent, spec)) is not None:
                imported.add(r)
    pages = sorted(p for p in (SRC / "pages").glob("*.ts*")
                   if p.suffix in (".ts", ".tsx") and ".test." not in p.name)
    return len(pages), [p.relative_to(FE).as_posix() for p in pages if p.resolve() not in imported]


if __name__ == "__main__":
    total, missing = untested()
    print(f"# modułów w src/pages: {total}, bez testu: {len(missing)}")
    print("\n".join(missing))

"""CODE-003: mypy w CI z listą znanych błędów — logika porównania (bez uruchamiania mypy)
i obecność kroku w ci-backend."""
from collections import Counter
from pathlib import Path

import yaml

from scripts import mypy_baseline as mb

ROOT = Path(__file__).resolve().parents[2]
OUT = """\
app/a.py:10: error: Item "None" of "X | None" has no attribute "y"  [union-attr]
app/a.py:10: note: See https://mypy.rtfd.io
app\\b.py:7:5: error: Name "Z" is defined on line 3  [no-redef]
app/a.py:99: error: Item "None" of "X | None" has no attribute "y"  [union-attr]
Found 3 errors in 2 files (checked 2 source files)
"""


def test_normalize_bez_numerow_linii_i_notatek():
    got = mb.normalize(OUT)
    assert got == Counter({
        'app/a.py: Item "None" of "X | None" has no attribute "y"  [union-attr]': 2,
        'app/b.py: Name "Z" is defined on line N  [no-redef]': 1,
    })


def test_compare_nowe_i_naprawione():
    base = mb.normalize(OUT)
    cur = base.copy()
    cur['app/a.py: Item "None" of "X | None" has no attribute "y"  [union-attr]'] += 1
    cur['app/c.py: Incompatible return value  [return-value]'] = 1
    del cur['app/b.py: Name "Z" is defined on line N  [no-redef]']
    new, fixed = mb.compare(cur, base)
    assert new == ['app/a.py: Item "None" of "X | None" has no attribute "y"  [union-attr]',
                   'app/c.py: Incompatible return value  [return-value]']
    assert fixed == ['app/b.py: Name "Z" is defined on line N  [no-redef]']


def test_lista_znanych_bledow_w_formacie_normalize():
    lines = [ln for ln in mb.BASELINE.read_text(encoding="utf-8").splitlines()
             if ln and not ln.startswith("#")]
    assert lines == sorted(lines)
    assert all(ln.startswith("app/") and ": " in ln and ln.rstrip().endswith("]") for ln in lines)


def test_ci_backend_sprawdza_typy():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "ci-backend.yml").read_text(encoding="utf-8"))
    runs = " ".join(s.get("run", "") for job in wf["jobs"].values() for s in job["steps"])
    assert "scripts/mypy_baseline.py" in runs
    # wersja mypy przypięta w locku narzędzi CI (cache pip), nie instalowana osobno w workflow
    lock = (ROOT / "backend" / "requirements-dev.txt").read_text(encoding="utf-8")
    assert any(line.startswith("mypy==") for line in lock.splitlines())

"""Szkic wpisów tests/permissions.yaml dla tras, których jeszcze w nim nie ma.

Uruchom z katalogu backend/:  python ../tests/gen_permissions.py
Wypisuje linie do wklejenia (NIE nadpisuje pliku — wpisy w nim są rozstrzygnięte ręcznie/testem).
Wartości '?' = rola sprawdzana w treści handlera: ustal je testem
tests/test_permissions_matrix.py::test_handler_checked_cells_match_yaml.
"""
import pathlib
import sys

import yaml

sys.path.insert(0, ".")
from tests.test_permissions_matrix import YAML_PATH, _routes, derive  # noqa: E402

have = yaml.safe_load(pathlib.Path(YAML_PATH).read_text(encoding="utf-8"))["routes"]
missing = [(k, v) for k, v in _routes().items() if k not in have]
for key, (m, p, r) in sorted(missing):
    cells = ", ".join(f"{role}: {val!r}" if isinstance(val, str) else f"{role}: {val}"
                      for role, val in derive(m, p, r).items())
    print(f'  "{key}": {{{cells}}}')
print(f"# brakujących tras: {len(missing)}", file=sys.stderr)

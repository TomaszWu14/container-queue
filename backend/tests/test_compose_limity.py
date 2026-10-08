"""INFRA-004: limity zasobów w compose serwerowych (host 4 vCPU / 4 GB RAM).

- bazy (obraz postgres): bez twardego `mem_limit` (zabicie Postgresa = ryzyko dla danych),
  z `mem_reservation`; bez ujemnego `oom_score_adj` (Docker w LXC/rootless nie wystartuje),
- pozostałe serwisy: `mem_limit` i `cpus` (domyślne ≤ zasoby hosta),
- app i n8n: dodatni `oom_score_adj` — przy braku RAM OOM killer wybiera je, nie bazę.
Lokalny stack dev (docker-compose.yml) — bez limitów.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SERVER_FILES = ("docker-compose.coolify.yml", "docker-compose.n8n.yml", "docker-compose.n8n-host.yml")
UNITS = {"k": 2**10, "m": 2**20, "g": 2**30}


def _default(value) -> str:
    """`${APP_MEM_LIMIT:-1536m}` → `1536m` (wartość, gdy zmiennej nie ustawiono w Coolify)."""
    m = re.fullmatch(r"\$\{\w+:-([^}]+)\}", str(value))
    return m.group(1) if m else str(value)


def _bytes(value) -> int:
    m = re.fullmatch(r"(\d+)([kmg])?b?", _default(value).lower())
    assert m, f"nieczytelny limit pamięci: {value}"
    return int(m.group(1)) * UNITS.get(m.group(2) or "", 1)


def _services():
    for name in SERVER_FILES:
        compose = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
        for svc, spec in compose["services"].items():
            yield f"{name}:{svc}", spec


def test_databases_reserved_not_capped():
    dbs = [(n, s) for n, s in _services() if str(s.get("image", "")).startswith("postgres:")]
    assert len(dbs) == 3
    for name, spec in dbs:
        assert "mem_limit" not in spec, name
        assert _bytes(spec.get("mem_reservation", 0)) >= 256 * 2**20, f"{name}: brak mem_reservation"
        assert int(spec.get("oom_score_adj", 0)) >= 0, f"{name}: ujemny oom_score_adj wymaga uprawnień"


def test_other_services_capped_within_host():
    for name, spec in _services():
        if str(spec.get("image", "")).startswith("postgres:"):
            continue
        assert "mem_limit" in spec and "cpus" in spec, f"{name}: brak mem_limit/cpus"
        assert _bytes(spec["mem_limit"]) <= 2 * 2**30, name
        assert 0 < float(_default(spec["cpus"])) <= 4, name


def test_app_and_n8n_go_first_under_oom():
    services = dict(_services())
    for name in ("docker-compose.coolify.yml:app", "docker-compose.n8n.yml:n8n",
                 "docker-compose.n8n-host.yml:n8n"):
        assert int(services[name].get("oom_score_adj", 0)) > 0, name
    assert _bytes(services["docker-compose.coolify.yml:app"]["mem_limit"]) >= 1024 * 2**20

"""BUILD-009: każdy serwis w compose uruchamianych na serwerze ma rotację docker logs.

Bez `logging.options` domyślny sterownik json-file trzyma logi bez limitu — najbardziej
brama nginx (access log z każdego żądania) i n8n. Wyjątek: lokalny stack dev
(docker-compose.yml), który nie działa na serwerze.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEV_ONLY = {"docker-compose.yml"}


def _server_compose_files():
    files = sorted(p for p in ROOT.glob("docker-compose*.yml") if p.name not in DEV_ONLY)
    assert {p.name for p in files} >= {"docker-compose.coolify.yml", "docker-compose.n8n.yml"}
    return files


def test_every_server_service_rotates_docker_logs():
    missing = []
    for path in _server_compose_files():
        services = yaml.safe_load(path.read_text(encoding="utf-8"))["services"]
        for name, spec in services.items():
            log = spec.get("logging") or {}
            opts = log.get("options") or {}
            # json-file jawnie: przy innym domyślnym sterowniku demona (np. journald)
            # opcje max-size/max-file byłyby nieznane i kontener by nie wstał
            if log.get("driver") != "json-file" or not opts.get("max-size") \
                    or not opts.get("max-file"):
                missing.append(f"{path.name}:{name}")
    assert not missing, f"serwisy bez rotacji docker logs: {missing}"

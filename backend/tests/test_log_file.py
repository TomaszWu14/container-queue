"""OBS-007: trwałe logi — opcjonalny plik z rotacją (LOG_FILE), maskowanie tokenów i
request-id w linii; rotacja logów Dockera w compose dla app i db."""
import logging
from pathlib import Path

import yaml

from app import logfile
from app.main import AvizoTokenLogFilter

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "Abcdefghijklmnop1234567890"


def test_log_file_masks_token_and_has_request_id(tmp_path):
    path = tmp_path / "logs" / "app.log"
    handler = logfile.attach_file_handler(str(path), AvizoTokenLogFilter())
    token = logfile.request_id_var.set("abcd1234")
    try:
        logging.getLogger("app.test_log_file").warning("GET /api/avizo/%s", TOKEN)
    finally:
        logfile.request_id_var.reset(token)
        for name in logfile.FILE_LOGGERS:
            logging.getLogger(name).removeHandler(handler)
        handler.close()
    text = path.read_text(encoding="utf-8")
    assert "/api/avizo/[token]" in text
    assert TOKEN not in text
    assert "rid=abcd1234" in text


def test_compose_rotates_docker_logs_for_app_and_db():
    compose = yaml.safe_load((ROOT / "docker-compose.coolify.yml").read_text(encoding="utf-8"))
    for name in ("app", "db"):
        log = compose["services"][name].get("logging") or {}
        assert log.get("driver") == "json-file", name
        assert log.get("options", {}).get("max-size"), name
        assert log.get("options", {}).get("max-file"), name
    app = compose["services"]["app"]
    assert "LOG_FILE" in app["environment"]
    assert any(str(v).endswith(":/data/logs") for v in app["volumes"])

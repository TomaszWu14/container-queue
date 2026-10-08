"""INFRA-008: HEALTHCHECK ze strażnikiem zawieszenia (scripts/healthcheck.py) + wymagania obrazu
i compose, bez których strażnik nie zadziała (init jako PID 1, exec uvicorn, restart)."""
import http.server
import re
import signal
import socket
import threading
from pathlib import Path

import pytest
import yaml

from scripts import healthcheck as hc

ROOT = Path(__file__).resolve().parents[2]


def _run(state, *results, restart_after=3):
    kills = []
    for r in results:
        state = hc.step(r, state, restart_after, kill=kills.append)
    return state, kills


def test_nic_nie_zabija_przed_pierwszym_zdrowym_stanem():
    # start / migracja Alembica: aplikacja jeszcze nie słucha — nie przerywamy
    state, kills = _run({}, *["down"] * 10)
    assert kills == [] and not state.get("seen_healthy")


def test_po_zawieszeniu_sigterm_potem_sigkill():
    state, kills = _run({}, "ok", "down", "down")
    assert kills == [] and state["down"] == 2
    state, kills = _run(state, "down", "down", "down")
    assert kills == [signal.SIGTERM, signal.SIGTERM, hc.KILL_SIGNAL]


def test_sygnal_ubicia_istnieje_na_kazdej_platformie():
    # signal.SIGKILL nie istnieje na Windows — import i krok strażnika nie mogą się wywracać
    assert hc.KILL_SIGNAL == getattr(signal, "SIGKILL", signal.SIGTERM)
    if hasattr(signal, "SIGKILL"):
        assert hc.KILL_SIGNAL == signal.SIGKILL   # Linux (prod) bez zmian


def test_odpowiedz_zeruje_licznik_a_503_go_nie_rusza():
    state, kills = _run({}, "ok", "down", "down", "ok", "down", "error", "error", "down")
    assert kills == [] and state["down"] == 2   # 503 (baza) nie jest zawieszeniem aplikacji


def test_wylaczenie_zmienna():
    _, kills = _run({}, "ok", *["down"] * 10, restart_after=0)
    assert kills == []


def test_stan_z_poprzedniego_startu_kontenera_jest_zerowany(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "STATE", tmp_path / "health.json")
    hc._save({"boot": "111", "seen_healthy": True, "down": 7})
    assert hc._load("111")["down"] == 7
    assert hc._load("222") == {"boot": "222"}   # restart kontenera = nowy PID 1


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(503 if self.path == "/down" else 200)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture()
def server():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_probe(server):
    assert hc.probe(server + "/ok") == "ok"
    assert hc.probe(server + "/down") == "error"
    with socket.socket() as s:          # port bez nasłuchu → odmowa połączenia
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert hc.probe(f"http://127.0.0.1:{port}/") == "down"
    with socket.socket() as hung:       # przyjmuje połączenie, nie odpowiada (zawieszony proces)
        hung.bind(("127.0.0.1", 0))
        hung.listen()
        assert hc.probe(f"http://127.0.0.1:{hung.getsockname()[1]}/", timeout=0.3) == "down"


def test_obraz_i_compose_pozwalaja_straznikowi_dzialac():
    docker = (ROOT / "Dockerfile.coolify").read_text(encoding="utf-8")
    assert re.search(r'^\s+CMD \["python", "scripts/healthcheck.py"\]', docker, flags=re.M)
    assert re.search(r'^CMD \["sh", "-c", "alembic upgrade head && exec uvicorn ', docker, flags=re.M)
    app = yaml.safe_load((ROOT / "docker-compose.coolify.yml").read_text(encoding="utf-8"))["services"]["app"]
    assert app.get("init") is True, "bez init strażnik nie zakończy procesu (PID 1)"
    assert app.get("restart") in ("unless-stopped", "always")

"""scripts/smoke.sh (audyt CICD-001): przechodzi na zdrowym wdrożeniu, pada, gdy baza leży
albo logowanie nie działa. Serwer-atrapa w wątku — skrypt woła go curlem jak prawdziwy serwer."""
import json
import os
import pathlib
import shutil
import subprocess  # nosec B404
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "smoke.sh"


def _serve(db_ok: bool):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, body):
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path == "/api/health":
                self._send(200, {"status": "ok", "database": "ok", "version": "abc123"}) if db_ok \
                    else self._send(503, {"status": "error", "database": "unavailable"})
            elif self.path == "/":
                self._send(200, "<html></html>")
            elif self.path.startswith("/api/containers"):
                ok = self.headers.get("Authorization") == "Bearer tok"
                self._send(200 if ok else 401, [])
            else:
                self._send(404, {})

        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            ok = "username=smoke" in body and "password=tajne" in body
            self._send(200, {"access_token": "tok"}) if ok else self._send(401, {})

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _run(db_ok=True, **env):
    sh = shutil.which("sh")
    if not sh or not shutil.which("curl"):
        pytest.skip("brak sh/curl")
    server = _serve(db_ok)
    try:
        script = SCRIPT.read_bytes().replace(b"\r\n", b"\n")
        return subprocess.run([sh, "-s", f"http://127.0.0.1:{server.server_port}"], input=script,
                              env={**os.environ, **env}, capture_output=True)  # nosec
    finally:
        server.shutdown()


def test_smoke_passes_on_healthy_deploy_with_login():
    proc = _run(SMOKE_LOGIN="smoke", SMOKE_PASSWORD="tajne")
    assert proc.returncode == 0, proc.stderr
    assert b"SMOKE: OK" in proc.stdout and b"kolejka ok" in proc.stdout


def test_smoke_fails_when_database_down():
    assert _run(db_ok=False).returncode != 0


def test_smoke_fails_on_bad_login():
    assert _run(SMOKE_LOGIN="smoke", SMOKE_PASSWORD="zle").returncode != 0
